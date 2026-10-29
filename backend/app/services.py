"""Data-access helpers shared by the routers.

Single-table layout (all of a user's data lives under PK = USER#<id>):
  USER#<id>   PROFILE              -> profile
  EMAIL#<em>  EMAIL                -> email -> user lookup (+ password hash)
  USER#<id>   EXP#<expenseId>      -> expense   (date_sk = <YYYY-MM-DD>#<id> on LSI "ByDate")
  USER#<id>   BUDGET#<category>    -> monthly budget
  USER#<id>   REC#<recurringId>    -> recurring expense template
  USER#<id>   CAT#<categoryId>     -> custom category
  USER#<id>   CARD#<cardId>        -> credit card (available_paise is kept up to date atomically)
  USER#<id>   CPAY#<paymentId>     -> credit card bill payment / refund
  USER#<id>   LOAN#<loanId>        -> loan (EMI) or borrowing, with its repayments
"""
import datetime as dt
import logging
from collections import defaultdict

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from fastapi import HTTPException

from .constants import CATEGORIES, CATEGORY_IDS, CREDIT_CARD, MAX_RANGE_MONTHS
from .db import get_table, query_all, user_pk
from .utils import add_months, days_in_month, month_range, now_iso, to_rupees, today

log = logging.getLogger(__name__)


def _items(user_id: str, prefix: str) -> list[dict]:
    return query_all(
        KeyConditionExpression=Key("PK").eq(user_pk(user_id)) & Key("SK").begins_with(prefix)
    )


def _cancel_reasons(e: ClientError) -> list[str]:
    return [r.get("Code", "") for r in e.response.get("CancellationReasons", [])]


# ======================= categories =======================
def custom_categories(user_id: str) -> list[dict]:
    items = sorted(_items(user_id, "CAT#"), key=lambda i: i.get("created_at", ""))
    return [
        {"id": i["id"], "label": i["label"], "emoji": i["emoji"], "color": i["color"], "custom": True}
        for i in items
    ]


def all_categories(user_id: str) -> list[dict]:
    defaults = [{**c, "custom": False} for c in CATEGORIES]
    custom = custom_categories(user_id)
    # keep "Other" last
    return defaults[:-1] + custom + defaults[-1:]


def category_labels(user_id: str) -> dict[str, str]:
    return {c["id"]: c["label"] for c in all_categories(user_id)}


def check_category(user_id: str, category: str) -> None:
    if category in CATEGORY_IDS:
        return
    if category.startswith("c_"):
        got = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"CAT#{category}"}).get("Item")
        if got:
            return
    raise HTTPException(422, "unknown category")


# ======================= credit cards =======================
def get_card(user_id: str, card_id: str) -> dict:
    item = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"CARD#{card_id}"}).get("Item")
    if not item:
        raise HTTPException(404, "Card not found")
    return item


def list_cards(user_id: str) -> list[dict]:
    return sorted(_items(user_id, "CARD#"), key=lambda c: c.get("created_at", ""))


def check_card(user_id: str, payment_method: str | None, card_id: str | None,
               allow_archived: str | None = None) -> None:
    """A credit-card payment may name one of the user's (active) cards."""
    if payment_method != CREDIT_CARD or not card_id:
        return
    item = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"CARD#{card_id}"}).get("Item")
    if not item:
        raise HTTPException(422, "unknown credit card")
    if item.get("archived") and card_id != allow_archived:
        raise HTTPException(422, "that card has been removed")


def card_out(card: dict, month_spend: dict | None = None) -> dict:
    limit = int(card["limit_paise"])
    available = int(card["available_paise"])
    spend = (month_spend or {}).get(card["id"], {"total": 0, "count": 0})
    return {
        "id": card["id"],
        "name": card["name"],
        "bank": card.get("bank", ""),
        "last4": card.get("last4", ""),
        "credit_limit": to_rupees(limit),
        "available": to_rupees(available),
        "used": to_rupees(limit - available),
        "utilization": round((limit - available) / limit * 100, 1) if limit else None,
        "statement_day": card.get("statement_day"),
        "due_day": card.get("due_day"),
        "color": card.get("color"),
        "archived": bool(card.get("archived")),
        "month_spent": to_rupees(spend["total"]),
        "month_count": spend["count"],
    }


def _card_delta(old: dict | None, new: dict | None) -> dict[str, int]:
    """How much each card's available balance must change when `old` becomes `new`."""
    deltas: dict[str, int] = defaultdict(int)
    if old and old.get("card_id"):
        deltas[old["card_id"]] += int(old["amount_paise"])
    if new and new.get("card_id"):
        deltas[new["card_id"]] -= int(new["amount_paise"])
    return {k: v for k, v in deltas.items() if v}


