from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response

from ..db import get_table, user_pk
from ..schemas import RecurringIn, RecurringOut
from ..security import current_user_id
from ..services import check_card, check_category, list_recurring, recurring_out, sync_auto
from ..utils import now_iso, to_paise

router = APIRouter(prefix="/recurring", tags=["recurring"])


def _item(user_id: str, rec_id: str, body: RecurringIn, *, last_generated: str | None,
          created_at: str | None) -> dict:
    item = {
        "PK": user_pk(user_id),
        "SK": f"REC#{rec_id}",
        "type": "recurring",
        "id": rec_id,
        "amount_paise": to_paise(body.amount),
        "category": body.category,
        "note": body.note,
        "day_of_month": body.day_of_month,
        "start_month": body.start_month,
        "active": body.active,
        "created_at": created_at or now_iso(),
        "updated_at": now_iso(),
    }
    if body.payment_method:
        item["payment_method"] = body.payment_method
    if body.card_id:
        item["card_id"] = body.card_id
    if body.end_month:
        item["end_month"] = body.end_month
    if last_generated:
        item["last_generated_month"] = last_generated
    return item


def _get(user_id: str, rec_id: str) -> dict:
    item = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"REC#{rec_id}"}).get("Item")
    if not item:
        raise HTTPException(404, "Recurring expense not found")
    return item


@router.get("", response_model=list[RecurringOut])
def list_all(user_id: str = Depends(current_user_id)):
    sync_auto(user_id)
    recs = sorted(list_recurring(user_id), key=lambda r: (int(r["day_of_month"]), r["created_at"]))
    return [recurring_out(r) for r in recs]


@router.post("", response_model=RecurringOut, status_code=201)
def create(body: RecurringIn, user_id: str = Depends(current_user_id)):
    check_category(user_id, body.category)
    check_card(user_id, body.payment_method, body.card_id)
    rec_id = uuid4().hex[:12]
    get_table().put_item(Item=_item(user_id, rec_id, body, last_generated=None, created_at=None))
    sync_auto(user_id)
    return recurring_out(_get(user_id, rec_id))


@router.put("/{rec_id}", response_model=RecurringOut)
def update(rec_id: str, body: RecurringIn, user_id: str = Depends(current_user_id)):
    old = _get(user_id, rec_id)
    if body.category != old["category"]:
        check_category(user_id, body.category)
    check_card(user_id, body.payment_method, body.card_id, allow_archived=old.get("card_id"))
    # Edits apply to future occurrences; already-added expenses stay as they are.
    get_table().put_item(Item=_item(
        user_id, rec_id, body,
        last_generated=old.get("last_generated_month"),
        created_at=old.get("created_at"),
    ))
    sync_auto(user_id)
    return recurring_out(_get(user_id, rec_id))


@router.delete("/{rec_id}", status_code=204)
def delete(rec_id: str, user_id: str = Depends(current_user_id)):
    _get(user_id, rec_id)
    get_table().delete_item(Key={"PK": user_pk(user_id), "SK": f"REC#{rec_id}"})
    return Response(status_code=204)
