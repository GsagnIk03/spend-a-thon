"""Data-access helpers shared by the routers. Every function takes the request's
connection (one transaction per request) and every query is scoped to `user_id`."""
import datetime as dt
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import Connection, and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .constants import CATEGORIES, CATEGORY_IDS, CREDIT_CARD, MAX_RANGE_MONTHS
from .db import budgets, cards, categories, expenses, loan_repayments, loans, recurring
from .utils import add_months, days_in_month, month_range, to_rupees, today


def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat()


def _rows(result) -> list[dict]:
    return [dict(r._mapping) for r in result]


def _one(result) -> dict | None:
    r = result.first()
    return dict(r._mapping) if r else None


# ======================= categories =======================
def custom_categories(conn: Connection, user_id: str) -> list[dict]:
    rows = _rows(conn.execute(
        select(categories).where(categories.c.user_id == user_id).order_by(categories.c.created_at)
    ))
    return [{"id": r["id"], "label": r["label"], "emoji": r["emoji"], "color": r["color"], "custom": True}
            for r in rows]


def all_categories(conn: Connection, user_id: str) -> list[dict]:
    defaults = [{**c, "custom": False} for c in CATEGORIES]
    return defaults[:-1] + custom_categories(conn, user_id) + defaults[-1:]  # keep "Other" last


def category_labels(conn: Connection, user_id: str) -> dict[str, str]:
    return {c["id"]: c["label"] for c in all_categories(conn, user_id)}


def check_category(conn: Connection, user_id: str, category: str) -> None:
    if category in CATEGORY_IDS:
        return
    found = conn.execute(select(categories.c.id).where(
        categories.c.id == category, categories.c.user_id == user_id)).first()
    if not found:
        raise HTTPException(422, "unknown category")


# ======================= credit cards =======================
def get_card(conn: Connection, user_id: str, card_id: str) -> dict:
    row = _one(conn.execute(select(cards).where(cards.c.id == card_id, cards.c.user_id == user_id)))
    if not row:
        raise HTTPException(404, "Card not found")
    return row


def list_cards(conn: Connection, user_id: str) -> list[dict]:
    return _rows(conn.execute(select(cards).where(cards.c.user_id == user_id).order_by(cards.c.created_at)))


def check_card(conn: Connection, user_id: str, payment_method: str | None, card_id: str | None,
               allow_archived: str | None = None) -> None:
    """A credit-card payment may name one of the user's (active) cards."""
    if payment_method != CREDIT_CARD or not card_id:
        return
    row = _one(conn.execute(select(cards.c.archived).where(cards.c.id == card_id, cards.c.user_id == user_id)))
    if not row:
        raise HTTPException(422, "unknown credit card")
    if row["archived"] and card_id != allow_archived:
        raise HTTPException(422, "that card has been removed")


def card_out(card: dict, month_spend: dict | None = None) -> dict:
    limit = int(card["limit_paise"])
    available = int(card["available_paise"])
    spend = (month_spend or {}).get(card["id"], {"total": 0, "count": 0})
    return {
        "id": card["id"],
        "name": card["name"],
        "bank": card.get("bank") or "",
        "last4": card.get("last4") or "",
        "credit_limit": to_rupees(limit),
        "available": to_rupees(available),
        "used": to_rupees(limit - available),
        "utilization": round((limit - available) / limit * 100, 1) if limit else None,
        "statement_day": card.get("statement_day"),
        "due_day": card.get("due_day"),
        "color": card.get("color"),
        "archived": bool(card.get("archived")),
        "month_spent": to_rupees(spend["total"]),
        "month_count": spend["count"],
    }


def adjust_card(conn: Connection, user_id: str, card_id: str, delta_paise: int) -> None:
    if not delta_paise:
        return
    conn.execute(
        update(cards)
        .where(cards.c.id == card_id, cards.c.user_id == user_id)
        .values(available_paise=cards.c.available_paise + delta_paise, updated_at=func.now())
    )


def _card_delta(old: dict | None, new: dict | None) -> dict[str, int]:
    """How much each card's available balance must change when `old` becomes `new`."""
    deltas: dict[str, int] = defaultdict(int)
    if old and old.get("card_id"):
        deltas[old["card_id"]] += int(old["amount_paise"])
    if new and new.get("card_id"):
        deltas[new["card_id"]] -= int(new["amount_paise"])
    return {k: v for k, v in deltas.items() if v}


# ======================= expenses =======================
def build_expense(user_id: str, expense_id: str, *, amount_paise: int, date: str | dt.date,
                  category: str, note: str = "", payment_method: str | None = None,
                  card_id: str | None = None, recurring_id: str | None = None,
                  loan_id: str | None = None) -> dict:
    return {
        "id": expense_id,
        "user_id": user_id,
        "amount_paise": amount_paise,
        "date": dt.date.fromisoformat(date) if isinstance(date, str) else date,
        "category": category,
        "note": note,
        "payment_method": payment_method,
        "card_id": card_id if payment_method == CREDIT_CARD else None,
        "recurring_id": recurring_id,
        "loan_id": loan_id,
    }


