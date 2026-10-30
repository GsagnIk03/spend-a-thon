import datetime as dt

from app import services
from tests.conftest import register


def add(client, auth, **kw):
    body = {"amount": 250.5, "date": "2026-10-05", "category": "food", "note": "Lunch",
            "payment_method": "Google Pay", **kw}
    r = client.post("/api/expenses", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


# ---------- auth ----------
def test_register_login_me(client):
    auth = register(client, email="Me@Example.com")
    assert client.get("/api/auth/me", headers=auth).json()["email"] == "me@example.com"
    r = client.post("/api/auth/login", json={"email": "ME@example.com", "password": "secret123"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Sagnik"


def test_duplicate_email_and_bad_password(client, auth):
    r = client.post("/api/auth/register",
                    json={"name": "X", "email": "sagnik@example.com", "password": "whatever1"})
    assert r.status_code == 409
    r = client.post("/api/auth/login", json={"email": "sagnik@example.com", "password": "nope-nope"})
    assert r.status_code == 401


def test_requires_auth(client):
    assert client.get("/api/expenses").status_code == 401
    assert client.get("/api/expenses", headers={"Authorization": "Bearer junk"}).status_code == 401


# ---------- expenses ----------
def test_expense_crud_and_month_filter(client, auth):
    e = add(client, auth)
    assert e["amount"] == 250.5
    add(client, auth, date="2026-09-30", amount=100, category="fuel")

    oct_ = client.get("/api/expenses?month=2026-10", headers=auth).json()
    assert [x["id"] for x in oct_] == [e["id"]]

    r = client.put(f"/api/expenses/{e['id']}", headers=auth,
                   json={"amount": "99.99", "date": "2026-09-01", "category": "groceries", "note": ""})
    assert r.status_code == 200 and r.json()["amount"] == 99.99
    assert client.get("/api/expenses?month=2026-10", headers=auth).json() == []
    assert len(client.get("/api/expenses?month=2026-09", headers=auth).json()) == 2

    assert client.delete(f"/api/expenses/{e['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/expenses/{e['id']}", headers=auth).status_code == 404


def test_validation(client, auth):
    bad = [
        {"amount": -5, "date": "2026-10-01", "category": "food"},
        {"amount": 5, "date": "2026-10-01", "category": "nope"},
        {"amount": 5.555, "date": "2026-10-01", "category": "food"},
        {"amount": 5, "date": "2026-10-01", "category": "food", "payment_method": "Bitcoin"},
    ]
    for b in bad:
        assert client.post("/api/expenses", json=b, headers=auth).status_code == 422, b
    assert client.get("/api/expenses?month=2026-13", headers=auth).status_code == 422


def test_users_are_isolated(client, auth):
    e = add(client, auth)
    other = register(client, email="tuhin@example.com", name="Tuhin")
    assert client.get("/api/expenses?month=2026-10", headers=other).json() == []
    assert client.get(f"/api/expenses/{e['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/expenses/{e['id']}", headers=other).status_code == 404
    assert client.get("/api/summary?month=2026-10", headers=other).json()["total"] == 0


# ---------- budgets + summary ----------
def test_budgets_and_summary(client, auth):
    add(client, auth, amount=300, category="food", date="2026-10-02")
    add(client, auth, amount=200, category="food", date="2026-10-02")
    add(client, auth, amount=1000, category="rent", date="2026-10-01")
    add(client, auth, amount=400, category="fuel", date="2026-09-15")

    r = client.put("/api/budgets", headers=auth, json={"budgets": {"food": 450, "travel": 2000}})
    assert r.json()["budgets"] == {"food": 450.0, "travel": 2000.0}
    client.put("/api/budgets", headers=auth, json={"budgets": {"travel": None}})
    assert client.get("/api/budgets", headers=auth).json()["budgets"] == {"food": 450.0}

    s = client.get("/api/summary?month=2026-10", headers=auth).json()
    assert s["total"] == 1500 and s["count"] == 3 and s["previous_total"] == 400
    assert s["budget_total"] == 450
    assert s["by_category"][0] == {"category": "rent", "spent": 1000.0, "count": 1, "budget": None}
    assert {"category": "food", "spent": 500.0, "count": 2, "budget": 450.0} in s["by_category"]
    assert s["by_payment"][0]["label"] == "Google Pay" and s["by_payment"][0]["count"] == 3
    assert len(s["by_day"]) == 31 and s["by_day"][1] == {"date": "2026-10-02", "total": 500.0}
    assert [t["month"] for t in s["trend"]] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert s["top"][0]["amount"] == 1000


# ---------- recurring ----------
def test_recurring_generation_is_idempotent(client, auth, monkeypatch):
    today = {"d": dt.date(2026, 10, 15)}
    monkeypatch.setattr(services, "today", lambda: today["d"])

    r = client.post("/api/recurring", headers=auth, json={
        "amount": 15000, "category": "rent", "note": "Flat rent", "day_of_month": 20,
        "start_month": "2026-08",
    })
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["last_generated_month"] == "2026-09" and rec["next_due"] == "2026-10-20"

    def months():
        out = []
        for m in ("2026-08", "2026-09", "2026-10"):
            out += client.get(f"/api/expenses?month={m}", headers=auth).json()
        return sorted(x["date"] for x in out)

    assert months() == ["2026-08-20", "2026-09-20"]

    today["d"] = dt.date(2026, 10, 25)
    assert months() == ["2026-08-20", "2026-09-20", "2026-10-20"]
    assert months() == ["2026-08-20", "2026-09-20", "2026-10-20"]  # no duplicates

    # a deleted occurrence is not re-created
    sep = client.get("/api/expenses?month=2026-09", headers=auth).json()[0]
    assert sep["recurring_id"] == rec["id"]
    client.delete(f"/api/expenses/{sep['id']}", headers=auth)
    assert months() == ["2026-08-20", "2026-10-20"]

    # day 31 clamps to the month's last day; pausing stops generation
    client.put(f"/api/recurring/{rec['id']}", headers=auth, json={
        "amount": 16000, "category": "rent", "day_of_month": 31, "start_month": "2026-08", "active": False,
    })
    today["d"] = dt.date(2026, 11, 30)
    assert client.get("/api/expenses?month=2026-11", headers=auth).json() == []
    client.put(f"/api/recurring/{rec['id']}", headers=auth, json={
        "amount": 16000, "category": "rent", "day_of_month": 31, "start_month": "2026-08", "active": True,
    })
    nov = client.get("/api/expenses?month=2026-11", headers=auth).json()
    assert [(x["date"], x["amount"]) for x in nov] == [("2026-11-30", 16000.0)]

    assert client.delete(f"/api/recurring/{rec['id']}", headers=auth).status_code == 204
    assert client.get("/api/recurring", headers=auth).json() == []


def test_recurring_end_month_validation(client, auth):
    r = client.post("/api/recurring", headers=auth, json={
        "amount": 10, "category": "emi", "day_of_month": 5, "start_month": "2026-10", "end_month": "2026-09",
    })
    assert r.status_code == 422


# ---------- export ----------
def test_export_csv(client, auth):
    add(client, auth, amount=120, note="Tea, samosa", date="2026-10-03")
    add(client, auth, amount=80, category="transport", date="2026-09-03", payment_method=None)
    r = client.get("/api/export?start=2026-09&end=2026-10", headers=auth)
    assert r.status_code == 200
    assert 'filename="expenses_2026-09_to_2026-10.csv"' in r.headers["content-disposition"]
    lines = r.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("Date,Category,Amount (INR)")
    assert lines[1].startswith("2026-09-03,Transport,80.00")
    assert lines[2] == '2026-10-03,Food & Dining,120.00,"Tea, samosa",Google Pay,,'
    assert client.get("/api/export?start=2026-10&end=2026-09", headers=auth).status_code == 422


def test_meta_and_health(client, auth):
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/meta").status_code == 401
    m = client.get("/api/meta", headers=auth).json()
    assert len(m["categories"]) == 16 and "Google Pay" in m["payment_methods"] and m["cards"] == []
