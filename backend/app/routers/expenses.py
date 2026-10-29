from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection

from ..constants import MAX_RANGE_MONTHS
from ..db import get_db
from ..schemas import ExpenseIn, ExpenseOut
from ..security import current_user_id
from ..services import (
    build_expense, check_card, check_category, delete_expense, expense_out, get_expense,
    insert_expense, payment_key, query_months, sync_auto, update_expense,
)
from ..utils import month_range, require_month, to_paise

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseOut])
def list_expenses(month: str | None = None, start: str | None = None, end: str | None = None,
                  category: str | None = None, payment: str | None = None,
                  user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    """One month (`month`) or a range (`start`..`end`, YYYY-MM).

    `payment` filters by payment key: a method name ("Cash", "Google Pay") or "card:<id>".
    """
    if start or end:
        end = require_month(end, "end")
        start = require_month(start, "start") if start else end
        if start > end:
            raise HTTPException(422, "start must not be after end")
        if len(month_range(start, end)) > MAX_RANGE_MONTHS:
            raise HTTPException(422, f"at most {MAX_RANGE_MONTHS} months at a time")
    else:
        start = end = require_month(month)
    sync_auto(conn, user_id)
    items = query_months(conn, user_id, start, end)
    if category:
        items = [i for i in items if i["category"] == category]
    if payment:
        items = [i for i in items if payment_key(i) == payment]
    return [expense_out(i) for i in items]


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, user_id: str = Depends(current_user_id),
                   conn: Connection = Depends(get_db)):
    check_category(conn, user_id, body.category)
    check_card(conn, user_id, body.payment_method, body.card_id)
    item = build_expense(
        user_id, uuid4().hex,
        amount_paise=to_paise(body.amount),
        date=body.date,
        category=body.category,
        note=body.note,
        payment_method=body.payment_method,
        card_id=body.card_id,
    )
    return expense_out(insert_expense(conn, user_id, item))


@router.get("/{expense_id}", response_model=ExpenseOut)
def read_expense(expense_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    return expense_out(get_expense(conn, user_id, expense_id))


@router.put("/{expense_id}", response_model=ExpenseOut)
def edit_expense(expense_id: str, body: ExpenseIn, user_id: str = Depends(current_user_id),
                 conn: Connection = Depends(get_db)):
    old = get_expense(conn, user_id, expense_id, lock=True)
    if body.category != old["category"]:
        check_category(conn, user_id, body.category)
    check_card(conn, user_id, body.payment_method, body.card_id, allow_archived=old.get("card_id"))
    new = build_expense(
        user_id, expense_id,
        amount_paise=to_paise(body.amount),
        date=body.date,
        category=body.category,
        note=body.note,
        payment_method=body.payment_method,
        card_id=body.card_id,
    )
    return expense_out(update_expense(conn, user_id, old, new))


@router.delete("/{expense_id}", status_code=204)
def remove_expense(expense_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    old = get_expense(conn, user_id, expense_id, lock=True)
    delete_expense(conn, user_id, old)
    return Response(status_code=204)
