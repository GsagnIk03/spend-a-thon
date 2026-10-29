from uuid import uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response

from ..config import get_settings
from ..constants import MAX_RANGE_MONTHS, RECEIPT_MAX_BYTES, RECEIPT_TYPES
from ..db import get_s3, get_table
from ..schemas import ExpenseIn, ExpenseOut, ReceiptAttachIn, ReceiptUploadIn
from ..security import current_user_id
from ..services import (
    build_expense_item, check_card, check_category, expense_out, get_expense, payment_key,
    query_months, remove_expense, save_expense, sync_auto,
)
from ..utils import month_range, require_month, to_paise

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _bucket() -> str:
    bucket = get_settings().receipts_bucket
    if not bucket:
        raise HTTPException(503, "Receipt storage is not configured")
    return bucket


def _delete_receipt_object(key: str | None) -> None:
    if not key or not get_settings().receipts_bucket:
        return
    try:
        get_s3().delete_object(Bucket=get_settings().receipts_bucket, Key=key)
    except ClientError:
        pass


@router.get("", response_model=list[ExpenseOut])
def list_expenses(month: str | None = None, start: str | None = None, end: str | None = None,
                  category: str | None = None, payment: str | None = None,
                  user_id: str = Depends(current_user_id)):
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
    sync_auto(user_id)
    items = query_months(user_id, start, end)
    if category:
        items = [i for i in items if i["category"] == category]
    if payment:
        items = [i for i in items if payment_key(i) == payment]
    items.sort(key=lambda i: (i["date"], i.get("created_at", "")), reverse=True)
    return [expense_out(i) for i in items]


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseIn, user_id: str = Depends(current_user_id)):
    check_category(user_id, body.category)
    check_card(user_id, body.payment_method, body.card_id)
    item = build_expense_item(
        user_id, uuid4().hex,
        amount_paise=to_paise(body.amount),
        date=body.date.isoformat(),
        category=body.category,
        note=body.note,
        payment_method=body.payment_method,
        card_id=body.card_id,
    )
    save_expense(user_id, item)
    return expense_out(item)


@router.get("/{expense_id}", response_model=ExpenseOut)
def read_expense(expense_id: str, user_id: str = Depends(current_user_id)):
    return expense_out(get_expense(user_id, expense_id))


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: str, body: ExpenseIn, user_id: str = Depends(current_user_id)):
    old = get_expense(user_id, expense_id)
    if body.category != old["category"]:
        check_category(user_id, body.category)
    check_card(user_id, body.payment_method, body.card_id, allow_archived=old.get("card_id"))
    item = build_expense_item(
        user_id, expense_id,
        amount_paise=to_paise(body.amount),
        date=body.date.isoformat(),
        category=body.category,
        note=body.note,
        payment_method=body.payment_method,
        card_id=body.card_id,
        recurring_id=old.get("recurring_id"),
        loan_id=old.get("loan_id"),
        receipt_key=old.get("receipt_key"),
        created_at=old.get("created_at"),
    )
    save_expense(user_id, item, old)
    return expense_out(item)


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: str, user_id: str = Depends(current_user_id)):
    old = get_expense(user_id, expense_id)
    remove_expense(user_id, old)
    _delete_receipt_object(old.get("receipt_key"))
    return Response(status_code=204)


# ---------- receipts ----------
@router.post("/{expense_id}/receipt/upload-url")
def receipt_upload_url(expense_id: str, body: ReceiptUploadIn,
                       user_id: str = Depends(current_user_id)):
    get_expense(user_id, expense_id)
    ext = RECEIPT_TYPES[body.content_type]
    key = f"receipts/{user_id}/{expense_id}/{uuid4().hex}.{ext}"
    post = get_s3().generate_presigned_post(
        Bucket=_bucket(),
        Key=key,
        Fields={"Content-Type": body.content_type},
        Conditions=[
            {"Content-Type": body.content_type},
            ["content-length-range", 1, RECEIPT_MAX_BYTES],
        ],
        ExpiresIn=600,
    )
    return {"url": post["url"], "fields": post["fields"], "key": key}


@router.put("/{expense_id}/receipt", response_model=ExpenseOut)
def attach_receipt(expense_id: str, body: ReceiptAttachIn,
                   user_id: str = Depends(current_user_id)):
    item = get_expense(user_id, expense_id)
    if not body.key.startswith(f"receipts/{user_id}/{expense_id}/"):
        raise HTTPException(400, "Invalid receipt key")
    try:
        get_s3().head_object(Bucket=_bucket(), Key=body.key)
    except ClientError:
        raise HTTPException(400, "Receipt upload not found, please try again")
    old_key = item.get("receipt_key")
    get_table().update_item(
        Key={"PK": item["PK"], "SK": item["SK"]},
        UpdateExpression="SET receipt_key = :k",
        ExpressionAttributeValues={":k": body.key},
    )
    if old_key and old_key != body.key:
        _delete_receipt_object(old_key)
    item["receipt_key"] = body.key
    return expense_out(item)


@router.get("/{expense_id}/receipt")
def receipt_url(expense_id: str, user_id: str = Depends(current_user_id)):
    item = get_expense(user_id, expense_id)
    key = item.get("receipt_key")
    if not key:
        raise HTTPException(404, "No receipt attached")
    url = get_s3().generate_presigned_url(
        "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=600
    )
    return {"url": url}


@router.delete("/{expense_id}/receipt", response_model=ExpenseOut)
def remove_receipt(expense_id: str, user_id: str = Depends(current_user_id)):
    item = get_expense(user_id, expense_id)
    key = item.pop("receipt_key", None)
    if key:
        get_table().update_item(
            Key={"PK": item["PK"], "SK": item["SK"]}, UpdateExpression="REMOVE receipt_key"
        )
        _delete_receipt_object(key)
    return expense_out(item)
