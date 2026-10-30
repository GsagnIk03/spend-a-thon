from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, select

from ..constants import CATEGORY_COLORS
from ..db import budgets, categories, expenses, get_db, recurring
from ..schemas import CategoryIn
from ..security import current_user_id
from ..services import all_categories, custom_categories

router = APIRouter(prefix="/categories", tags=["categories"])

MAX_CUSTOM = 40


def _get(conn: Connection, user_id: str, cat_id: str) -> dict:
    row = conn.execute(select(categories).where(categories.c.id == cat_id, categories.c.user_id == user_id)).first()
    if not row:
        raise HTTPException(404, "Category not found (built-in categories can't be changed)")
    return dict(row._mapping)


def _check_name(conn: Connection, user_id: str, label: str, except_id: str | None = None) -> None:
    for c in all_categories(conn, user_id):
        if c["label"].lower() == label.lower() and c["id"] != except_id:
            raise HTTPException(409, f'You already have a category called "{c["label"]}"')


def _out(row: dict) -> dict:
    return {"id": row["id"], "label": row["label"], "emoji": row["emoji"], "color": row["color"], "custom": True}


@router.get("")
def list_categories(user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    return all_categories(conn, user_id)


@router.post("", status_code=201)
def create_category(body: CategoryIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    existing = custom_categories(conn, user_id)
    if len(existing) >= MAX_CUSTOM:
        raise HTTPException(422, f"You can have up to {MAX_CUSTOM} custom categories")
    _check_name(conn, user_id, body.label)
    row = {
        "id": f"c_{uuid4().hex[:8]}", "user_id": user_id, "label": body.label, "emoji": body.emoji,
        "color": body.color or CATEGORY_COLORS[len(existing) % len(CATEGORY_COLORS)],
    }
    conn.execute(categories.insert().values(**row))
    return _out(row)


@router.put("/{cat_id}")
def update_category(cat_id: str, body: CategoryIn, user_id: str = Depends(current_user_id),
                    conn: Connection = Depends(get_db)):
    old = _get(conn, user_id, cat_id)
    _check_name(conn, user_id, body.label, except_id=cat_id)
    values = {"label": body.label, "emoji": body.emoji, "color": body.color or old["color"]}
    conn.execute(categories.update().where(categories.c.id == cat_id, categories.c.user_id == user_id).values(**values))
    return _out({**old, **values})


@router.delete("/{cat_id}", status_code=204)
def delete_category(cat_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    """Expenses and recurring items in this category move to "Other"; its budget is removed."""
    _get(conn, user_id, cat_id)
    conn.execute(expenses.update().where(expenses.c.user_id == user_id, expenses.c.category == cat_id)
                 .values(category="other"))
    conn.execute(recurring.update().where(recurring.c.user_id == user_id, recurring.c.category == cat_id)
                 .values(category="other"))
    conn.execute(budgets.delete().where(budgets.c.user_id == user_id, budgets.c.category == cat_id))
    conn.execute(categories.delete().where(categories.c.id == cat_id, categories.c.user_id == user_id))
    return Response(status_code=204)
