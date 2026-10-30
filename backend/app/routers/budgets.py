from fastapi import APIRouter, Depends
from sqlalchemy import Connection, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import budgets, get_db
from ..schemas import BudgetsIn
from ..security import current_user_id
from ..services import check_category, load_budgets
from ..utils import to_paise, to_rupees

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _out(conn: Connection, user_id: str) -> dict:
    return {"budgets": {k: to_rupees(v) for k, v in load_budgets(conn, user_id).items()}}


@router.get("")
def get_budgets(user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    return _out(conn, user_id)


@router.put("")
def save_budgets(body: BudgetsIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    """Upsert budgets. A null or 0 amount removes that category's budget."""
    for category, amount in body.budgets.items():
        if not amount:
            conn.execute(budgets.delete().where(budgets.c.user_id == user_id, budgets.c.category == category))
            continue
        check_category(conn, user_id, category)
        stmt = pg_insert(budgets).values(user_id=user_id, category=category, amount_paise=to_paise(amount))
        conn.execute(stmt.on_conflict_do_update(
            index_elements=["user_id", "category"],
            set_={"amount_paise": stmt.excluded.amount_paise, "updated_at": func.now()},
        ))
    return _out(conn, user_id)