def _card_updates(table_name: str, user_id: str, deltas: dict[str, int]) -> list[dict]:
    return [
        {
            "Update": {
                "TableName": table_name,
                "Key": {"PK": user_pk(user_id), "SK": f"CARD#{cid}"},
                "UpdateExpression": "ADD available_paise :d",
                "ConditionExpression": "attribute_exists(PK)",
                "ExpressionAttributeValues": {":d": delta},
            }
        }
        for cid, delta in deltas.items()
    ]


# ======================= expenses =======================
def build_expense_item(user_id: str, expense_id: str, *, amount_paise: int, date: str,
                       category: str, note: str = "", payment_method: str | None = None,
                       card_id: str | None = None, recurring_id: str | None = None,
                       loan_id: str | None = None, receipt_key: str | None = None,
                       created_at: str | None = None) -> dict:
    item = {
        "PK": user_pk(user_id),
        "SK": f"EXP#{expense_id}",
        "date_sk": f"{date}#{expense_id}",
        "type": "expense",
        "id": expense_id,
        "amount_paise": amount_paise,
        "date": date,
        "category": category,
        "note": note,
        "created_at": created_at or now_iso(),
        "updated_at": now_iso(),
    }
    optional = {
        "payment_method": payment_method,
        "card_id": card_id if payment_method == CREDIT_CARD else None,
        "recurring_id": recurring_id,
        "loan_id": loan_id,
        "receipt_key": receipt_key,
    }
    item.update({k: v for k, v in optional.items() if v})
    return item


def save_expense(user_id: str, new: dict, old: dict | None = None, *, only_if_new: bool = False) -> bool:
    """Write an expense and move the money on any credit card(s) in one transaction.

    Returns False if `only_if_new` and the expense already existed.
    """
    table = get_table()
    put = {"TableName": table.name, "Item": new}
    if only_if_new:
        put["ConditionExpression"] = "attribute_not_exists(PK)"
    tx = [{"Put": put}] + _card_updates(table.name, user_id, _card_delta(old, new))
    try:
        table.meta.client.transact_write_items(TransactItems=tx)
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            reasons = _cancel_reasons(e)
            if only_if_new and reasons and reasons[0] == "ConditionalCheckFailed":
                return False
            if "ConditionalCheckFailed" in reasons[1:]:
                raise HTTPException(422, "unknown credit card")
        raise
    return True


def remove_expense(user_id: str, old: dict) -> None:
    table = get_table()
    tx = [{
        "Delete": {
            "TableName": table.name,
            "Key": {"PK": old["PK"], "SK": old["SK"]},
            "ConditionExpression": "attribute_exists(PK)",
        }
    }] + _card_updates(table.name, user_id, _card_delta(old, None))
    try:
        table.meta.client.transact_write_items(TransactItems=tx)
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            raise HTTPException(404, "Expense not found")
        raise


def expense_out(item: dict) -> dict:
    return {
        "id": item["id"],
        "amount": to_rupees(item["amount_paise"]),
        "date": item["date"],
        "category": item["category"],
        "note": item.get("note", ""),
        "payment_method": item.get("payment_method"),
        "card_id": item.get("card_id"),
        "has_receipt": bool(item.get("receipt_key")),
        "recurring_id": item.get("recurring_id"),
        "loan_id": item.get("loan_id"),
        "created_at": item.get("created_at"),
    }


def get_expense(user_id: str, expense_id: str) -> dict:
    item = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"EXP#{expense_id}"}).get("Item")
    if not item:
        raise HTTPException(404, "Expense not found")
    return item


def query_expenses(user_id: str, start_date: str, end_date: str) -> list[dict]:
    """All of a user's expenses with start_date <= date <= end_date (YYYY-MM-DD, inclusive)."""
    return query_all(
        IndexName="ByDate",
        KeyConditionExpression=Key("PK").eq(user_pk(user_id))
        & Key("date_sk").between(start_date, f"{end_date}#~"),
    )


def query_months(user_id: str, start_month: str, end_month: str) -> list[dict]:
    return query_expenses(user_id, f"{start_month}-01", f"{end_month}-31")


def expenses_with_category(user_id: str, category: str) -> list[dict]:
    return query_all(
        KeyConditionExpression=Key("PK").eq(user_pk(user_id)) & Key("SK").begins_with("EXP#"),
        FilterExpression=Attr("category").eq(category),
    )


# ======================= budgets =======================
def load_budgets(user_id: str) -> dict[str, int]:
    return {i["category"]: int(i["amount_paise"]) for i in _items(user_id, "BUDGET#")}


# ======================= aggregation =======================
def payment_key(item: dict) -> str:
    method = item.get("payment_method") or "Not set"
    if method == CREDIT_CARD and item.get("card_id"):
        return f"card:{item['card_id']}"
    return method


