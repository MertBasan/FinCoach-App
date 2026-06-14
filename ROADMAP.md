# Roadmap

## Phase 1 — Foundation [DONE, TR repo]
- Multi-tenant data model with RLS
- Three user roles (superuser, accountant, client)
- Client management, monthly task tracker, documents, notes
- PDF → Excel bank extraction
- 11 services as Coming Soon cards

## Phase 2 — Reports + KPIs [DONE, TR repo]
- Data spine: accounts, periods, transactions
- Bank extraction stages transactions for approval
- Transaction review UI
- Deterministic P&L, cash position, KPI dashboard (accountant + client portal)

## Phase 3 — Admin + assignments + external data [DONE, TR repo only]
- Firm admin role + user management
- Client-accountant assignments (scoped visibility)
- Task assignments to individual accountants
- Period snapshots (manual data entry for external-system clients)
- Audit log for admin actions

## Phase 4 — SME Monthly Insights Portal [CURRENT, TR repo]
See `HANDOFF_PHASE_4.md` (in fincoach-tr/docs/).
- Accountant-side publish action with editable note to client
- AR/AP fields exposed on snapshot entry form
- SME portal monthly page (`/portal/monthly`) — month picker, KPI tiles,
  deterministic comparison labels, tabbed detail sections
- Tabs: Gelir Tablosu, Nakit Akışı, Gider Analizi, Alacak & Borç
- SME sees only published snapshots
- Portal navigation updated (İstatistikler replaces old insights link)

## Phase 5 — ETASQL file import [NEXT, TR repo]
Pending: real ETASQL export file from accountant contact.
- Upload ETASQL export → auto-populate snapshot fields
- Accountant reviews pre-filled snapshot, approves, publishes
- Same publish → portal flow as Phase 4
- Source: `eta_sql_import`

## Phase 6 — n8n AI agent integration
- FinCoach exposes a fact-sheet API endpoint (approved published snapshot as JSON)
- n8n reads the fact sheet, generates plain-Turkish insight text
- Insight text surfaces in the SME portal monthly page
- Accountant reviews/approves AI commentary before client sees it
- AI never produces numbers — only narrates the fact sheet

## Phase 7 — AI categorization (originally Phase 4)
- AI suggests chart-of-accounts categories for unapproved transactions
- Bulk approve/reject flow
- `approval_status='ai_suggested'` gets its first real use

## Phase 8+ — Remaining services (order TBD by accountant feedback)
- Bank reconciliation
- Accounts receivable (aged debtors, payment chasing)
- Accounts payable (supplier invoices, due dates)
- VAT/KDV prep (Turkish KDV beyannamesi)
- Payroll ingestion
- Anomaly detection

## UK repo catch-up
UK repo is at Phase 2. Bring to Phase 3 parity as a separate builder session
before Phase 5 begins (or earlier if needed for UK beta demos).
Brief: "TR repo is the reference implementation — apply same changes, English UI,
GBP currency, no VKN/TCKN."

## Security hardening (before any real firm onboards)
Dedicated sprint — must complete before beta:
- CSRF on all forms
- Password reset (email-based)
- Email verification on registration
- Login rate limiting
- Server-side session revocation

## How phases are decided
After each phase ships, demo to the accountant contacts and to SME owners.
Listen for which gap they'd actually pay to close. Their answer overrides this
roadmap. The roadmap is a default, not a contract.
