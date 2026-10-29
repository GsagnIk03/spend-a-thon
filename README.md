# spend-a-thon

Personal expense tracker. Anyone can sign up; every user sees only their own expenses.

- **Dashboard** – month total, change vs last month, budget left, daily average, category donut, day-by-day and 6-month charts, biggest expenses
- **Expenses** – add / edit / delete, search, category and payment-method filters, grouped by day
- **Budgets** – monthly limit per category with progress (amber at 85%, red when over)
- **Recurring** – rent, EMIs, subscriptions; added automatically on their due day (day 29–31 falls back to the month's last day), pause / resume, optional end month
- **Insights** – any period (this month → 12 months / custom): spend per category with counts, averages and month-by-month bars, and per payment method (Cash, Google Pay, PhonePe, each credit card…); tap a row to see the actual transactions
- **Custom categories** – add your own (e.g. Cigarettes, Tea & Snacks) from the expense form or the Categories screen
- **Credit cards** – limit, available balance, utilisation, statement/due days. Spends on a card reduce its available balance automatically (edits, card switches and deletes are reversed correctly); record bill payments/refunds or sync the balance with your bank app
- **Loans & borrowings** – EMI loans work out EMIs paid/due, amount paid, remaining and closure date from the schedule, so they stay current on their own; personal borrowings track repayments. Optionally log each EMI as an expense on its date
- **CSV export** – any range up to 24 months, opens cleanly in Excel / Google Sheets (includes the card used)
- **Android app** + iPhone home-screen app (see *Phones*)
- INR only, Asia/Kolkata time, mobile-first (bottom tab bar, installable to home screen)

## Stack & cost (all free tiers, no card needed)

| Part | Service |
|---|---|
| Frontend | React + TypeScript (Vite), served by **Vercel** |
| API | FastAPI as a **Vercel** Python function (`api/index.py`), same domain as the site — no CORS |
| Database | **Neon** Postgres (free: 1 GB, scales to zero when idle, wakes automatically) |
| CI + Android app | **GitHub Actions** (tests on every push; builds the APK) |

Vercel deploys automatically on every push to `main`. Recurring expenses and loan EMIs are generated when you open the app, dated on their due day, so nothing needs to run in the background.

```
spend-a-thon/
├── vercel.json               # build + routing (/api/* → Python function, rest → React app)
├── api/index.py              # Vercel entrypoint → backend/app
├── requirements.txt          # Python deps for the function
├── backend/
│   ├── app/                  # FastAPI: routers/, services.py (logic), db.py (schema)
│   ├── tests/                # pytest, runs against a real Postgres
│   └── scripts/seed.py       # load categories / cards / loans through the API
├── frontend/                 # React app + Capacitor config for Android
└── .github/workflows/ci.yml  # tests + Android build
```

## First-time deploy

1. **Push to GitHub** – create a repo `spend-a-thon` (private is fine) and push this folder to `main`.
2. **Vercel** – sign in at vercel.com with GitHub → *Add New… → Project* → import `spend-a-thon`. Leave every setting as detected (`vercel.json` drives the build) → **Deploy**. The first deploy will show API errors until the database is connected — that's expected.
3. **Neon database** – in the Vercel project: **Storage → Create Database → Neon** (free plan, region **Singapore** to sit next to the API) → connect it to the project. This adds `DATABASE_URL` automatically. Tables are created on first use.
4. **Secret** – Vercel project → **Settings → Environment Variables** → add `JWT_SECRET` (Production) = a long random string. PowerShell:
   `$b = New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b)`
5. **Redeploy** – *Deployments → ⋯ → Redeploy* so the new variables apply. Open `https://<project>.vercel.app`, **sign up**.
6. **Load your loans** – `python backend/scripts/seed.py https://<project>.vercel.app <your-email>`.
7. **Android build** – GitHub repo → **Settings → Secrets and variables → Actions → Variables** → add `SITE_URL` = `https://<project>.vercel.app`. Then *Actions → CI & Android app → Run workflow*.

## Phones

**Android** – every push to `main` (once `SITE_URL` is set) publishes the app at
`https://github.com/<you>/spend-a-thon/releases/download/android-latest/spend-a-thon.apk`.
Open that on the phone (if the repo is private, sign in to GitHub in the phone's browser first), download, tap to install and allow "install unknown apps" for your browser when asked. The app is a native shell around the live site, so web updates reach it instantly — you only need a new APK if the app shell itself changes.

*Signing (recommended, once):* without these secrets the APK is debug-signed with a key cached by GitHub, which expires after 7 days without a build — after that a new APK won't install over the old one (uninstall first; your data is safe on the server). To fix the key permanently, on your PC (keytool comes with any JDK / Android Studio):

```powershell
keytool -genkeypair -v -keystore spendathon.jks -alias spendathon -keyalg RSA -keysize 2048 -validity 10000
[Convert]::ToBase64String([IO.File]::ReadAllBytes("spendathon.jks")) | Set-Clipboard
```

then add secrets `ANDROID_KEYSTORE_BASE64` (paste), `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_PASSWORD` (same passwords you chose) and `ANDROID_KEY_ALIAS` = `spendathon`. Keep `spendathon.jks` safe — it's what lets future APKs update the installed app.

**iPhone** – Apple doesn't allow installing app files outside the App Store without a paid developer account, so on iOS use the web app: open the site in **Safari → Share → Add to Home Screen**. It gets its own icon and opens full-screen like an app. (A real App Store / TestFlight build is possible later with an Apple Developer account, US$99/year, using the same Capacitor setup: `npx cap add ios` on a Mac.)

## Custom domain (optional, free eu.org name)

Vercel project → **Settings → Domains** → add e.g. `spendathon.yourname.eu.org`, then create the CNAME record Vercel shows at your DNS host. HTTPS is automatic. Update the `SITE_URL` variable and re-run the Android build so the app points at the new address.

## Load your existing loans & categories

`backend/scripts/seed.py` loads categories, cards and loans from a JSON file through the API (see `seed.example.json` for the format; your own `seed.json` is git-ignored so personal figures never reach GitHub). Sign up on the site first, then:

```bash
cd backend
python scripts/seed.py https://<your-site> you@example.com      # asks for your password
```

Re-running is safe: anything already there is skipped.

## Run locally

```bash
# 1. Postgres
docker run -d --name spendathon-db -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=spendathon postgres:16

# 2. API (from the repo root)
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r backend/requirements-dev.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/spendathon   # PowerShell: $env:DATABASE_URL="..."
uvicorn api.index:app --reload --port 8000              # docs at http://localhost:8000/api/docs

# 3. Web (new terminal)
cd frontend && npm install && npm run dev               # http://localhost:5173 (proxies /api to :8000)
```

Tests: `cd backend && TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/spendathon pytest -q` (the suite drops and recreates the tables, so point it at a throwaway database).

## Data model (Postgres)

`users`, `categories` (custom ones), `expenses`, `budgets`, `recurring`, `cards`, `card_payments`, `loans`, `loan_repayments` — defined in `backend/app/db.py`. Every user-data table has `user_id`, and every query filters on it: that is what keeps each person's data private. Amounts are integer paise. A card's `available_paise` changes in the same database transaction as the expense that uses it.

## Notes

- Login sessions last 30 days (`TOKEN_TTL_DAYS`). Changing `JWT_SECRET` logs everyone out.
- Categories live in `backend/app/constants.py`; add one there and it appears everywhere.
