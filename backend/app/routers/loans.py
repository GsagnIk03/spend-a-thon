from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection, func, select

from ..db import get_db, loan_repayments, loans
from ..schemas import LoanIn, RepaymentIn
from ..security import current_user_id
from ..services import check_card, get_loan, list_loans, loan_out, repayments_for, sync_auto
from ..utils import to_paise, today

router = APIRouter(prefix="/loans", tags=["loans & borrowings"])


def _values(body: LoanIn, old: dict | None) -> dict:
    v = {
        "kind": body.kind, "lender": body.lender, "taken_by": body.taken_by,
        "principal_paise": to_paise(body.principal), "note": body.note, "taken_on": body.taken_on,
        "interest_rate": None, "total_interest_paise": None, "installment_paise": None,
        "emi_day": None, "emi_count": None, "first_emi_date": None, "emi_adjustment": 0,
        "insurance": False, "log_emis_as_expenses": False, "payment_method": None, "card_id": None,
        "emi_log_from": None, "last_logged_emi": None,
    }
    if body.kind == "loan":
        v.update({
            "interest_rate": body.interest_rate,
            "total_interest_paise": to_paise(body.total_interest) if body.total_interest is not None else None,
            "installment_paise": to_paise(body.installment),
            "emi_day": body.emi_day, "emi_count": body.emi_count, "first_emi_date": body.first_emi_date,
            "emi_adjustment": body.emi_adjustment, "insurance": body.insurance,
            "log_emis_as_expenses": body.log_emis_as_expenses,
            "payment_method": body.payment_method, "card_id": body.card_id,
        })
        if body.log_emis_as_expenses:
            was_on = bool(old and old.get("log_emis_as_expenses"))
            # Only EMIs from the day this was switched on get logged - no back-filling.
            v["emi_log_from"] = old["emi_log_from"] if was_on and old.get("emi_log_from") else today()
            v["last_logged_emi"] = old.get("last_logged_emi") if was_on else None
    return v


def _out(conn: Connection, user_id: str, loan_id: str) -> dict:
    loan = get_loan(conn, user_id, loan_id)
    return loan_out(loan, repayments_for(conn, user_id, [loan_id])[loan_id])


def _summary(items: list[dict]) -> dict:
    active = [l for l in items if l["status"] == "active"]
    return {
        "outstanding": round(sum(l["remaining"] for l in active), 2),
        "monthly_emi": round(sum(l["monthly_outgo"] for l in active), 2),
        "total_borrowed": round(sum(l["principal"] for l in items), 2),
        "total_paid": round(sum(l["total_paid"] for l in items), 2),
        "active_count": len(active),
        "outstanding_loans": round(sum(l["remaining"] for l in active if l["kind"] == "loan"), 2),
        "outstanding_borrowings": round(sum(l["remaining"] for l in active if l["kind"] == "borrowing"), 2),
    }


@router.get("")
def list_all(user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    sync_auto(conn, user_id)
    rows = list_loans(conn, user_id)
    reps = repayments_for(conn, user_id, [r["id"] for r in rows])
    items = [loan_out(r, reps[r["id"]]) for r in rows]
    items.sort(key=lambda l: (l["status"] != "active", l["kind"] != "loan", -l["remaining"], l["lender"]))
    return {"loans": items, "summary": _summary(items)}


@router.post("", status_code=201)
def create(body: LoanIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    check_card(conn, user_id, body.payment_method, body.card_id)
    loan_id = uuid4().hex[:10]
    conn.execute(loans.insert().values(id=loan_id, user_id=user_id, **_values(body, None)))
    sync_auto(conn, user_id)
    return _out(conn, user_id, loan_id)


@router.put("/{loan_id}")
def update(loan_id: str, body: LoanIn, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    old = get_loan(conn, user_id, loan_id)
    check_card(conn, user_id, body.payment_method, body.card_id, allow_archived=old.get("card_id"))
    conn.execute(loans.update().where(loans.c.id == loan_id, loans.c.user_id == user_id)
                 .values(**_values(body, old), updated_at=func.now()))
    sync_auto(conn, user_id)
    return _out(conn, user_id, loan_id)


@router.delete("/{loan_id}", status_code=204)
def delete(loan_id: str, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    get_loan(conn, user_id, loan_id)
    conn.execute(loans.delete().where(loans.c.id == loan_id, loans.c.user_id == user_id))
    return Response(status_code=204)


# ---------- repayments (borrowings) / prepayments (loans) ----------
@router.post("/{loan_id}/repayments", status_code=201)
def add_repayment(loan_id: str, body: RepaymentIn, user_id: str = Depends(current_user_id),
                  conn: Connection = Depends(get_db)):
    get_loan(conn, user_id, loan_id)
    n = conn.execute(select(func.count()).select_from(loan_repayments)
                     .where(loan_repayments.c.loan_id == loan_id)).scalar_one()
    if n >= 300:
        raise HTTPException(422, "Too many repayments on one loan")
    conn.execute(loan_repayments.insert().values(
        id=uuid4().hex[:8], user_id=user_id, loan_id=loan_id, amount_paise=to_paise(body.amount),
        date=body.date, note=body.note.strip(),
    ))
    return _out(conn, user_id, loan_id)


@router.delete("/{loan_id}/repayments/{rep_id}")
def delete_repayment(loan_id: str, rep_id: str, user_id: str = Depends(current_user_id),
                     conn: Connection = Depends(get_db)):
    get_loan(conn, user_id, loan_id)
    gone = conn.execute(loan_repayments.delete().where(
        loan_repayments.c.id == rep_id, loan_repayments.c.loan_id == loan_id,
        loan_repayments.c.user_id == user_id,
    ).returning(loan_repayments.c.id)).first()
    if not gone:
        raise HTTPException(404, "Repayment not found")
    return _out(conn, user_id, loan_id)
