import csv
import io
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection

from ..constants import CREDIT_CARD, MAX_RANGE_MONTHS, PAYMENT_METHODS
from ..db import get_db
from ..security import current_user_id
from ..services import (
    aggregate, all_categories, card_out, category_labels, expense_out, list_cards, load_budgets,
    payment_key, payment_rows, query_months, sync_auto,
)
from ..utils import add_months, days_in_month, month_range, require_month, to_rupees

router = APIRouter(tags=["insights"])


def _range(start: str | None, end: str | None) -> tuple[str, str]:
    end = require_month(end, "end")
    start = require_month(start, "start") if start else end
    if start > end:
        raise HTTPException(422, "start must not be after end")
    if len(month_range(start, end)) > MAX_RANGE_MONTHS:
        raise HTTPException(422, f"at most {MAX_RANGE_MONTHS} months at a time")
    return start, end


@router.get("/meta")
def meta(user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    """Everything the UI needs for pickers and labels: categories (incl. custom), payment
    methods and credit cards (incl. archived, so old expenses can still be labelled)."""
    return {
        "categories": all_categories(conn, user_id),
        "payment_methods": PAYMENT_METHODS,
        "cards": [card_out(c) for c in list_cards(conn, user_id)],
    }


@router.get("/summary")
def summary(month: str | None = None, user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    month = require_month(month)
    sync_auto(conn, user_id)
    start = add_months(month, -5)
    items = query_months(conn, user_id, start, month)
    budgets = load_budgets(conn, user_id)

    trend = {m: 0 for m in month_range(start, month)}
    by_day = {f"{month}-{d:02d}": 0 for d in range(1, days_in_month(month) + 1)}
    this_month = []
    for it in items:
        paise = int(it["amount_paise"])
        iso = it["date"].isoformat()
        m = iso[:7]
        if m in trend:
            trend[m] += paise
        if m == month:
            this_month.append(it)
            by_day[iso] += paise

    agg = aggregate(this_month)
    cats = set(agg["by_cat"]) | set(budgets)
    by_category = sorted(
        (
            {
                "category": c,
                "spent": to_rupees(agg["by_cat"][c][0] if c in agg["by_cat"] else 0),
                "count": agg["by_cat"][c][1] if c in agg["by_cat"] else 0,
                "budget": to_rupees(budgets[c]) if c in budgets else None,
            }
            for c in cats
        ),
        key=lambda x: (-x["spent"], x["category"]),
    )
    cards = {c["id"]: c for c in list_cards(conn, user_id)}
    top = sorted(this_month, key=lambda i: int(i["amount_paise"]), reverse=True)[:5]
    budget_total = sum(budgets.values())
    return {
        "month": month,
        "total": to_rupees(trend[month]),
        "count": len(this_month),
        "previous_total": to_rupees(trend[add_months(month, -1)]),
        "budget_total": to_rupees(budget_total) if budget_total else None,
        "by_category": by_category,
        "by_payment": payment_rows(agg["by_pay"], cards),
        "by_day": [{"date": d, "total": to_rupees(v)} for d, v in by_day.items()],
        "trend": [{"month": m, "total": to_rupees(v)} for m, v in trend.items()],
        "top": [expense_out(i) for i in top],
    }


@router.get("/insights")
def insights(start: str | None = None, end: str | None = None, user_id: str = Depends(current_user_id),
             conn: Connection = Depends(get_db)):
    """Spend per category and per payment method over a period, with month-by-month series."""
    start, end = _range(start, end)
    sync_auto(conn, user_id)
    items = query_months(conn, user_id, start, end)
    months = month_range(start, end)
    agg = aggregate(items)
    total = sum(int(i["amount_paise"]) for i in items)

    cat_monthly: dict[str, dict[str, int]] = defaultdict(lambda: {m: 0 for m in months})
    pay_monthly: dict[str, dict[str, int]] = defaultdict(lambda: {m: 0 for m in months})
    monthly = {m: 0 for m in months}
    for it in items:
        p = int(it["amount_paise"])
        m = it["date"].isoformat()[:7]
        monthly[m] += p
        cat_monthly[it["category"]][m] += p
        pay_monthly[payment_key(it)][m] += p

    cards = {c["id"]: c for c in list_cards(conn, user_id)}
    by_category = sorted(
        (
            {
                "category": c,
                "total": to_rupees(t),
                "count": n,
                "average": to_rupees(t // n) if n else 0,
                "share": round(t / total * 100, 1) if total else 0,
                "monthly": [{"month": m, "total": to_rupees(v)} for m, v in cat_monthly[c].items()],
            }
            for c, (t, n) in agg["by_cat"].items()
        ),
        key=lambda x: -x["total"],
    )
    by_payment = payment_rows(agg["by_pay"], cards)
    for row in by_payment:
        row["share"] = round(row["total"] / to_rupees(total) * 100, 1) if total else 0
        row["monthly"] = [{"month": m, "total": to_rupees(v)} for m, v in pay_monthly[row["key"]].items()]

    groups: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # rolled up: Cash / Credit card / ...
    for key, (t, n) in agg["by_pay"].items():
        g = CREDIT_CARD if key.startswith("card:") else key
        groups[g][0] += t
        groups[g][1] += n

    return {
        "start": start,
        "end": end,
        "months": len(months),
        "total": to_rupees(total),
        "count": len(items),
        "monthly_average": to_rupees(total // len(months)),
        "monthly": [{"month": m, "total": to_rupees(v)} for m, v in monthly.items()],
        "by_category": by_category,
        "by_payment": by_payment,
        "by_method": sorted(
            ({"method": g, "total": to_rupees(t), "count": n} for g, (t, n) in groups.items()),
            key=lambda r: -r["total"],
        ),
    }


@router.get("/export")
def export_csv(start: str | None = None, end: str | None = None,
               user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    start, end = _range(start, end)
    sync_auto(conn, user_id)
    items = sorted(query_months(conn, user_id, start, end), key=lambda i: (i["date"], i["created_at"]))
    labels = category_labels(conn, user_id)
    cards = {c["id"]: c["name"] for c in list_cards(conn, user_id)}

    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel opens ₹ and emoji correctly
    w = csv.writer(buf)
    w.writerow(["Date", "Category", "Amount (INR)", "Note", "Payment method", "Card", "Auto-added"])
    for i in items:
        card = cards.get(i.get("card_id") or "", "") if i.get("payment_method") == CREDIT_CARD else ""
        w.writerow([
            i["date"].isoformat(),
            labels.get(i["category"], i["category"]),
            f"{to_rupees(i['amount_paise']):.2f}",
            i.get("note") or "",
            i.get("payment_method") or "",
            card,
            "Yes" if i.get("recurring_id") or i.get("loan_id") else "",
        ])
    name = f"expenses_{start}" + (f"_to_{end}" if end != start else "") + ".csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
