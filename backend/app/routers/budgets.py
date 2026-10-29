from fastapi import APIRouter, Depends

from ..db import get_table, user_pk
from ..schemas import BudgetsIn
from ..security import current_user_id
from ..services import check_category, load_budgets
from ..utils import now_iso, to_paise, to_rupees

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _out(user_id: str) -> dict:
    return {"budgets": {k: to_rupees(v) for k, v in load_budgets(user_id).items()}}


@router.get("")
def get_budgets(user_id: str = Depends(current_user_id)):
    return _out(user_id)


@router.put("")
def save_budgets(body: BudgetsIn, user_id: str = Depends(current_user_id)):
    """Upsert budgets. A null or 0 amount removes that category's budget."""
    for category, amount in body.budgets.items():
        if amount:
            check_category(user_id, category)
    with get_table().batch_writer() as batch:
        for category, amount in body.budgets.items():
            key = {"PK": user_pk(user_id), "SK": f"BUDGET#{category}"}
            if amount is None or amount == 0:
                batch.delete_item(Key=key)
            else:
                batch.put_item(Item={
                    **key,
                    "type": "budget",
                    "category": category,
                    "amount_paise": to_paise(amount),
                    "updated_at": now_iso(),
                })
    return _out(user_id)