def aggregate(items: list[dict]) -> dict:
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_pay: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for it in items:
        p = int(it["amount_paise"])
        by_cat[it["category"]][0] += p
        by_cat[it["category"]][1] += 1
        k = payment_key(it)
        by_pay[k][0] += p
        by_pay[k][1] += 1
    return {"by_cat": by_cat, "by_pay": by_pay}


def payment_rows(by_pay: dict[str, list[int]], cards: dict[str, dict]) -> list[dict]:
    rows = []
    for key, (total, count) in by_pay.items():
        if key.startswith("card:"):
            cid = key[5:]
            card = cards.get(cid)
            rows.append({
                "key": key, "method": CREDIT_CARD, "card_id": cid,
                "label": card["name"] if card else "Removed card",
                "color": card.get("color") if card else None,
                "total": to_rupees(total), "count": count,
            })
        else:
            rows.append({"key": key, "method": key, "card_id": None, "label": key, "color": None,
                         "total": to_rupees(total), "count": count})
    rows.sort(key=lambda r: (-r["total"], r["label"]))
    return rows


# ======================= recurring =======================
def recurring_next_due(rec: dict, td: dt.date | None = None) -> str | None:
    if not rec.get("active", True):
        return None
    td = td or today()
    last = rec.get("last_generated_month")
    month = add_months(last, 1) if last else rec["start_month"]
    cur = td.strftime("%Y-%m")
    if month < cur:
        month = cur
    end = rec.get("end_month")
    if end and month > end:
        return None
    day = min(int(rec["day_of_month"]), days_in_month(month))
    return f"{month}-{day:02d}"


def recurring_out(rec: dict, td: dt.date | None = None) -> dict:
    return {
        "id": rec["id"],
        "amount": to_rupees(rec["amount_paise"]),
        "category": rec["category"],
        "note": rec.get("note", ""),
        "payment_method": rec.get("payment_method"),
        "card_id": rec.get("card_id"),
        "day_of_month": int(rec["day_of_month"]),
        "start_month": rec["start_month"],
        "end_month": rec.get("end_month"),
        "active": bool(rec.get("active", True)),
        "last_generated_month": rec.get("last_generated_month"),
        "next_due": recurring_next_due(rec, td),
    }


def list_recurring(user_id: str) -> list[dict]:
    return _items(user_id, "REC#")


def _sync_recurring(user_id: str, td: dt.date) -> int:
    cur = td.strftime("%Y-%m")
    table = get_table()
    created = 0
    for rec in list_recurring(user_id):
        if not rec.get("active", True):
            continue
        last_gen = rec.get("last_generated_month")
        first = add_months(last_gen, 1) if last_gen else rec["start_month"]
        last = min(cur, rec["end_month"]) if rec.get("end_month") else cur
        if first > last:
            continue
        done_upto = None
        for month in month_range(first, last)[-MAX_RANGE_MONTHS:]:
            day = min(int(rec["day_of_month"]), days_in_month(month))
            if month == cur and td.day < day:
                break
            item = build_expense_item(
                user_id, f"rec{rec['id']}{month.replace('-', '')}",
                amount_paise=int(rec["amount_paise"]),
                date=f"{month}-{day:02d}",
                category=rec["category"],
                note=rec.get("note", ""),
                payment_method=rec.get("payment_method"),
                card_id=rec.get("card_id"),
                recurring_id=rec["id"],
            )
            created += save_expense(user_id, item, only_if_new=True)
            done_upto = month
        if done_upto:
            _mark(table, rec, "last_generated_month", done_upto)
    return created


def _mark(table, item: dict, field: str, value: str) -> None:
    try:
        table.update_item(
            Key={"PK": item["PK"], "SK": item["SK"]},
            UpdateExpression=f"SET {field} = :v",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeValues={":v": value},
        )
    except ClientError as e:  # deleted concurrently - fine
        log.warning("could not update %s: %s", item["SK"], e)


# ======================= loans & borrowings =======================
def list_loans(user_id: str) -> list[dict]:
    return _items(user_id, "LOAN#")


def get_loan(user_id: str, loan_id: str) -> dict:
    item = get_table().get_item(Key={"PK": user_pk(user_id), "SK": f"LOAN#{loan_id}"}).get("Item")
    if not item:
        raise HTTPException(404, "Loan not found")
    return item


def emi_dates(loan: dict) -> list[dt.date]:
    """First EMI on first_emi_date, then on emi_day of each following month."""
    first = dt.date.fromisoformat(loan["first_emi_date"])
    first_month = first.strftime("%Y-%m")
    out = [first]
    for i in range(1, int(loan["emi_count"])):
        m = add_months(first_month, i)
        out.append(dt.date(int(m[:4]), int(m[5:]), min(int(loan["emi_day"]), days_in_month(m))))
    return out