def insert_expense(conn: Connection, user_id: str, new: dict, *, only_if_new: bool = False) -> dict | None:
    """Insert an expense and take it off its credit card, in the request's transaction.

    With `only_if_new`, an existing id is left alone (returns None) - used for
    auto-generated expenses so they're created exactly once.
    """
    stmt = pg_insert(expenses).values(**new)
    if only_if_new:
        stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
    row = _one(conn.execute(stmt.returning(expenses)))
    if row is None:
        return None
    for cid, delta in _card_delta(None, row).items():
        adjust_card(conn, user_id, cid, delta)
    return row


def update_expense(conn: Connection, user_id: str, old: dict, new: dict) -> dict:
    values = {k: v for k, v in new.items() if k not in ("id", "user_id", "recurring_id", "loan_id")}
    row = _one(conn.execute(
        update(expenses).where(expenses.c.id == old["id"], expenses.c.user_id == user_id)
        .values(**values, updated_at=func.now()).returning(expenses)
    ))
    for cid, delta in _card_delta(old, row).items():
        adjust_card(conn, user_id, cid, delta)
    return row


def delete_expense(conn: Connection, user_id: str, old: dict) -> None:
    conn.execute(expenses.delete().where(expenses.c.id == old["id"], expenses.c.user_id == user_id))
    for cid, delta in _card_delta(old, None).items():
        adjust_card(conn, user_id, cid, delta)


def expense_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "amount": to_rupees(row["amount_paise"]),
        "date": _iso(row["date"]),
        "category": row["category"],
        "note": row.get("note") or "",
        "payment_method": row.get("payment_method"),
        "card_id": row.get("card_id"),
        "recurring_id": row.get("recurring_id"),
        "loan_id": row.get("loan_id"),
        "created_at": _iso(row.get("created_at")),
    }


def get_expense(conn: Connection, user_id: str, expense_id: str, *, lock: bool = False) -> dict:
    q = select(expenses).where(expenses.c.id == expense_id, expenses.c.user_id == user_id)
    if lock:
        q = q.with_for_update()
    row = _one(conn.execute(q))
    if not row:
        raise HTTPException(404, "Expense not found")
    return row


def query_months(conn: Connection, user_id: str, start_month: str, end_month: str) -> list[dict]:
    start = dt.date.fromisoformat(f"{start_month}-01")
    end = dt.date.fromisoformat(f"{end_month}-{days_in_month(end_month):02d}")
    return _rows(conn.execute(
        select(expenses)
        .where(expenses.c.user_id == user_id, expenses.c.date >= start, expenses.c.date <= end)
        .order_by(expenses.c.date.desc(), expenses.c.created_at.desc())
    ))


# ======================= budgets =======================
def load_budgets(conn: Connection, user_id: str) -> dict[str, int]:
    rows = conn.execute(select(budgets.c.category, budgets.c.amount_paise).where(budgets.c.user_id == user_id))
    return {r.category: int(r.amount_paise) for r in rows}


# ======================= aggregation =======================
def payment_key(item: dict) -> str:
    method = item.get("payment_method") or "Not set"
    if method == CREDIT_CARD and item.get("card_id"):
        return f"card:{item['card_id']}"
    return method


def aggregate(items: list[dict]) -> dict:
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_pay: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for it in items:
        p = int(it["amount_paise"])
        by_cat[it["category"]][0] += p
        by_cat[it["category"]][1] += 1
        k = payment_key(it)
        by_pay[k][0] += p
        by_pay[k][1] += 1
    return {"by_cat": by_cat, "by_pay": by_pay}


def payment_rows(by_pay: dict[str, list[int]], cards_by_id: dict[str, dict]) -> list[dict]:
    rows = []
    for key, (total, count) in by_pay.items():
        if key.startswith("card:"):
            cid = key[5:]
            card = cards_by_id.get(cid)
            rows.append({
                "key": key, "method": CREDIT_CARD, "card_id": cid,
                "label": card["name"] if card else "Removed card",
                "color": card.get("color") if card else None,
                "total": to_rupees(total), "count": count,
            })
        else:
            rows.append({"key": key, "method": key, "card_id": None, "label": key, "color": None,
                         "total": to_rupees(total), "count": count})
    rows.sort(key=lambda r: (-r["total"], r["label"]))
    return rows


