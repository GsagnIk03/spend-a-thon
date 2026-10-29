# spend-a-thon

Personal expense tracker. Anyone can sign up; every user sees only their own expenses.

- **Dashboard** – month total, change vs last month, budget left, daily average, category donut, day-by-day and 6-month charts, biggest expenses
- **Expenses** – add / edit / delete, search, category filter, grouped by day, receipt photos or PDFs (up to 5 MB)
- **Budgets** – monthly limit per category with progress (amber at 85%, red when over)
- **Recurring** – rent, EMIs, subscriptions; added automatically on their due day (day 29–31 falls back to the month's last day), pause / resume, optional end month
- **Insights** – any period (this month → 12 months / custom): spend per category with counts, averages and month-by-month bars, and per payment method (Cash, Google Pay, PhonePe, each credit card…); tap a row to see the actual transactions
- **Custom categories** – add your own (e.g. Cigarettes, Tea & Snacks) from the expense form or the Categories screen
- **Credit cards** – limit, available balance, utilisation, statement/due days. Spends on a card reduce its available balance automatically (edits, card switches and deletes are reversed correctly); record bill payments/refunds or sync the balance with your bank app
- **Loans & borrowings** – EMI loans work out EMIs paid/due, amount paid, remaining and closure date from the schedule, so they stay current on their own; personal borrowings track repayments. Optionally log each EMI as an expense on its date
- **CSV export** – any range up to 24 months, opens cleanly in Excel / Google Sheets (includes the card used)
- INR only, Asia/Kolkata time, mobile-first (bottom tab bar, installable to home screen)

## Stack & cost

| Part | Service | Cost at personal scale |
|---|---|---|
| Frontend | React + TypeScript (Vite) on S3 + CloudFront | free tier |
| API | FastAPI on Lambda (Mangum) behind API Gateway HTTP API | free tier |
| Data | DynamoDB on-demand, single table | free tier |
| Receipts | Private S3 bucket, browser uploads via short-lived signed forms | a few paise/month |
| Deploys | GitHub Actions → AWS via OIDC (no stored AWS keys) | free |

No EC2, no NAT, no scheduler: recurring expenses are generated when you open the app, dated on their due day, so nothing runs (or bills) in the background.

CloudFront serves the site **and** forwards `/api/*` to API Gateway, so the app and API share one origin — no CORS setup.

```
spend-a-thon/
├── template.yaml              # the whole AWS stack (SAM)
├── infra/github-oidc.yaml     # one-time: deploy role for GitHub Actions
├── .github/workflows/deploy.yml
├── backend/                   # FastAPI app + pytest suite
│   ├── app/
│   │   ├── main.py            # app + Lambda handler
│   │   ├── services.py        # data access, recurring generation
│   │   ├── routers/           # auth, expenses, budgets, recurring, insights
│   │   └── ...
│   ├── tests/
│   └── scripts/create_local_table.py
└── frontend/                  # React app
    └── src/{pages,components}
```

## First-time deploy

1. **Create the GitHub repo** `spend-a-thon` and push this folder to `main`.
2. **Create the deploy role** (once): in the AWS console → CloudFormation → *Create stack* → upload `infra/github-oidc.yaml`. Enter your GitHub username. If this AWS account already has the GitHub OIDC provider (for example from another project), set `CreateOidcProvider` to `false`. Copy the `RoleArn` output.
3. **Repo settings → Secrets and variables → Actions**
   - Secret `AWS_ROLE_ARN` = the role ARN from step 2
   - Secret `JWT_SECRET` = a long random string, e.g. output of `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - (optional) Variable `AWS_REGION` – defaults to `ap-south-1` (Mumbai)
4. **Settings → Environments** → create an environment named `production` (the deploy job uses it).
5. Push to `main` (or run the workflow manually). Tests run first, then the stack deploys and the site uploads. The run summary shows the URL (`https://dxxxx.cloudfront.net`).

### Custom domain (optional, free eu.org name)

1. In **ACM, region us-east-1** (CloudFront requires it) request a public certificate for e.g. `spendathon.yourname.eu.org`, DNS validation. Add the CNAME it shows at your DNS host and wait until it's *Issued*.
2. Repo variables: `DOMAIN_NAME` = `spendathon.yourname.eu.org`, `CERTIFICATE_ARN` = the cert ARN. Re-run the workflow.
3. Add a CNAME `spendathon.yourname.eu.org → <CloudFrontDomain output>` at your DNS host.

## Load your existing loans & categories

`backend/scripts/seed.py` loads categories, cards and loans from a JSON file through the API (see `seed.example.json` for the format; your own `seed.json` is git-ignored so personal figures never reach GitHub). Sign up on the site first, then:

```bash
cd backend
python scripts/seed.py https://<your-site> you@example.com      # asks for your password
```

Re-running is safe: anything already there is skipped.

## Run locally

```bash
# 1. DynamoDB Local
docker run -d -p 8001:8000 amazon/dynamodb-local

# 2. API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DYNAMODB_ENDPOINT=http://localhost:8001 AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=ap-south-1
python scripts/create_local_table.py
uvicorn app.main:app --reload --port 8000      # docs at http://localhost:8000/api/docs

# 3. Web (new terminal)
cd frontend && npm install && npm run dev       # http://localhost:5173 (proxies /api to :8000)
```

Receipt uploads need a real S3 bucket; locally set `RECEIPTS_BUCKET` to a dev bucket you own (with your AWS credentials) or skip them — everything else works without it.

Tests: `cd backend && pytest -q` (uses moto, no AWS needed).

## Data model (one DynamoDB table)

| PK | SK | What |
|---|---|---|
| `USER#<id>` | `PROFILE` | name, email |
| `EMAIL#<email>` | `EMAIL` | login lookup + PBKDF2 password hash |
| `USER#<id>` | `EXP#<id>` | expense (`date_sk = <date>#<id>` on the `ByDate` index for month queries) |
| `USER#<id>` | `BUDGET#<category>` | monthly limit |
| `USER#<id>` | `REC#<id>` | recurring template + `last_generated_month` |
| `USER#<id>` | `CAT#<id>` | custom category |
| `USER#<id>` | `CARD#<id>` | credit card; `available_paise` changes in the same DynamoDB transaction as the expense |
| `USER#<id>` | `CPAY#<id>` | card bill payment / refund |
| `USER#<id>` | `LOAN#<id>` | EMI loan or borrowing, with its repayments |

Amounts are stored as integer paise. Every query is scoped to the caller's `USER#` partition, which is what keeps users' data separate. The table and receipts bucket have `Retain` deletion policies, so deleting the stack never deletes your data.

## Notes

- Login sessions last 30 days (`TOKEN_TTL_DAYS`). Changing `JWT_SECRET` logs everyone out.
- API Gateway throttles to 20 req/s (burst 50) as a cheap guard against abuse.
- Categories live in `backend/app/constants.py`; add one there and it appears everywhere.
