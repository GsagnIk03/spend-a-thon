from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, func, select

from ..constants import CARD_COLORS
from ..db import card_payments, cards, get_db
from ..schemas import CardBalanceIn, CardIn, CardPaymentIn
from ..security import current_user_id
from ..services import adjust_card, card_month_spend, card_out, get_card, list_cards, sync_auto
from ..utils import current_month, to_paise, to_rupees

router = APIRouter(prefix="/cards", tags=["credit cards"])


def _where(user_id: str, card_id: str):
    return (cards.c.id == card_id) & (cards.c.user_id == user_id)


@router.get("")
def list_all(include_archived: bool = False, user_id: str = Depends(current_user_id),
             conn: Connection = Depends(get_db)):
    sync_auto(conn, user_id)
    spend = card_month_spend(conn, user_id, current_month())
    return [card_out(c, spend) for c in list_cards(conn, user_id) if include_archived or not c["archived"]]


@router.post("", status_code=201)
def create(body: CardIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    existing = list_cards(conn, user_id)
    row = conn.execute(cards.insert().values(
        id=uuid4().hex[:10], user_id=user_id, name=body.name, bank=body.bank, last4=body.last4,
        limit_paise=to_paise(body.credit_limit), available_paise=to_paise(body.available),
        statement_day=body.statement_day, due_day=body.due_day,
        color=body.color or CARD_COLORS[len(existing) % len(CARD_COLORS)],
    ).returning(cards)).first()
    return card_out(dict(row._mapping))


@router.put("/{card_id}")
def update(card_id: str, body: CardIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    """Edit details. `available` here overwrites the balance (use it to match your bank's app)."""
    old = get_card(conn, user_id, card_id)
    row = conn.execute(cards.update().where(_where(user_id, card_id)).values(
        name=body.name, bank=body.bank, last4=body.last4,
        limit_paise=to_paise(body.credit_limit), available_paise=to_paise(body.available),
        statement_day=body.statement_day, due_day=body.due_day,
        color=body.color or old["color"], updated_at=func.now(),
    ).returning(cards)).first()
    return card_out(dict(row._mapping))


@router.put("/{card_id}/balance")
def set_balance(card_id: str, body: CardBalanceIn, user_id: str = Depends(current_user_id),
                conn: Connection = Depends(get_db)):
    get_card(conn, user_id, card_id)
    row = conn.execute(cards.update().where(_where(user_id, card_id))
                       .values(available_paise=to_paise(body.available), updated_at=func.now())
                       .returning(cards)).first()
    return card_out(dict(row._mapping))


@router.delete("/{card_id}", status_code=204)
def archive(card_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    """Cards are archived, not deleted, so past expenses still show which card they were on."""
    get_card(conn, user_id, card_id)
    conn.execute(cards.update().where(_where(user_id, card_id)).values(archived=True))
    return Response(status_code=204)


@router.post("/{card_id}/restore")
def restore(card_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    get_card(conn, user_id, card_id)
    row = conn.execute(cards.update().where(_where(user_id, card_id)).values(archived=False)
                       .returning(cards)).first()
    return card_out(dict(row._mapping))


# ---------- bill payments & refunds (credit the card) ----------
def _payment_out(p: dict) -> dict:
    return {"id": p["id"], "card_id": p["card_id"], "amount": to_rupees(p["amount_paise"]),
            "date": p["date"].isoformat(), "note": p.get("note") or "", "kind": p.get("kind") or "payment"}


@router.get("/{card_id}/payments")
def list_payments(card_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    get_card(conn, user_id, card_id)
    rows = conn.execute(
        select(card_payments)
        .where(card_payments.c.user_id == user_id, card_payments.c.card_id == card_id)
        .order_by(card_payments.c.date.desc(), card_payments.c.created_at.desc())
    )
    return [_payment_out(dict(r._mapping)) for r in rows]


@router.post("/{card_id}/payments", status_code=201)
def add_payment(card_id: str, body: CardPaymentIn, user_id: str = Depends(current_user_id),
                conn: Connection = Depends(get_db)):
    """Paying the bill (or a refund) frees up limit: available balance goes up."""
    get_card(conn, user_id, card_id)
    amount = to_paise(body.amount)
    row = conn.execute(card_payments.insert().values(
        id=uuid4().hex[:12], user_id=user_id, card_id=card_id, amount_paise=amount,
        date=body.date, note=body.note.strip(), kind=body.kind,
    ).returning(card_payments)).first()
    adjust_card(conn, user_id, card_id, amount)
    return {"payment": _payment_out(dict(row._mapping)), "card": card_out(get_card(conn, user_id, card_id))}


@router.delete("/{card_id}/payments/{payment_id}")
def delete_payment(card_id: str, payment_id: str, user_id: str = Depends(current_user_id),
                   conn: Connection = Depends(get_db)):
    row = conn.execute(
        card_payments.delete()
        .where(card_payments.c.id == payment_id, card_payments.c.user_id == user_id,
               card_payments.c.card_id == card_id)
        .returning(card_payments.c.amount_paise)
    ).first()
    if not row:
        raise HTTPException(404, "Payment not found")
    adjust_card(conn, user_id, card_id, -int(row.amount_paise))
    return card_out(get_card(conn, user_id, card_id))
