"""
Catalog of services offered by FinCoach. Each entry says whether the service
is currently available or coming soon, and where it lives in the app.
"""

SERVICES = [
    {
        "slug": "pdf_extraction",
        "name": "Bank Statement → Excel",
        "category": "Ingestion",
        "status": "available",
        "url": "/services/pdf-extraction",
        "short": "Extract bank statement PDFs into validated transaction rows.",
        "long": "Accountant-grade extraction for bank statements. Dedicated parsers for "
                "Halkbank, Akbank, Ziraat (vector + scanned/OCR), Yapı Kredi, Kuveyt Türk, "
                "and Türkiye Finans Katılım; generic fallback for other banks. Every row "
                "is verified by balance-chain validation before output. Both source PDF "
                "and resulting Excel are filed to the client's documents.",
        "icon": "📄",
    },
    {
        "slug": "transaction_categorization",
        "name": "Transaction Categorization",
        "category": "Bookkeeping",
        "status": "coming_soon",
        "url": None,
        "short": "Auto-suggest categories for bank lines and invoices.",
        "long": "Rules engine + AI assist proposes the correct expense account. "
                "Accountant approves in bulk. Learns from your corrections.",
        "icon": "🏷️",
    },
    {
        "slug": "bank_reconciliation",
        "name": "Bank Reconciliation",
        "category": "Bookkeeping",
        "status": "coming_soon",
        "url": None,
        "short": "Match bank lines to invoices and ledger entries.",
        "long": "Detects duplicates, missing entries, and unmatched transactions.",
        "icon": "🔁",
    },
    {
        "slug": "financial_reporting",
        "name": "Financial Reporting",
        "category": "Reporting",
        "status": "available",
        "url": None,  # Per-client: surfaced under client detail page
        "short": "P&L, cost-of-sales, operating expenses, with prior-period and prior-year comparison.",
        "long": "Computed deterministically from approved transactions only. Open any client and "
                "click Reports.",
        "icon": "📊",
    },
    {
        "slug": "kpi_dashboard",
        "name": "KPI Dashboard",
        "category": "Reporting",
        "status": "available",
        "url": None,
        "short": "Revenue, net profit, gross margin, top 3 expense categories per client.",
        "long": "Live KPIs on the Reports tab for each client. Same numbers shown to the client "
                "on their portal Insights page.",
        "icon": "📈",
    },
    {
        "slug": "ar",
        "name": "Accounts Receivable",
        "category": "Cash flow",
        "status": "coming_soon",
        "url": None,
        "short": "Track unpaid invoices and chase actions.",
        "long": "Aged debtors report, payment reminders, client statements.",
        "icon": "💷",
    },
    {
        "slug": "ap",
        "name": "Accounts Payable",
        "category": "Cash flow",
        "status": "coming_soon",
        "url": None,
        "short": "Supplier invoices, due dates, duplicate detection.",
        "long": "Track what's owed to suppliers and schedule payments.",
        "icon": "📤",
    },
    {
        "slug": "vat",
        "name": "VAT & Tax Support",
        "category": "Compliance",
        "status": "coming_soon",
        "url": None,
        "short": "VAT calculations, filing prep, tax summaries.",
        "long": "Quarterly VAT support, corporation tax prep, year-end packs.",
        "icon": "🏛️",
    },
    {
        "slug": "payroll",
        "name": "Payroll Support",
        "category": "Compliance",
        "status": "coming_soon",
        "url": None,
        "short": "Payslip ingestion, payroll journals, cost analytics.",
        "long": "Bring payroll outputs in, post to the ledger, analyse cost by team.",
        "icon": "👥",
    },
    {
        "slug": "ai_commentary",
        "name": "AI Commentary",
        "category": "Intelligence",
        "status": "coming_soon",
        "url": None,
        "short": "Plain-English narrative on monthly numbers.",
        "long": "Strictly grounded on calculated figures — never invented. "
                "Accountant reviews and approves before client sees.",
        "icon": "💬",
    },
    {
        "slug": "anomaly_detection",
        "name": "Anomaly Detection",
        "category": "Intelligence",
        "status": "coming_soon",
        "url": None,
        "short": "Flag unusual transactions for accountant review.",
        "long": "Customer concentration, expense spikes, duplicate suppliers, "
                "and other operational anomalies surfaced automatically.",
        "icon": "🚩",
    },
    {
        "slug": "workflow_automation",
        "name": "Workflow Automation",
        "category": "Operations",
        "status": "coming_soon",
        "url": None,
        "short": "Monthly close checklists, reminders, approvals.",
        "long": "You're already using the monthly task tracker for this. "
                "Approval flows, recurring imports, and email reminders come next.",
        "icon": "⚙️",
    },
]


def by_slug(slug: str):
    for s in SERVICES:
        if s["slug"] == slug:
            return s
    return None
