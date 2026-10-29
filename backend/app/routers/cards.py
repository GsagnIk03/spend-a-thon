from uuid import uuid4

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response

from ..constants import CARD_COLORS, CREDIT_CARD
from ..db import get_table, query_all, user_pk
from ..schemas import CardBalanceIn, CardIn, CardPaymentIn
from ..security import current_user_id
from ..services import card_out, get_card, list_cards, query_months, sync_auto
from ..utils import current_month, now_iso, to_paise, to_rupees

router = APIRouter(prefix="/cards", tags=["credit cards"])


def _month_spend(user_id: str) -> dict[str, dict]:
    month = current_month()
    out: dict[str, dict] = {}
    for e in query_months(user_id, month, month):
        if e.get("payment_method") == CREDIT_CARD and e.get("card_id"):
            s = out.setdefault(e["card_id"], {"total": 0, "count": 0})
            s["total"] += int(e["amount_paise"])
            s["count"] += 1
    return out


@router.get("")
def list_all(include_archived: bool = False, user_id: str = Depends(current_user_id)):
    sync_auto(user_id)
    spend = _month_spend(user_id)
    cards = [c for c in list_cards(user_id) if include_archived or not c.get("archived")]
    return [card_out(c, spend) for c in cards]


@router.post("", status_code=201)
def create(body: CardIn, user_id: str = Depends(current_user_id)):
    existing = list_cards(user_id)
    card_id = uuid4().hex[:10]
    item = {
        "PK": user_pk(user_id), "SK": f"CARD#{card_id}", "type": "card",
        "id": card_id, "name": body.name, "bank": body.bank, "last4": body.last4,
        "limit_paise": to_paise(body.credit_limit),
        "available_paise": to_paise(body.available),
        "color": body.color or CARD_COLORS[len(existing) % len(CARD_COLORS)],
        "created_at": now_iso(),
    }
    if body.statement_day:
        item["statement_day"] = body.statement_day
    if body.due_day:
        item["due_day"] = body.due_day
    get_table().put_item(Item=item)
    return card_out(item)


@router.put("/{card_id}")
def update(card_id: str, body: CardIn, user_id: str = Depends(current_user_id)):
    """Edit details. `available` here overwrites the balance (use it to match your bank's app)."""
    old = get_card(user_id, card_id)
    fields = {
        "name": body.name, "bank": body.bank, "last4": body.last4,
        "limit_paise": to_paise(body.credit_limit),
        "available_paise": to_paise(body.available),
        "color": body.color or old.get("color"),
        "statement_day": body.statement_day, "due_day": body.due_day,
        "updated_at": now_iso(),
    }
    sets = {k: v for k, v in fields.items() if v is not None}
    removes = [k for k, v in fields.items() if v is None and k in old]
    expr = "SET " + ", ".join(f"#{k} = :{k}" for k in sets)
    if removes:
        expr += " REMOVE " + ", ".join(f"#{k}" for k in removes)
    resp = get_table().update_item(
        Key={"PK": old["PK"], "SK": old["SK"]},
        UpdateExpression=expr,
        ExpressionAttributeNames={f"#{k}": k for k in [*sets, *removes]},
        ExpressionAttributeValues={f":{k}": v for k, v in sets.items()},
        ReturnValues="ALL_NEW",
    )
    return card_out(resp["Attributes"])


@router.put("/{card_id}/balance")
def set_balance(card_id: str, body: CardBalanceIn, user_id: str = Depends(current_user_id)):
    card = get_card(user_id, card_id)
    resp = get_table().update_item(
        Key={"PK": card["PK"], "SK": card["SK"]},
        UpdateExpression="SET available_paise = :a, updated_at = :u",
        ExpressionAttributeValues={":a": to_paise(body.available), ":u": now_iso()},
        ReturnValues="ALL_NEW",
    )
    return card_out(resp["Attributes"])


@router.delete("/{card_id}", status_code=204)
def archive(card_id: str, user_id: str = Depends(current_user_id)):
    """Cards are archived, not deleted, so past expenses still show which card they were on."""
    card = get_card(user_id, card_id)
    get_table().update_item(
        Key={"PK": card["PK"], "SK": card["SK"]},
        UpdateExpression="SET archived = :t",
        ExpressionAttributeValues={":t": True},
    )
    return Response(status_code=204)


@router.post("/{card_id}/restore")
def restore(card_id: str, user_id: str = Depends(current_user_id)):
    card = get_card(user_id, card_id)
    get_table().update_item(Key={"PK": card["PK"], "SK": card["SK"]}, UpdateExpression="REMOVE archived")
    card.pop("archived", None)
    return card_out(card)


# ---------- bill payments & refunds (credit the card) ----------
def _payment_out(p: dict) -> dict:
    return {"id": p["id"], "card_id": p["card_id"], "amount": to_rupees(p["amount_paise"]),
            "date": p["date"], "note": p.get("note", ""), "kind": p.get("kind", "payment")}


@router.get("/{card_id}/payments")
def list_payments(card_id: str, user_id: str = Depends(current_user_id)):
    get_card(user_id, card_id)
    items = query_all(KeyConditionExpression=Key("PK").eq(user_pk(user_id)) & Key("SK").begins_with("CPAY#"))
    items = [p for p in items if p["card_id"] == card_id]
    items.sort(key=lambda p: (p["date"], p.get("created_at", "")), reverse=True)
    return [_payment_out(p) for p in items]


@router.post("/{card_id}/payments", status_code=201)
def add_payment(card_id: str, body: CardPaymentIn, user_id: str = Depends(current_user_id)):
    """Paying the bill (or a refund) frees up limit: available balance goes up."""
    get_card(user_id, card_id)
    table = get_table()
    pid = uuid4().hex[:12]
    amount = to_paise(body.amount)
    item = {
        "PK": user_pk(user_id), "SK": f"CPAY#{pid}", "type": "card_payment",
        "id": pid, "card_id": card_id, "amount_paise": amount, "date": body.date.isoformat(),
        "note": body.note.strip(), "kind": body.kind, "created_at": now_iso(),
    }
    table.meta.client.transact_write_items(TransactItems=[
        {"Put": {"TableName": table.name, "Item": item}},
        {"Update": {
            "TableName": table.name,
            "Key": {"PK": user_pk(user_id), "SK": f"CARD#{card_id}"},
            "UpdateExpression": "ADD available_paise :d",
            "ExpressionAttributeValues": {":d": amount},
        }},
    ])
    return {"payment": _payment_out(item), "card": card_out(get_card(user_id, card_id))}


@router.delete("/{card_id}/payments/{payment_id}")
def delete_payment(card_id: str, payment_id: str, user_id: str = Depends(current_user_id)):
    table = get_table()
    p = table.get_item(Key={"PK": user_pk(user_id), "SK": f"CPAY#{payment_id}"}).get("Item")
    if not p or p["card_id"] != card_id:
        raise HTTPException(404, "Payment not found")
    try:
        table.meta.client.transact_write_items(TransactItems=[
            {"Delete": {"TableName": table.name, "Key": {"PK": p["PK"], "SK": p["SK"]},
                        "ConditionExpression": "attribute_exists(PK)"}},
            {"Update": {
                "TableName": table.name,
                "Key": {"PK": user_pk(user_id), "SK": f"CARD#{card_id}"},
                "UpdateExpression": "ADD available_paise :d",
                "ExpressionAttributeValues": {":d": -int(p["amount_paise"])},
            }},
        ])
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            raise HTTPException(404, "Payment not found")
        raise
    return card_out(get_card(user_id, card_id))