def loan_out(loan: dict, td: dt.date | None = None) -> dict:
    td = td or today()
    principal = int(loan["principal_paise"])
    repayments = sorted(loan.get("repayments", []), key=lambda r: r["date"])
    extra_paid = sum(int(r["amount_paise"]) for r in repayments)
    out = {
        "id": loan["id"],
        "kind": loan["kind"],
        "lender": loan["lender"],
        "taken_by": loan.get("taken_by", ""),
        "principal": to_rupees(principal),
        "note": loan.get("note", ""),
        "taken_on": loan.get("taken_on"),
        "repayments": [
            {"id": r["id"], "amount": to_rupees(r["amount_paise"]), "date": r["date"], "note": r.get("note", "")}
            for r in repayments
        ],
        "interest_rate": None, "total_interest": None, "installment": None, "emi_day": None,
        "emi_count": None, "first_emi_date": None, "emi_adjustment": 0, "insurance": False,
        "log_emis_as_expenses": False, "payment_method": loan.get("payment_method"),
        "card_id": loan.get("card_id"),
        "emis_paid": None, "emis_due": None, "next_emi_date": None, "closure_date": None,
    }
    if loan["kind"] == "loan":
        count = int(loan["emi_count"])
        inst = int(loan["installment_paise"])
        if loan.get("total_interest_paise") is not None:
            interest = int(loan["total_interest_paise"])
        else:
            interest = max(0, inst * count - principal)
        dates = emi_dates(loan)
        scheduled = sum(1 for d in dates if d <= td)
        paid = max(0, min(count, scheduled + int(loan.get("emi_adjustment", 0))))
        total_paid = inst * paid + extra_paid
        remaining = max(0, principal + interest - total_paid)
        upcoming = [d for d in dates if d > td]
        out.update({
            "interest_rate": float(loan["interest_rate"]) if loan.get("interest_rate") is not None else None,
            "total_interest": to_rupees(interest),
            "installment": to_rupees(inst),
            "emi_day": int(loan["emi_day"]),
            "emi_count": count,
            "first_emi_date": loan["first_emi_date"],
            "emi_adjustment": int(loan.get("emi_adjustment", 0)),
            "insurance": bool(loan.get("insurance")),
            "log_emis_as_expenses": bool(loan.get("log_emis_as_expenses")),
            "emis_paid": paid,
            "emis_due": count - paid,
            "next_emi_date": upcoming[0].isoformat() if upcoming and paid < count and remaining else None,
            "closure_date": dates[-1].isoformat(),
            "total_payable": to_rupees(principal + interest),
            "total_paid": to_rupees(total_paid),
            "remaining": to_rupees(remaining),
            "monthly_outgo": to_rupees(inst) if remaining and paid < count else 0.0,
        })
    else:
        out.update({
            "total_payable": to_rupees(principal),
            "total_paid": to_rupees(extra_paid),
            "remaining": to_rupees(max(0, principal - extra_paid)),
            "monthly_outgo": 0.0,
        })
    out["status"] = "closed" if out["remaining"] <= 0 else "active"
    return out


def _sync_loan_emis(user_id: str, td: dt.date) -> int:
    """For loans with `log_emis_as_expenses`, add each EMI to expenses on its date
    (only from the day the option was switched on, never back-filled)."""
    table = get_table()
    created = 0
    for loan in list_loans(user_id):
        if loan["kind"] != "loan" or not loan.get("log_emis_as_expenses"):
            continue
        start = loan.get("emi_log_from") or td.isoformat()
        last = loan.get("last_logged_emi")
        done = None
        for d in emi_dates(loan):
            iso = d.isoformat()
            if iso < start or (last and iso <= last):
                continue
            if d > td:
                break
            item = build_expense_item(
                user_id, f"emi{loan['id']}{iso.replace('-', '')}",
                amount_paise=int(loan["installment_paise"]),
                date=iso,
                category="emi",
                note=f"{loan['lender']} EMI",
                payment_method=loan.get("payment_method"),
                card_id=loan.get("card_id"),
                loan_id=loan["id"],
            )
            created += save_expense(user_id, item, only_if_new=True)
            done = iso
        if done:
            _mark(table, loan, "last_logged_emi", done)
    return created


# ======================= auto-generated expenses =======================
def sync_auto(user_id: str, td: dt.date | None = None) -> int:
    """Add any recurring expenses / loan EMIs that have fallen due.

    Runs whenever the user's expenses are read, so there is no scheduler to pay for.
    Idempotent: generated expenses get deterministic ids, and the last-generated
    markers stop a deleted occurrence from being re-created.
    """
    td = td or today()
    return _sync_recurring(user_id, td) + _sync_loan_emis(user_id, td)
