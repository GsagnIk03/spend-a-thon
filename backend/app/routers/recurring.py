from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, func, select

from ..db import get_db, recurring
from ..schemas import RecurringIn, RecurringOut
from ..security import current_user_id
from ..services import check_card, check_category, list_recurring, recurring_out, sync_auto
from ..utils import to_paise

router = APIRouter(prefix="/recurring", tags=["recurring"])


def _values(body: RecurringIn) -> dict:
    return {
        "amount_paise": to_paise(body.amount),
        "category": body.category,
        "note": body.note,
        "payment_method": body.payment_method,
        "card_id": body.card_id,
        "day_of_month": body.day_of_month,
        "start_month": body.start_month,
        "end_month": body.end_month,
        "active": body.active,
    }


def _get(conn: Connection, user_id: str, rec_id: str) -> dict:
    row = conn.execute(select(recurring).where(recurring.c.id == rec_id, recurring.c.user_id == user_id)).first()
    if not row:
        raise HTTPException(404, "Recurring expense not found")
    return dict(row._mapping)


@router.get("", response_model=list[RecurringOut])
def list_all(user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    sync_auto(conn, user_id)
    recs = sorted(list_recurring(conn, user_id), key=lambda r: (int(r["day_of_month"]), r["created_at"]))
    return [recurring_out(r) for r in recs]


@router.post("", response_model=RecurringOut, status_code=201)
def create(body: RecurringIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    check_category(conn, user_id, body.category)
    check_card(conn, user_id, body.payment_method, body.card_id)
    rec_id = uuid4().hex[:12]
    conn.execute(recurring.insert().values(id=rec_id, user_id=user_id, **_values(body)))
    sync_auto(conn, user_id)
    return recurring_out(_get(conn, user_id, rec_id))


@router.put("/{rec_id}", response_model=RecurringOut)
def update(rec_id: str, body: RecurringIn, user_id: str = Depends(current_user_id),
           conn: Connection = Depends(get_db)):
    old = _get(conn, user_id, rec_id)
    if body.category != old["category"]:
        check_category(conn, user_id, body.category)
    check_card(conn, user_id, body.payment_method, body.card_id, allow_archived=old.get("card_id"))
    # Edits apply to future occurrences; already-added expenses stay as they are.
    conn.execute(recurring.update().where(recurring.c.id == rec_id, recurring.c.user_id == user_id)
                 .values(**_values(body), updated_at=func.now()))
    sync_auto(conn, user_id)
    return recurring_out(_get(conn, user_id, rec_id))


@router.delete("/{rec_id}", status_code=204)
def delete(rec_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    _get(conn, user_id, rec_id)
    conn.execute(recurring.delete().where(recurring.c.id == rec_id, recurring.c.user_id == user_id))
    return Response(status_code=204)