# ======================= recurring =======================
def recurring_next_due(rec: dict, td: dt.date | None = None) -> str | None:
    if not rec.get("active", True):
        return None
    td = td or today()
    last = rec.get("last_generated_month")
    month = add_months(last, 1) if last else rec["start_month"]
    cur = td.strftime("%Y-%m")
    if month < cur:
        month = cur
    end = rec.get("end_month")
    if end and month > end:
        return None
    day = min(int(rec["day_of_month"]), days_in_month(month))
    return f"{month}-{day:02d}"


def recurring_out(rec: dict, td: dt.date | None = None) -> dict:
    return {
        "id": rec["id"],
        "amount": to_rupees(rec["amount_paise"]),
        "category": rec["category"],
        "note": rec.get("note") or "",
        "payment_method": rec.get("payment_method"),
        "card_id": rec.get("card_id"),
        "day_of_month": int(rec["day_of_month"]),
        "start_month": rec["start_month"],
        "end_month": rec.get("end_month"),
        "active": bool(rec.get("active", True)),
        "last_generated_month": rec.get("last_generated_month"),
        "next_due": recurring_next_due(rec, td),
    }


def list_recurring(conn: Connection, user_id: str, *, lock: bool = False) -> list[dict]:
    q = select(recurring).where(recurring.c.user_id == user_id).order_by(recurring.c.created_at)
    if lock:
        q = q.with_for_update()
    return _rows(conn.execute(q))


def _sync_recurring(conn: Connection, user_id: str, td: dt.date) -> int:
    cur = td.strftime("%Y-%m")
    created = 0
    # FOR UPDATE: two requests syncing at once can't both generate the same month
    for rec in list_recurring(conn, user_id, lock=True):
        if not rec.get("active", True):
            continue
        last_gen = rec.get("last_generated_month")
        first = add_months(last_gen, 1) if last_gen else rec["start_month"]
        last = min(cur, rec["end_month"]) if rec.get("end_month") else cur
        if first > last:
            continue
        done_upto = None
        for month in month_range(first, last)[-MAX_RANGE_MONTHS:]:
            day = min(int(rec["day_of_month"]), days_in_month(month))
            if month == cur and td.day < day:
                break
            item = build_expense(
                user_id, f"rec{rec['id']}{month.replace('-', '')}",
                amount_paise=int(rec["amount_paise"]),
                date=f"{month}-{day:02d}",
                category=rec["category"],
                note=rec.get("note") or "",
                payment_method=rec.get("payment_method"),
                card_id=rec.get("card_id"),
                recurring_id=rec["id"],
            )
            created += insert_expense(conn, user_id, item, only_if_new=True) is not None
            done_upto = month
        if done_upto:
            conn.execute(update(recurring).where(recurring.c.id == rec["id"])
                         .values(last_generated_month=done_upto))
    return created


# ======================= loans & borrowings =======================
def list_loans(conn: Connection, user_id: str, *, lock: bool = False) -> list[dict]:
    q = select(loans).where(loans.c.user_id == user_id).order_by(loans.c.created_at)
    if lock:
        q = q.with_for_update()
    return _rows(conn.execute(q))


def get_loan(conn: Connection, user_id: str, loan_id: str) -> dict:
    row = _one(conn.execute(select(loans).where(loans.c.id == loan_id, loans.c.user_id == user_id)))
    if not row:
        raise HTTPException(404, "Loan not found")
    return row


