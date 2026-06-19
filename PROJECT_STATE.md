# Project state

_Last updated: 2026-06-14_

## What's shipped — TR repo (fincoach-tr)

### Phase 1a — Bank statement extraction
- Multi-bank PDF extractor (~1,940 lines)
- Banks: Halkbank V1+V2, Akbank, Ziraat (vector + scanned/OCR), Yapı Kredi, Kuveyt Türk, Türkiye Finans Katılım, generic fallback
- Balance-chain validated; source PDF + result XLSX stored as Documents

### Phase 1b-1d — Data spine + transaction review
- Chart of accounts (TDHP SME subset), accounting periods, transactions — all RLS-scoped
- Bank extraction stages rows as unapproved transactions
- Transaction review UI: inline edit, approve/unapprove, bulk approve

### Phase 2 — Reports + KPIs
- Deterministic P&L, cash position, KPI dashboard
- Prior-period and prior-year comparison columns
- Client portal KPI view (superseded by Phase 4 portal)

### Phase 3 — Admin + assignments + external data
- `users.is_firm_admin` + `is_active`; `require_firm_admin` dependency
- User management UI at `/manage/*`; `admin_audit_log` table
- `client_assignments` — scoped visibility; `visible_clients_for()` helper
- Transitive scoping: tasks, docs, notes, transactions, reports, snapshots → 404 not 403
- `tasks.assigned_to_user_id`; ad-hoc task creation
- `period_snapshots` — all financial fields + `expense_breakdown` JSONB; manual entry UI
- Snapshot-first reporting with source banner

### Phase 4 — SME monthly insights portal
- `period_snapshots` gains `published`, `published_at`, `published_by_id`, `accountant_note`
- AR/AP fields exposed on snapshot entry form
- Accountant publish flow: "Müşteriye Yayınla" button with editable default note
- `/portal/monthly` — month picker (published only), accountant note card, 3 KPI tiles
  with deterministic comparison labels, 4 tabs (Gelir Tablosu / Nakit Akışı /
  Gider Analizi / Alacak & Borç)
- `app/portal/insights.py` — `compute_comparison_labels()` deterministic helper
- Portal sidebar: "İstatistikler" replaces old insights link
- 48/48 tests green

## What's in progress — Phase 5 (TR repo)

See `docs/HANDOFF_PHASE_5.md` in the repo.
- New "İşlem İnceleme" sidebar item: `/transactions` cross-client pending view
- `/api/v1/assistant/context` endpoint — approved transactions + snapshot as JSON
- `/portal/assistant` becomes a real Turkish-language AI chat UI
- n8n webhook integration (n8n workflow built manually by developer)
- No LLM calls inside FinCoach; n8n handles LLM orchestration

## What's shipped — UK repo (fincoach-uk)

UK repo is at **Phase 2**. Phases 3 and 4 not yet applied.

To bring to Phase 3 parity: builder session with HANDOFF_PHASE_3.md,
instruction "TR is the reference implementation — English UI, GBP, no VKN/TCKN."

## What's not shipped (deliberately)

- CSRF, password reset, email verification, login rate limiting, session revocation
  — security hardening sprint (must complete before beta)
- ETASQL / file parsers — Phase 6, pending real export file
- Conversation history persistence — Phase 6+
- Document embedding (pgvector RAG) — Phase 6+
- AI categorization of transactions — Phase 7
- All remaining service catalog items (reconciliation, AR, AP, VAT, payroll, etc.)

## Tests (TR repo, Phase 4 complete)

48/48 green:
- `tests/test_auth.py` — 3
- `tests/test_tenancy.py` — 19
- `tests/test_phase3.py` — 15
- `tests/test_phase4.py` — 11

## How to run

```bash
cp .env.example .env        # set N8N_WEBHOOK_URL for assistant feature
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

Boğaziçi Kahve has 18 approved transactions (Haziran 2026) — primary test client
for the AI assistant once n8n is connected.
