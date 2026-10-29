"""Load categories, credit cards and loans into your spend-a-thon account through the API.

    python scripts/seed.py https://your-site.cloudfront.net you@example.com [path/to/seed.json]

Prompts for your password. Safe to re-run: anything with the same name already in
your account (category label, card name, lender + taken-by + amount) is skipped.
Uses only the standard library.
"""
import getpass
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def call(base: str, method: str, path: str, token: str | None = None, body=None):
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} failed ({e.code}): {e.read().decode()}") from None


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    base, email = sys.argv[1], sys.argv[2]
    seed_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).with_name("seed.json")
    data = json.loads(seed_path.read_text(encoding="utf-8"))

    token = call(base, "POST", "/auth/login", body={"email": email, "password": getpass.getpass("Password: ")})["token"]

    have = {c["label"].lower() for c in call(base, "GET", "/categories", token)}
    for c in data.get("categories", []):
        if c["label"].lower() in have:
            print(f"  = category {c['label']} (exists)")
            continue
        call(base, "POST", "/categories", token, c)
        print(f"  + category {c['label']}")

    have = {c["name"].lower() for c in call(base, "GET", "/cards?include_archived=true", token)}
    for c in data.get("cards", []):
        if c["name"].lower() in have:
            print(f"  = card {c['name']} (exists)")
            continue
        call(base, "POST", "/cards", token, c)
        print(f"  + card {c['name']}")

    existing = call(base, "GET", "/loans", token)["loans"]
    have = {(l["lender"].lower(), l["taken_by"].lower(), round(l["principal"])) for l in existing}
    for l in data.get("loans", []):
        key = (l["lender"].lower(), l.get("taken_by", "").lower(), round(l["principal"]))
        if key in have:
            print(f"  = {l['lender']} (exists)")
            continue
        body = {k: v for k, v in l.items() if k != "repayments"}
        loan = call(base, "POST", "/loans", token, body)
        for r in l.get("repayments", []):
            loan = call(base, "POST", f"/loans/{loan['id']}/repayments", token, r)
        extra = f", {loan['emis_paid']}/{loan['emi_count']} EMIs" if loan["kind"] == "loan" else ""
        print(f"  + {loan['lender']}: remaining ₹{loan['remaining']:,.0f}{extra}")

    s = call(base, "GET", "/loans", token)["summary"]
    print(f"\nDone. Outstanding ₹{s['outstanding']:,.0f} · EMIs ₹{s['monthly_emi']:,.0f}/month")


if __name__ == "__main__":
    main()
