from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response

from ..constants import CATEGORY_COLORS
from ..db import get_table, user_pk
from ..schemas import CategoryIn
from ..security import current_user_id
from ..services import all_categories, custom_categories, expenses_with_category, list_recurring
from ..utils import now_iso

router = APIRouter(prefix="/categories", tags=["categories"])

MAX_CUSTOM = 40


def _get(user_id: str, cat_id: str) -> dict:
    item = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"CAT#{cat_id}"}).get("Item")
    if not item:
        raise HTTPException(404, "Category not found (built-in categories can't be changed)")
    return item


def _check_name(user_id: str, label: str, except_id: str | None = None) -> None:
    for c in all_categories(user_id):
        if c["label"].lower() == label.lower() and c["id"] != except_id:
            raise HTTPException(409, f'You already have a category called "{c["label"]}"')


@router.get("")
def list_categories(user_id: str = Depends(current_user_id)):
    return all_categories(user_id)


@router.post("", status_code=201)
def create_category(body: CategoryIn, user_id: str = Depends(current_user_id)):
    existing = custom_categories(user_id)
    if len(existing) >= MAX_CUSTOM:
        raise HTTPException(422, f"You can have up to {MAX_CUSTOM} custom categories")
    _check_name(user_id, body.label)
    cat_id = f"c_{uuid4().hex[:8]}"
    color = body.color or CATEGORY_COLORS[len(existing) % len(CATEGORY_COLORS)]
    item = {
        "PK": user_pk(user_id), "SK": f"CAT#{cat_id}", "type": "category",
        "id": cat_id, "label": body.label, "emoji": body.emoji, "color": color,
        "created_at": now_iso(),
    }
    get_table().put_item(Item=item)
    return {"id": cat_id, "label": body.label, "emoji": body.emoji, "color": color, "custom": True}


@router.put("/{cat_id}")
def update_category(cat_id: str, body: CategoryIn, user_id: str = Depends(current_user_id)):
    old = _get(user_id, cat_id)
    _check_name(user_id, body.label, except_id=cat_id)
    old.update({"label": body.label, "emoji": body.emoji, "color": body.color or old["color"],
                "updated_at": now_iso()})
    get_table().put_item(Item=old)
    return {"id": cat_id, "label": old["label"], "emoji": old["emoji"], "color": old["color"], "custom": True}


@router.delete("/{cat_id}", status_code=204)
def delete_category(cat_id: str, user_id: str = Depends(current_user_id)):
    """Expenses and recurring items in this category move to "Other"; its budget is removed."""
    _get(user_id, cat_id)
    table = get_table()
    with table.batch_writer() as batch:
        for exp in expenses_with_category(user_id, cat_id):
            batch.put_item(Item={**exp, "category": "other", "updated_at": now_iso()})
        for rec in list_recurring(user_id):
            if rec["category"] == cat_id:
                batch.put_item(Item={**rec, "category": "other", "updated_at": now_iso()})
        batch.delete_item(Key={"PK": user_pk(user_id), "SK": f"BUDGET#{cat_id}"})
        batch.delete_item(Key={"PK": user_pk(user_id), "SK": f"CAT#{cat_id}"})
    return Response(status_code=204)
