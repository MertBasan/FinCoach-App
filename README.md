# FinCoach

Workflow automation for accountants serving SMEs. This build covers:

- Multi-tenant foundation (Postgres + Row Level Security)
- Three user roles: Superuser, Accountant, Client
- Monthly task tracker per client
- Client management, notes, documents
- **Bank-statement PDF extractor** with dedicated parsers (Halkbank V1+V2, Akbank, Ziraat vector+OCR, Yapı Kredi, Kuveyt Türk, Türkiye Finans Katılım, generic fallback). Balance-chain validated.
- **Data spine** — chart of accounts (default UK SME), monthly accounting periods, transactions with approval workflow
- **Transaction review & approve UI** per client/period
- **Financial Reporting** — P&L with prior-period and prior-year comparison, cash position
- **KPI Dashboard** — revenue, net profit, gross margin, top expense categories, shared between accountant and client portal

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Wait for `Application startup complete`, then in another terminal:

```bash
docker compose exec app python -m scripts.seed_demo
```

Open <http://localhost:8000>.

## Demo logins

All passwords: **`demo1234`**

| Role | Email | Lands at |
| --- | --- | --- |
| Accountant | `sarah@anderson.co` | Dashboard |
| Client (Maple, GBP) | `owner@maplecafe.co.uk` | Portal — has seeded transactions and reports |
| Client (Northwind, EUR) | `finance@northwind.de` | Portal — empty state |
| Client (Sunset, USD) | `hi@sunsetyoga.com` | Portal — empty state |
| Client (Bright Pixels, GBP) | `ops@brightpixels.io` | Portal — empty state |
| Superuser | `admin@fincoach.dev` | Platform admin |

## The demo walk-through

1. **Sign in as Sarah** (accountant).
2. **Click into Maple Café Ltd.** Real address, currency, monthly task progress, recent documents, recent notes.
3. **Click Reports.** Real P&L with prior-month comparison, gross margin %, top expense categories. All numbers come from approved transactions only.
4. **Click Review transactions.** 2 pending rows, 12 approved. Try editing one (description, amount, account dropdown from the chart of accounts), save, then bulk-approve the rest.
5. **Click Services.** 3 Available cards (Bank → Excel, Financial Reporting, KPI Dashboard) plus 9 Coming Soon.
6. **Open Bank Statement → Excel.** Pick a client, upload a real bank statement PDF. You'll get an XLSX back; the source PDF and output XLSX are both filed to the client's documents; for trusted bank parsers the rows are staged as unapproved transactions for review.
7. **Log out, log in as the Maple client** (`owner@maplecafe.co.uk`). Their Insights page shows the same KPIs Sarah just saw — but only for transactions Sarah has approved.

## Architecture

```
app/
├── main.py              FastAPI entrypoint
├── config.py            settings
├── db/                  SQLAlchemy session + RLS helper + models
├── auth/                bcrypt + signed-cookie sessions, role guards
├── reference/           currencies + countries
├── dashboard/           accountant home
├── clients/             list, create, detail
├── notes/               firm + client-linked notes
├── tasks/               monthly task templates and board
├── documents/           upload, list, download, visibility toggle
├── services/            services hub + bank-statement extraction (~1,950 LOC)
├── transactions/        review & approve UI
├── spine/               accounts, periods, staging, approved-only queries
├── reporting/           P&L, cash, KPIs (deterministic Python — no AI)
├── portal/              client-facing pages
├── admin/               superuser overview
└── ui/                  templates + CSS
```

## Multi-tenant isolation

Row-Level Security on every tenant-scoped table:
`clients`, `notes`, `task_templates`, `client_monthly_tasks`, `documents`,
`accounts`, `accounting_periods`, `transactions`.

The `app.current_firm_id` Postgres setting is set per-request by
`get_current_user`. The setting is **session-scoped** (`is_local=false`) so
it survives commits within a request. `get_db` clears the setting in its
`finally` block to prevent stale values leaking between requests on a
pooled connection.

The contract is documented and tested:

- Cross-firm read isolation (one test per table)
- Cross-firm write rejection
- Cross-firm update affects zero rows
- No-context denies all access
- Setting survives `COMMIT`
- Setting survives `ROLLBACK` (when the setting itself was committed earlier)
- Explicit clear blocks subsequent access
- Pool reset on session close

22 tests, all green against real Postgres.

## Approval gating

Every reporting / KPI / analytical query goes through
`app/spine/queries.py`. These helpers bake in `approval_status='approved'`
as a non-negotiable filter. Adding new analytical code: import a helper
from there, do not write a raw `select(Transaction)`. AI-touched records
(coming in Phase 3) will land as `approval_status='ai_suggested'` and
will not appear in reports until an accountant signs them off.

## Running tests

```bash
docker compose up -d db
docker compose exec db createdb -U fincoach fincoach_test
docker compose run --rm -e POSTGRES_DB=fincoach_test app pytest -v
```

22 tests must pass. If `test_firm_context_survives_commit` ever goes red,
the tenancy primitive has regressed and reports are at risk of silently
returning zero rows. Stop and fix before merging.

## Resetting the demo

Idempotent:

```bash
docker compose exec app python -m scripts.seed_demo
```

## Service status (from `app/services/catalog.py`)

**Available:**
- Bank Statement → Excel (with transaction staging for trusted bank parsers)
- Financial Reporting (per-client Reports tab)
- KPI Dashboard (per-client Reports tab + client portal Insights)

**Coming Soon** (placeholders on the Services page):
- Transaction Categorization
- Bank Reconciliation
- Accounts Receivable
- Accounts Payable
- VAT & Tax Support
- Payroll Support
- AI Commentary
- Anomaly Detection
- Workflow Automation
