"""Postgres schema and connection handling.

Every table that holds user data has a `user_id` column, and every query filters on it -
that is what keeps one person's expenses invisible to everyone else.
Money is stored as integer paise (BIGINT) to avoid rounding errors.
"""
import threading
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import (
    BigInteger, Boolean, Column, Connection, Date, DateTime, ForeignKey, Index, Integer, MetaData,
    Numeric, String, Table, create_engine, func, text,
)
from sqlalchemy.engine import Engine

from .config import get_settings

metadata = MetaData()


def _ts(name: str) -> Column:
    return Column(name, DateTime(timezone=True), nullable=False, server_default=func.now())


def _user_fk() -> Column:
    return Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


users = Table(
    "users", metadata,
    Column("id", String(32), primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("name", String(60), nullable=False),
    Column("password_hash", String(200), nullable=False),
    _ts("created_at"),
)

categories = Table(
    "categories", metadata,
    Column("id", String(40), primary_key=True),
    _user_fk(),
    Column("label", String(30), nullable=False),
    Column("emoji", String(16), nullable=False),
    Column("color", String(7), nullable=False),
    _ts("created_at"),
    Index("ix_categories_user", "user_id"),
)

cards = Table(
    "cards", metadata,
    Column("id", String(32), primary_key=True),
    _user_fk(),
    Column("name", String(40), nullable=False),
    Column("bank", String(40), nullable=False, server_default=""),
    Column("last4", String(4), nullable=False, server_default=""),
    Column("limit_paise", BigInteger, nullable=False),
    Column("available_paise", BigInteger, nullable=False),
    Column("statement_day", Integer),
    Column("due_day", Integer),
    Column("color", String(7)),
    Column("archived", Boolean, nullable=False, server_default="false"),
    _ts("created_at"),
    _ts("updated_at"),
    Index("ix_cards_user", "user_id"),
)

card_payments = Table(
    "card_payments", metadata,
    Column("id", String(32), primary_key=True),
    _user_fk(),
    Column("card_id", String(32), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("date", Date, nullable=False),
    Column("note", String(120), nullable=False, server_default=""),
    Column("kind", String(10), nullable=False, server_default="payment"),
    _ts("created_at"),
    Index("ix_card_payments_card", "user_id", "card_id"),
)

expenses = Table(
    "expenses", metadata,
    Column("id", String(48), primary_key=True),
    _user_fk(),
    Column("amount_paise", BigInteger, nullable=False),
    Column("date", Date, nullable=False),
    Column("category", String(40), nullable=False),
    Column("note", String(200), nullable=False, server_default=""),
    Column("payment_method", String(30)),
    Column("card_id", String(32)),
    Column("recurring_id", String(32)),
    Column("loan_id", String(32)),
    _ts("created_at"),
    _ts("updated_at"),
    Index("ix_expenses_user_date", "user_id", "date"),
)

budgets = Table(
    "budgets", metadata,
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("category", String(40), primary_key=True),
    Column("amount_paise", BigInteger, nullable=False),
    _ts("updated_at"),
)

recurring = Table(
    "recurring", metadata,
    Column("id", String(32), primary_key=True),
    _user_fk(),
    Column("amount_paise", BigInteger, nullable=False),
    Column("category", String(40), nullable=False),
    Column("note", String(200), nullable=False, server_default=""),
    Column("payment_method", String(30)),
    Column("card_id", String(32)),
    Column("day_of_month", Integer, nullable=False),
    Column("start_month", String(7), nullable=False),
    Column("end_month", String(7)),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("last_generated_month", String(7)),
    _ts("created_at"),
    _ts("updated_at"),
    Index("ix_recurring_user", "user_id"),
)

loans = Table(
    "loans", metadata,
    Column("id", String(32), primary_key=True),
    _user_fk(),
    Column("kind", String(10), nullable=False),
    Column("lender", String(60), nullable=False),
    Column("taken_by", String(60), nullable=False, server_default=""),
    Column("principal_paise", BigInteger, nullable=False),
    Column("note", String(200), nullable=False, server_default=""),
    Column("taken_on", Date),
    Column("interest_rate", Numeric(5, 2)),
    Column("total_interest_paise", BigInteger),
    Column("installment_paise", BigInteger),
    Column("emi_day", Integer),
    Column("emi_count", Integer),
    Column("first_emi_date", Date),
    Column("emi_adjustment", Integer, nullable=False, server_default="0"),
    Column("insurance", Boolean, nullable=False, server_default="false"),
    Column("log_emis_as_expenses", Boolean, nullable=False, server_default="false"),
    Column("payment_method", String(30)),
    Column("card_id", String(32)),
    Column("emi_log_from", Date),
    Column("last_logged_emi", Date),
    _ts("created_at"),
    _ts("updated_at"),
    Index("ix_loans_user", "user_id"),
)

loan_repayments = Table(
    "loan_repayments", metadata,
    Column("id", String(32), primary_key=True),
    _user_fk(),
    Column("loan_id", String(32), ForeignKey("loans.id", ondelete="CASCADE"), nullable=False),
    Column("amount_paise", BigInteger, nullable=False),
    Column("date", Date, nullable=False),
    Column("note", String(120), nullable=False, server_default=""),
    _ts("created_at"),
    Index("ix_repayments_loan", "loan_id"),
)


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,     # Neon scales to zero; drop dead connections transparently
        pool_recycle=240,
        # Neon's pooled endpoint runs PgBouncer in transaction mode: no server-side prepared statements.
        connect_args={"prepare_threshold": None, "connect_timeout": 15},
    )


_schema_lock = threading.Lock()
_schema_ready = False


def ensure_schema() -> None:
    """Create tables on first use (idempotent), so a fresh Neon database needs no setup."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        engine = get_engine()
        with engine.begin() as conn:
            # serialize concurrent cold starts creating the schema
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
            metadata.create_all(conn, checkfirst=True)
        _schema_ready = True


def reset_schema_flag() -> None:  # tests
    global _schema_ready
    _schema_ready = False


def get_db() -> Iterator[Connection]:
    """FastAPI dependency: one transaction per request, committed on success, rolled back on error."""
    ensure_schema()
    with get_engine().begin() as conn:
        yield conn
