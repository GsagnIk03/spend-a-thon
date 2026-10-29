from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response

from ..db import get_table, user_pk
from ..schemas import LoanIn, RepaymentIn
from ..security import current_user_id
from ..services import check_card, get_loan, list_loans, loan_out, sync_auto
from ..utils import now_iso, to_paise, today

router = APIRouter(prefix="/loans", tags=["loans & borrowings"])


def _item(user_id: str, loan_id: str, body: LoanIn, old: dict | None) -> dict:
    item = {
        "PK": user_pk(user_id), "SK": f"LOAN#{loan_id}", "type": "loan",
        "id": loan_id, "kind": body.kind, "lender": body.lender, "taken_by": body.taken_by,
        "principal_paise": to_paise(body.principal), "note": body.note,
        "repayments": (old or {}).get("repayments", []),
        "created_at": (old or {}).get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    if body.taken_on:
        item["taken_on"] = body.taken_on.isoformat()
    if body.kind == "loan":
        item.update({
            "installment_paise": to_paise(body.installment),
            "emi_day": body.emi_day,
            "emi_count": body.emi_count,
            "first_emi_date": body.first_emi_date.isoformat(),
            "emi_adjustment": body.emi_adjustment,
            "insurance": body.insurance,
            "log_emis_as_expenses": body.log_emis_as_expenses,
        })
        if body.interest_rate is not None:
            item["interest_rate"] = body.interest_rate
        if body.total_interest is not None:
            item["total_interest_paise"] = to_paise(body.total_interest)
        if body.payment_method:
            item["payment_method"] = body.payment_method
        if body.card_id:
            item["card_id"] = body.card_id
        if body.log_emis_as_expenses:
            was_on = old and old.get("log_emis_as_expenses")
            # Only EMIs from the day this was switched on get logged - no back-filling.
            item["emi_log_from"] = old["emi_log_from"] if was_on and old.get("emi_log_from") else today().isoformat()
            if was_on and old.get("last_logged_emi"):
                item["last_logged_emi"] = old["last_logged_emi"]
    return item


def _summary(loans: list[dict]) -> dict:
    active = [l for l in loans if l["status"] == "active"]
    return {
        "outstanding": round(sum(l["remaining"] for l in active), 2),
        "monthly_emi": round(sum(l["monthly_outgo"] for l in active), 2),
        "total_borrowed": round(sum(l["principal"] for l in loans), 2),
        "total_paid": round(sum(l["total_paid"] for l in loans), 2),
        "active_count": len(active),
        "outstanding_loans": round(sum(l["remaining"] for l in active if l["kind"] == "loan"), 2),
        "outstanding_borrowings": round(sum(l["remaining"] for l in active if l["kind"] == "borrowing"), 2),
    }


@router.get("")
def list_all(user_id: str = Depends(current_user_id)):
    sync_auto(user_id)
    loans = [loan_out(l) for l in list_loans(user_id)]
    loans.sort(key=lambda l: (l["status"] != "active", l["kind"] != "loan", -l["remaining"], l["lender"]))
    return {"loans": loans, "summary": _summary(loans)}


@router.post("", status_code=201)
def create(body: LoanIn, user_id: str = Depends(current_user_id)):
    check_card(user_id, body.payment_method, body.card_id)
    loan_id = uuid4().hex[:10]
    get_table().put_item(Item=_item(user_id, loan_id, body, None))
    sync_auto(user_id)
    return loan_out(get_loan(user_id, loan_id))


@router.put("/{loan_id}")
def update(loan_id: str, body: LoanIn, user_id: str = Depends(current_user_id)):
    old = get_loan(user_id, loan_id)
    check_card(user_id, body.payment_method, body.card_id, allow_archived=old.get("card_id"))
    get_table().put_item(Item=_item(user_id, loan_id, body, old))
    sync_auto(user_id)
    return loan_out(get_loan(user_id, loan_id))


@router.delete("/{loan_id}", status_code=204)
def delete(loan_id: str, user_id: str = Depends(current_user_id)):
    get_loan(user_id, loan_id)
    get_table().delete_item(Key={"PK": user_pk(user_id), "SK": f"LOAN#{loan_id}"})
    return Response(status_code=204)


# ---------- repayments (borrowings) / prepayments (loans) ----------
@router.post("/{loan_id}/repayments", status_code=201)
def add_repayment(loan_id: str, body: RepaymentIn, user_id: str = Depends(current_user_id)):
    loan = get_loan(user_id, loan_id)
    if len(loan.get("repayments", [])) >= 300:
        raise HTTPException(422, "Too many repayments on one loan")
    rep = {"id": uuid4().hex[:8], "amount_paise": to_paise(body.amount),
           "date": body.date.isoformat(), "note": body.note.strip()}
    get_table().update_item(
        Key={"PK": loan["PK"], "SK": loan["SK"]},
        UpdateExpression="SET repayments = list_append(if_not_exists(repayments, :empty), :r)",
        ExpressionAttributeValues={":r": [rep], ":empty": []},
    )
    return loan_out(get_loan(user_id, loan_id))


@router.delete("/{loan_id}/repayments/{rep_id}")
def delete_repayment(loan_id: str, rep_id: str, user_id: str = Depends(current_user_id)):
    loan = get_loan(user_id, loan_id)
    reps = loan.get("repayments", [])
    keep = [r for r in reps if r["id"] != rep_id]
    if len(keep) == len(reps):
        raise HTTPException(404, "Repayment not found")
    get_table().update_item(
        Key={"PK": loan["PK"], "SK": loan["SK"]},
        UpdateExpression="SET repayments = :r",
        ExpressionAttributeValues={":r": keep},
    )
    loan["repayments"] = keep
    return loan_out(loan)
