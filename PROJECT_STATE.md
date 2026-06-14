# Project state

_Last updated: 2026-06-12_

## What's shipped — TR repo (fincoach-tr)

### Phase 1a — Bank statement extraction
- Multi-bank PDF extractor (~1,940 lines)
- Banks supported: Halkbank V1+V2, Akbank, Ziraat (vector + scanned/OCR), Yapı Kredi, Kuveyt Türk, Türkiye Finans Katılım, generic fallback
- Balance-chain validated
- Source PDF stored as `Document` with `source='pdf_extraction_input'`
- Result XLSX stored as `Document` with `source='pdf_extraction_output'`
- Both default to `visible_to_client=False`

### Phase 1b — Data spine
- `accounts` — chart of accounts per client (TDHP SME subset)
- `accounting_periods` — monthly periods per client
- `transactions` — date, description, amount, account_id, period_id, source, approval_status, raw_reference
- All with RLS policy + isolation tests
- `app/spine/queries.py` — sole sanctioned analytical entry points

### Phase 1c — Transaction staging
- `app/spine/staging.py` turns parsed bank rows into `approval_status='unapproved'` transactions
- Auto-period creation, dedup, full `raw_reference` JSON, link to source PDF

### Phase 1d — Transaction review UI
- `/clients/{id}/transactions` — pending count, period switcher, inline edit, approve/bulk approve

### Phase 2 — Reports + KPIs
- Deterministic P&L: revenue, COGS, gross profit, operating expenses, net profit
- Prior-period and prior-year comparison columns
- Cash position: inflows, outflows, net change
- KPI tiles: revenue, net profit, gross margin %, transaction count, uncategorised %
- Top 3 expense categories
- Client portal Insights page (legacy — replaced in Phase 4)

### Phase 3 — Admin + assignments + external data
- `users.is_firm_admin` + `users.is_active` — firm admin boolean role
- `require_firm_admin` dependency; `is_active` checked on every authenticated request
- User management UI at `/manage/*` (list, add, edit, disable, audit log)
- `client_assignments` table — accountant→client scoped visibility
- `visible_clients_for(user, db)` helper + `get_visible_client_or_404` (404 not 403)
- Transitive scoping: tasks, docs, notes, transactions, reports, snapshots
- `tasks.assigned_to_user_id` — one task per accountant per template; ad-hoc task creation
- `period_snapshots` — aggregated period data: all financial fields + `expense_breakdown` JSONB
- Manual snapshot entry UI at `/clients/{id}/snapshots/{period_id}`
- Snapshot-first reporting: approved snapshot wins over transactions; source banner shown
- `admin_audit_log` — RLS-scoped, written on all admin actions
- 37/37 tests green

## What's shipped — UK repo (fincoach-uk)

UK repo is at **Phase 2**. Phase 3 not yet applied.

To bring UK to Phase 3 parity: give Claude Code the Phase 3 handoff brief with
instruction "TR repo is the reference implementation — apply same changes, English
UI strings, GBP currency, no VKN/TCKN."

## What's not shipped (deliberately)

- CSRF protection, password reset, email verification, login rate limiting,
  server-side session revocation — security hardening sprint (before beta)
- Report parsers (ETASQL, Logo, Mikro, Netsis) — awaiting real export file samples
- `revoked_sessions` blocklist — deferred to security hardening sprint
- Last-login timestamp on User — not in schema yet
- Notification system for task assignment — not planned
- AI categorization — Phase 4 in original roadmap, now Phase 5+ (roadmap resequenced)
- n8n AI agent integration — Phase 6
- Phase 4 features (currently being built — see HANDOFF_PHASE_4.md)

## Tests (TR repo)

37/37 green against real Postgres 16:
- `tests/test_auth.py` — 3 tests
- `tests/test_tenancy.py` — 19 tests
- `tests/test_phase3.py` — 15 tests

## How to run

```bash
cp .env.example .env
docker compose up --build
docker compose exec app python -m scripts.seed_demo
```
Open http://localhost:8000

## How to reset

```bash
docker compose down -v
docker compose up --build
docker compose exec app python -m scripts.seed_demo
```

## Demo logins (TR — password `demo1234`)

| Role | Email |
|------|-------|
| Accountant (firm admin) | ayse@aydinmusavirlik.com |
| Accountant (non-admin) | mehmet@aydinmusavirlik.com |
| Client (Boğaziçi Kahve) | bogazici@kahveatolyesi.com |
| Client (Anadolu Tekstil) | finans@anadolutekstil.com.tr |
| Client (Ege Yoga) | merhaba@egeyoga.com |
| Client (Pixel Tasarım) | iletisim@pixeltasarim.co |
| Superuser | admin@fincoach.dev |

Mehmet sees only Boğaziçi Kahve + Ege Yoga (assigned clients only).
Anadolu Tekstil has an approved manual snapshot with full expense breakdown.
