"""Custom categories, credit cards, loans & borrowings, insights."""
import datetime as dt

import pytest

from app import services
from tests.conftest import register

TODAY = dt.date(2026, 10, 29)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(services, "today", lambda: TODAY)
    from app.routers import loans as loans_router
    monkeypatch.setattr(loans_router, "today", lambda: TODAY)


def spend(client, auth, **kw):
    body = {"amount": 100, "date": "2026-10-10", "category": "food", "note": "", **kw}
    r = client.post("/api/expenses", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def card(client, auth, **kw):
    body = {"name": "HDFC Millennia", "bank": "HDFC", "last4": "4417", "credit_limit": 100000,
            "available": 80000, "statement_day": 15, "due_day": 5, **kw}
    r = client.post("/api/cards", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def available(client, auth, card_id):
    return next(c for c in client.get("/api/cards", headers=auth).json() if c["id"] == card_id)["available"]


# ---------- custom categories ----------
def test_custom_categories(client, auth):
    r = client.post("/api/categories", headers=auth, json={"label": "Cigarettes", "emoji": "🚬"})
    assert r.status_code == 201
    cig = r.json()
    assert cig["id"].startswith("c_") and cig["color"].startswith("#")
    assert client.post("/api/categories", headers=auth, json={"label": "cigarettes", "emoji": "x"}).status_code == 409
    assert client.post("/api/categories", headers=auth, json={"label": "Rent", "emoji": "x"}).status_code == 409

    e = spend(client, auth, category=cig["id"], amount=20)
    labels = [c["label"] for c in client.get("/api/meta", headers=auth).json()["categories"]]
    assert "Cigarettes" in labels and labels[-1] == "Other"

    # other users can't use it
    other = register(client, email="x@example.com")
    assert client.post("/api/expenses", headers=other,
                       json={"amount": 1, "date": "2026-10-01", "category": cig["id"]}).status_code == 422
    assert client.post("/api/expenses", headers=auth,
                       json={"amount": 1, "date": "2026-10-01", "category": "c_nope"}).status_code == 422

    client.put("/api/budgets", headers=auth, json={"budgets": {cig["id"]: 500}})
    assert client.put(f"/api/categories/{cig['id']}", headers=auth,
                      json={"label": "Smokes", "emoji": "🚬"}).json()["label"] == "Smokes"
    assert client.put("/api/categories/food", headers=auth, json={"label": "X", "emoji": "x"}).status_code == 404

    # deleting moves expenses to Other and drops the budget
    assert client.delete(f"/api/categories/{cig['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/expenses/{e['id']}", headers=auth).json()["category"] == "other"
    assert client.get("/api/budgets", headers=auth).json()["budgets"] == {}


# ---------- credit cards ----------
def test_card_balance_follows_expenses(client, auth):
    c = card(client, auth)
    assert c["used"] == 20000 and c["utilization"] == 20.0
    other_card = card(client, auth, name="SBI SimplyCLICK", available=50000)

    e = spend(client, auth, amount=1500.50, payment_method="Credit card", card_id=c["id"])
    assert available(client, auth, c["id"]) == 78499.50

    # edit amount
    body = {"amount": 2000, "date": "2026-10-10", "category": "food", "payment_method": "Credit card", "card_id": c["id"]}
    client.put(f"/api/expenses/{e['id']}", headers=auth, json=body)
    assert available(client, auth, c["id"]) == 78000

    # move to another card
    client.put(f"/api/expenses/{e['id']}", headers=auth, json={**body, "card_id": other_card["id"]})
    assert available(client, auth, c["id"]) == 80000
    assert available(client, auth, other_card["id"]) == 48000

    # switch to cash, then back, then delete
    client.put(f"/api/expenses/{e['id']}", headers=auth, json={**body, "payment_method": "Cash"})
    assert available(client, auth, other_card["id"]) == 50000
    assert client.get(f"/api/expenses/{e['id']}", headers=auth).json()["card_id"] is None
    client.put(f"/api/expenses/{e['id']}", headers=auth, json=body)
    assert available(client, auth, c["id"]) == 78000
    client.delete(f"/api/expenses/{e['id']}", headers=auth)
    assert available(client, auth, c["id"]) == 80000

    # month spend on the card
    spend(client, auth, amount=300, payment_method="Credit card", card_id=c["id"])
    got = next(x for x in client.get("/api/cards", headers=auth).json() if x["id"] == c["id"])
    assert got["month_spent"] == 300 and got["month_count"] == 1


def test_card_payments_and_balance(client, auth):
    c = card(client, auth)
    spend(client, auth, amount=5000, payment_method="Credit card", card_id=c["id"])
    r = client.post(f"/api/cards/{c['id']}/payments", headers=auth,
                    json={"amount": 25000, "date": "2026-10-20", "note": "Bill paid"})
    assert r.status_code == 201 and r.json()["card"]["available"] == 100000
    pid = r.json()["payment"]["id"]
    assert len(client.get(f"/api/cards/{c['id']}/payments", headers=auth).json()) == 1
    assert client.delete(f"/api/cards/{c['id']}/payments/{pid}", headers=auth).json()["available"] == 75000

    assert client.put(f"/api/cards/{c['id']}/balance", headers=auth, json={"available": 61234.5}).json()["available"] == 61234.5


def test_card_validation_and_archive(client, auth):
    c = card(client, auth)
    other = register(client, email="y@example.com")
    # someone else's card id
    r = client.post("/api/expenses", headers=other, json={
        "amount": 10, "date": "2026-10-01", "category": "food", "payment_method": "Credit card", "card_id": c["id"]})
    assert r.status_code == 422
    # card_id ignored for non-card methods
    e = spend(client, auth, payment_method="Cash", card_id=c["id"])
    assert e["card_id"] is None and available(client, auth, c["id"]) == 80000

    on_card = spend(client, auth, amount=50, payment_method="Credit card", card_id=c["id"])
    assert client.delete(f"/api/cards/{c['id']}", headers=auth).status_code == 204
    assert client.get("/api/cards", headers=auth).json() == []
    assert len(client.get("/api/cards?include_archived=true", headers=auth).json()) == 1
    # new spends on an archived card are refused, but old ones can still be edited
    r = client.post("/api/expenses", headers=auth, json={
        "amount": 10, "date": "2026-10-01", "category": "food", "payment_method": "Credit card", "card_id": c["id"]})
    assert r.status_code == 422
    r = client.put(f"/api/expenses/{on_card['id']}", headers=auth, json={
        "amount": 60, "date": "2026-10-10", "category": "food", "payment_method": "Credit card", "card_id": c["id"]})
    assert r.status_code == 200
    assert client.post(f"/api/cards/{c['id']}/restore", headers=auth).json()["available"] == 79940


def test_recurring_on_card_deducts_once(client, auth):
    c = card(client, auth)
    client.post("/api/recurring", headers=auth, json={
        "amount": 649, "category": "subscriptions", "note": "Netflix", "day_of_month": 18,
        "start_month": "2026-09", "payment_method": "Credit card", "card_id": c["id"]})
    client.get("/api/expenses?month=2026-10", headers=auth)
    client.get("/api/expenses?month=2026-10", headers=auth)
    assert available(client, auth, c["id"]) == 80000 - 2 * 649


# ---------- loans & borrowings (figures from the real sheet) ----------
SHEET = [
    {"kind": "loan", "lender": "Indusind Bank", "taken_by": "Sagnik", "principal": 265746,
     "interest_rate": 17.5, "total_interest": 80306, "installment": 9541, "emi_day": 4, "emi_count": 36,
     "first_emi_date": "2025-09-04", "insurance": True},
    {"kind": "loan", "lender": "Poonawalla Fincorp", "taken_by": "Sagnik", "principal": 400000,
     "interest_rate": 20.5, "total_interest": 135118, "installment": 14968, "emi_day": 5, "emi_count": 36,
     "first_emi_date": "2026-09-05", "insurance": True},
    {"kind": "loan", "lender": "Indusind Bank", "taken_by": "Shouvik Kar", "principal": 400000,
     "interest_rate": 15.5, "total_interest": 101243, "installment": 13964, "emi_day": 1, "emi_count": 36,
     "first_emi_date": "2026-02-09", "insurance": True},
]


def test_emi_loans_match_sheet(client, auth):
    out = [client.post("/api/loans", headers=auth, json=b).json() for b in SHEET]
    expect = [  # paid, due, total paid, remaining, closure
        (14, 22, 133574, 212478, "2028-08-04"),
        (2, 34, 29936, 505182, "2029-08-05"),
        (9, 27, 125676, 375567, "2029-01-01"),
    ]
    for loan, (paid, due, total_paid, remaining, closure) in zip(out, expect):
        assert (loan["emis_paid"], loan["emis_due"], loan["total_paid"], loan["remaining"], loan["closure_date"]) == \
            (paid, due, total_paid, remaining, closure), loan["lender"]
    assert out[0]["next_emi_date"] == "2026-11-04"
    assert out[2]["next_emi_date"] == "2026-11-01"

    data = client.get("/api/loans", headers=auth).json()
    assert data["summary"]["monthly_emi"] == 9541 + 14968 + 13964
    assert data["summary"]["outstanding"] == 212478 + 505182 + 375567


def test_emi_adjustment_and_prepayment(client, auth):
    loan = client.post("/api/loans", headers=auth, json={**SHEET[0], "emi_adjustment": -1}).json()
    assert loan["emis_paid"] == 13 and loan["remaining"] == 212478 + 9541
    loan = client.post(f"/api/loans/{loan['id']}/repayments", headers=auth,
                       json={"amount": 50000, "date": "2026-10-15", "note": "Part prepayment"}).json()
    assert loan["total_paid"] == 9541 * 13 + 50000


def test_borrowings(client, auth):
    b = client.post("/api/loans", headers=auth, json={
        "kind": "borrowing", "lender": "Manabendra Ganguly", "taken_by": "Sagnik", "principal": 150000,
        "installment": 999, "emi_count": 3}).json()  # EMI fields are ignored for borrowings
    assert b["installment"] is None and b["remaining"] == 150000
    b = client.post(f"/api/loans/{b['id']}/repayments", headers=auth,
                    json={"amount": 32000, "date": "2026-10-01"}).json()
    assert b["total_paid"] == 32000 and b["remaining"] == 118000 and b["status"] == "active"
    b = client.post(f"/api/loans/{b['id']}/repayments", headers=auth,
                    json={"amount": 118000, "date": "2026-10-20"}).json()
    assert b["status"] == "closed"
    rid = b["repayments"][-1]["id"]
    assert client.delete(f"/api/loans/{b['id']}/repayments/{rid}", headers=auth).json()["remaining"] == 118000

    assert client.post("/api/loans", headers=auth, json={
        "kind": "loan", "lender": "X", "principal": 100}).status_code == 422
    other = register(client, email="z@example.com")
    assert client.get("/api/loans", headers=other).json()["loans"] == []
    assert client.delete(f"/api/loans/{b['id']}", headers=other).status_code == 404


def test_emis_logged_as_expenses_from_switch_on(client, auth, monkeypatch):
    c = card(client, auth, available=100000)
    loan = client.post("/api/loans", headers=auth, json={
        **SHEET[1], "log_emis_as_expenses": True, "payment_method": "Credit card", "card_id": c["id"]}).json()
    # turned on 29 Oct: Sep 5 and Oct 5 EMIs are NOT back-filled
    assert client.get("/api/expenses?start=2026-09&end=2026-10", headers=auth).json() == []

    nov = dt.date(2026, 11, 6)
    monkeypatch.setattr(services, "today", lambda: nov)
    exps = client.get("/api/expenses?month=2026-11", headers=auth).json()
    assert [(e["date"], e["amount"], e["category"], e["loan_id"]) for e in exps] == \
        [("2026-11-05", 14968.0, "emi", loan["id"])]
    client.get("/api/expenses?month=2026-11", headers=auth)
    assert available(client, auth, c["id"]) == 100000 - 14968


# ---------- insights ----------
def test_insights_by_category_and_payment(client, auth):
    tea = client.post("/api/categories", headers=auth, json={"label": "Tea", "emoji": "☕"}).json()
    hdfc = card(client, auth)
    sbi = card(client, auth, name="SBI SimplyCLICK")
    spend(client, auth, amount=20, category=tea["id"], payment_method="Cash", date="2026-09-03")
    spend(client, auth, amount=30, category=tea["id"], payment_method="Cash", date="2026-10-03")
    spend(client, auth, amount=650, category="health", payment_method="Google Pay", date="2026-10-04")
    spend(client, auth, amount=1200, category="health", payment_method="Credit card", card_id=hdfc["id"], date="2026-10-05")
    spend(client, auth, amount=400, category="shopping", payment_method="Credit card", card_id=sbi["id"], date="2026-10-06")
    spend(client, auth, amount=999, category="food", date="2026-08-30")  # outside range

    r = client.get("/api/insights?start=2026-09&end=2026-10", headers=auth).json()
    assert r["total"] == 2300 and r["count"] == 5 and r["monthly_average"] == 1150
    cats = {c["category"]: c for c in r["by_category"]}
    assert cats["health"]["total"] == 1850 and cats["health"]["count"] == 2
    assert cats[tea["id"]]["total"] == 50 and cats[tea["id"]]["average"] == 25
    assert [m["total"] for m in cats[tea["id"]]["monthly"]] == [20, 30]

    pays = {p["label"]: (p["total"], p["count"]) for p in r["by_payment"]}
    assert pays == {"HDFC Millennia": (1200, 1), "Google Pay": (650, 1),
                    "SBI SimplyCLICK": (400, 1), "Cash": (50, 2)}
    methods = {m["method"]: (m["total"], m["count"]) for m in r["by_method"]}
    assert methods["Credit card"] == (1600, 2)

    # drill-down: expenses filtered by card / category over a range
    on_hdfc = client.get(f"/api/expenses?start=2026-09&end=2026-10&payment=card:{hdfc['id']}", headers=auth).json()
    assert [e["amount"] for e in on_hdfc] == [1200]
    teas = client.get(f"/api/expenses?start=2026-09&end=2026-10&category={tea['id']}", headers=auth).json()
    assert len(teas) == 2

    csv = client.get("/api/export?start=2026-10&end=2026-10", headers=auth).text
    assert "Tea,30.00,,Cash" in csv and "Credit card,HDFC Millennia" in csv