def repayments_for(conn: Connection, user_id: str, loan_ids: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if not loan_ids:
        return out
    rows = _rows(conn.execute(
        select(loan_repayments)
        .where(loan_repayments.c.user_id == user_id, loan_repayments.c.loan_id.in_(loan_ids))
        .order_by(loan_repayments.c.date, loan_repayments.c.created_at)
    ))
    for r in rows:
        out[r["loan_id"]].append(r)
    return out


def emi_dates(loan: dict) -> list[dt.date]:
    """First EMI on first_emi_date, then on emi_day of each following month."""
    first: dt.date = loan["first_emi_date"]
    first_month = first.strftime("%Y-%m")
    out = [first]
    for i in range(1, int(loan["emi_count"])):
        m = add_months(first_month, i)
        out.append(dt.date(int(m[:4]), int(m[5:]), min(int(loan["emi_day"]), days_in_month(m))))
    return out


def loan_out(loan: dict, repayments: list[dict], td: dt.date | None = None) -> dict:
    td = td or today()
    principal = int(loan["principal_paise"])
    extra_paid = sum(int(r["amount_paise"]) for r in repayments)
    out = {
        "id": loan["id"],
        "kind": loan["kind"],
        "lender": loan["lender"],
        "taken_by": loan.get("taken_by") or "",
        "principal": to_rupees(principal),
        "note": loan.get("note") or "",
        "taken_on": _iso(loan.get("taken_on")),
        "repayments": [
            {"id": r["id"], "amount": to_rupees(r["amount_paise"]), "date": _iso(r["date"]), "note": r.get("note") or ""}
            for r in repayments
        ],
        "interest_rate": None, "total_interest": None, "installment": None, "emi_day": None,
        "emi_count": None, "first_emi_date": None, "emi_adjustment": 0, "insurance": False,
        "log_emis_as_expenses": False, "payment_method": loan.get("payment_method"),
        "card_id": loan.get("card_id"),
        "emis_paid": None, "emis_due": None, "next_emi_date": None, "closure_date": None,
    }
    if loan["kind"] == "loan":
        count = int(loan["emi_count"])
        inst = int(loan["installment_paise"])
        if loan.get("total_interest_paise") is not None:
            interest = int(loan["total_interest_paise"])
        else:
            interest = max(0, inst * count - principal)
        dates = emi_dates(loan)
        scheduled = sum(1 for d in dates if d <= td)
        paid = max(0, min(count, scheduled + int(loan.get("emi_adjustment") or 0)))
        total_paid = inst * paid + extra_paid
        remaining = max(0, principal + interest - total_paid)
        upcoming = [d for d in dates if d > td]
        out.update({
            "interest_rate": float(loan["interest_rate"]) if loan.get("interest_rate") is not None else None,
            "total_interest": to_rupees(interest),
            "installment": to_rupees(inst),
            "emi_day": int(loan["emi_day"]),
            "emi_count": count,
            "first_emi_date": _iso(loan["first_emi_date"]),
            "emi_adjustment": int(loan.get("emi_adjustment") or 0),
            "insurance": bool(loan.get("insurance")),
            "log_emis_as_expenses": bool(loan.get("log_emis_as_expenses")),
            "emis_paid": paid,
            "emis_due": count - paid,
            "next_emi_date": upcoming[0].isoformat() if upcoming and paid < count and remaining else None,
            "closure_date": dates[-1].isoformat(),
            "total_payable": to_rupees(principal + interest),
            "total_paid": to_rupees(total_paid),
            "remaining": to_rupees(remaining),
            "monthly_outgo": to_rupees(inst) if remaining and paid < count else 0.0,
        })
    else:
        out.update({
            "total_payable": to_rupees(principal),
            "total_paid": to_rupees(extra_paid),
            "remaining": to_rupees(max(0, principal - extra_paid)),
            "monthly_outgo": 0.0,
        })
    out["status"] = "closed" if out["remaining"] <= 0 else "active"
    return out


def _sync_loan_emis(conn: Connection, user_id: str, td: dt.date) -> int:
    """For loans with `log_emis_as_expenses`, add each EMI to expenses on its date
    (only from the day the option was switched on, never back-filled)."""
    created = 0
    for loan in list_loans(conn, user_id, lock=True):
        if loan["kind"] != "loan" or not loan.get("log_emis_as_expenses"):
            continue
        start = loan.get("emi_log_from") or td
        last = loan.get("last_logged_emi")
        done = None
        for d in emi_dates(loan):
            if d < start or (last and d <= last):
                continue
            if d > td:
                break
            item = build_expense(
                user_id, f"emi{loan['id']}{d.strftime('%Y%m%d')}",
                amount_paise=int(loan["installment_paise"]),
                date=d,
                category="emi",
                note=f"{loan['lender']} EMI",
                payment_method=loan.get("payment_method"),
                card_id=loan.get("card_id"),
                loan_id=loan["id"],
            )
            created += insert_expense(conn, user_id, item, only_if_new=True) is not None
            done = d
        if done:
            conn.execute(update(loans).where(loans.c.id == loan["id"]).values(last_logged_emi=done))
    return created


# ======================= auto-generated expenses =======================
def sync_auto(conn: Connection, user_id: str, td: dt.date | None = None) -> int:
    """Add any recurring expenses / loan EMIs that have fallen due.

    Runs whenever the user's expenses are read, so there is no scheduler to pay for.
    Idempotent: generated expenses get deterministic ids, and the last-generated
    markers stop a deleted occurrence from being re-created.
    """
    td = td or today()
    return _sync_recurring(conn, user_id, td) + _sync_loan_emis(conn, user_id, td)


def card_month_spend(conn: Connection, user_id: str, month: str) -> dict[str, dict]:
    start = dt.date.fromisoformat(f"{month}-01")
    end = dt.date.fromisoformat(f"{month}-{days_in_month(month):02d}")
    rows = conn.execute(
        select(expenses.c.card_id, func.sum(expenses.c.amount_paise), func.count())
        .where(and_(expenses.c.user_id == user_id, expenses.c.payment_method == CREDIT_CARD,
                    expenses.c.card_id.is_not(None), expenses.c.date >= start, expenses.c.date <= end))
        .group_by(expenses.c.card_id)
    )
    return {cid: {"total": int(total), "count": int(n)} for cid, total, n in rows}

