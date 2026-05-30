"""
Demo data seed. Creates:
  - Accounting firm "Anderson & Co Accountants"
  - 1 accountant user (sarah@anderson.co / demo1234)
  - 4 SME clients with addresses, currencies, monthly tasks
  - 4 client portal users (one per client)
  - 1 superuser (admin@fincoach.dev / demo1234)
  - Sample notes (firm-wide + client-specific)
  - Sample documents (text fixtures, marked client-visible where useful)

Run inside the app container:
    docker compose run --rm app python -m scripts.seed_demo

Idempotent: it deletes existing demo data first.
"""
import os
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

# Allow running as `python -m scripts.seed_demo` from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal, set_firm_context
from app.db.models import (
    AccountingFirm, User, Client, Note,
    TaskTemplate, ClientMonthlyTask, Document,
)
from app.auth.security import hash_password
from app.tasks.workflow import (
    current_period, previous_period, generate_tasks_for_client_period,
)


FIRM_NAME = "Anderson & Co Accountants"
ACCOUNTANT_EMAIL = "sarah@anderson.co"
ADMIN_EMAIL = "admin@fincoach.dev"
PASSWORD = "demo1234"

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/code/uploaded_files"))


CLIENT_SEEDS = [
    {
        "name": "Maple Café Ltd",
        "industry": "Hospitality",
        "base_currency": "GBP",
        "address_line1": "12 High Street",
        "city": "Manchester", "postcode": "M1 4DN", "country_code": "GB",
        "submission_day_of_month": 7,
        "client_user_email": "owner@maplecafe.co.uk",
        "client_user_name": "James Patel",
    },
    {
        "name": "Northwind Trading",
        "industry": "Wholesale",
        "base_currency": "EUR",
        "address_line1": "Karl-Liebknecht-Str. 29",
        "city": "Berlin", "postcode": "10178", "country_code": "DE",
        "submission_day_of_month": 5,
        "client_user_email": "finance@northwind.de",
        "client_user_name": "Anna Müller",
    },
    {
        "name": "Sunset Yoga Studio",
        "industry": "Health & Wellness",
        "base_currency": "USD",
        "address_line1": "1457 Mission Street",
        "city": "San Francisco", "postcode": "94103", "country_code": "US",
        "submission_day_of_month": 10,
        "client_user_email": "hi@sunsetyoga.com",
        "client_user_name": "Priya Shah",
    },
    {
        "name": "Bright Pixels Studio",
        "industry": "Creative Agency",
        "base_currency": "GBP",
        "address_line1": "8 Brick Lane",
        "city": "London", "postcode": "E1 6RF", "country_code": "GB",
        "submission_day_of_month": 12,
        "client_user_email": "ops@brightpixels.io",
        "client_user_name": "Tom Reilly",
    },
]


DEFAULT_TEMPLATES = [
    ("Collect bank statements", "ingestion", 5, "Request bank statements for the prior month from the client."),
    ("Collect invoices & receipts", "ingestion", 7, "Receive and verify all sales invoices and expense receipts."),
    ("Categorise transactions", "bookkeeping", 12, "Code all transactions to the correct expense accounts."),
    ("Bank reconciliation", "bookkeeping", 14, "Reconcile bank statements against the ledger."),
    ("Aged receivables review", "receivables", 16, "Review overdue invoices and flag chase actions."),
    ("VAT preparation", "tax", 20, "Calculate VAT liability and prepare return."),
    ("Monthly management report", "reporting", 25, "Produce and send the monthly report to the client."),
]


def main():
    db: Session = SessionLocal()
    try:
        wipe_existing(db)
        firm = create_firm_with_accountant(db)
        create_superuser(db)
        create_task_templates(db, firm)
        create_clients_and_users(db, firm)
        create_sample_notes(db, firm)
        create_sample_documents(db, firm)

        # Generate this month and last month's tasks for every client,
        # mark some as complete to make the dashboard look lived-in.
        seed_task_progress(db, firm)

        # Spine: approved transactions for Maple Café so reports are non-empty.
        # Other clients stay with empty spines so the demo can show both states.
        seed_demo_transactions(db, firm)

        db.commit()
        print("\n✅ Demo data seeded successfully.\n")
        print(f"  Accountant login: {ACCOUNTANT_EMAIL} / {PASSWORD}")
        print(f"  Superuser login:  {ADMIN_EMAIL} / {PASSWORD}")
        print(f"  Client logins:")
        for c in CLIENT_SEEDS:
            print(f"    {c['client_user_email']} / {PASSWORD}    ({c['name']})")
        print("\n  Visit http://localhost:8000 and sign in.")
    finally:
        db.close()


def wipe_existing(db: Session):
    """Remove existing demo records (idempotent)."""
    print("Cleaning up any existing demo data…")
    set_firm_context(db, None)
    firm = db.scalar(select(AccountingFirm).where(AccountingFirm.name == FIRM_NAME))
    if firm:
        # Set firm context so we can delete RLS-protected rows
        set_firm_context(db, str(firm.id))
        # Spine cascades via FK ON DELETE CASCADE on client_id, but
        # transactions reference periods via RESTRICT. Order: txs, periods, accounts.
        from app.db.models import Account as _A, AccountingPeriod as _P, Transaction as _T
        db.execute(delete(_T).where(_T.firm_id == firm.id))
        db.execute(delete(_P).where(_P.firm_id == firm.id))
        db.execute(delete(_A).where(_A.firm_id == firm.id))
        # Client portal users
        clients = db.scalars(select(Client).where(Client.firm_id == firm.id)).all()
        client_ids = [c.id for c in clients]
        if client_ids:
            db.execute(delete(User).where(User.client_id.in_(client_ids)))
        set_firm_context(db, None)
        db.delete(firm)
    su = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if su:
        db.delete(su)
    db.flush()


def create_firm_with_accountant(db: Session) -> AccountingFirm:
    firm = AccountingFirm(id=uuid4(), name=FIRM_NAME)
    db.add(firm)
    db.flush()

    user = User(
        firm_id=firm.id,
        email=ACCOUNTANT_EMAIL,
        name="Sarah Anderson",
        password_hash=hash_password(PASSWORD),
        role="accountant",
    )
    db.add(user)
    db.flush()
    set_firm_context(db, str(firm.id))
    print(f"Created firm: {firm.name}")
    return firm


def create_superuser(db: Session):
    set_firm_context(db, None)
    su = User(
        firm_id=None,
        email=ADMIN_EMAIL,
        name="Platform Admin",
        password_hash=hash_password(PASSWORD),
        role="superuser",
    )
    db.add(su)
    db.flush()
    print("Created superuser")


def create_task_templates(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    for name, category, day, description in DEFAULT_TEMPLATES:
        db.add(TaskTemplate(
            firm_id=firm.id, name=name, category=category,
            day_of_month=day, description=description, active=True,
        ))
    db.flush()
    print(f"Created {len(DEFAULT_TEMPLATES)} task templates")


def create_clients_and_users(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    for seed in CLIENT_SEEDS:
        client = Client(
            firm_id=firm.id,
            name=seed["name"], industry=seed["industry"],
            base_currency=seed["base_currency"],
            address_line1=seed.get("address_line1"),
            city=seed.get("city"),
            postcode=seed.get("postcode"),
            country_code=seed.get("country_code"),
            submission_day_of_month=seed["submission_day_of_month"],
        )
        db.add(client)
        db.flush()

        # Default chart of accounts for this client
        from app.spine.chart_of_accounts import seed_default_coa
        seed_default_coa(db, firm.id, client.id)

        # Client portal user
        portal_user = User(
            firm_id=firm.id,
            client_id=client.id,
            email=seed["client_user_email"],
            name=seed["client_user_name"],
            password_hash=hash_password(PASSWORD),
            role="client",
        )
        db.add(portal_user)
        seed["_client_id"] = client.id  # stash for later
    db.flush()
    print(f"Created {len(CLIENT_SEEDS)} clients with portal users")


def create_sample_notes(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    accountant = db.scalar(select(User).where(User.email == ACCOUNTANT_EMAIL))

    firmwide = [
        ("Q3 deadline reminder", "VAT submissions due by month-end. Confirm with all clients by 20th."),
        ("New software subscription", "Upgraded to Pro tier — added to firm overheads."),
    ]
    for title, body in firmwide:
        db.add(Note(firm_id=firm.id, author_id=accountant.id, title=title, body=body))

    client_notes = [
        (CLIENT_SEEDS[0]["_client_id"], "Café equipment purchase",
         "Owner mentioned planning to buy new espresso machine in Q4. Confirm capital allowance treatment when invoice arrives."),
        (CLIENT_SEEDS[1]["_client_id"], "EU VAT registration",
         "Northwind is approaching German VAT threshold. Discuss registration timing on next call."),
        (CLIENT_SEEDS[2]["_client_id"], "Studio expansion",
         "Considering second location in Oakland. Will need cash flow forecast for lender."),
        (CLIENT_SEEDS[3]["_client_id"], "Late receipts",
         "Client tends to submit expense receipts 1-2 weeks late. Set up monthly reminder."),
    ]
    for cid, title, body in client_notes:
        db.add(Note(firm_id=firm.id, author_id=accountant.id, client_id=cid, title=title, body=body))
    print(f"Created {len(firmwide) + len(client_notes)} notes")


def create_sample_documents(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    accountant = db.scalar(select(User).where(User.email == ACCOUNTANT_EMAIL))
    period = current_period()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = [
        (CLIENT_SEEDS[0]["_client_id"], "April_bank_statement.pdf", "bank_statement",
         "Sample bank statement content for Maple Café.\nThis is a placeholder fixture for the demo.\n", False),
        (CLIENT_SEEDS[0]["_client_id"], "March_management_report.pdf", "report",
         "Maple Café — March 2026 Management Report\nRevenue, expenses, and commentary.\n", True),
        (CLIENT_SEEDS[1]["_client_id"], "Q1_invoices.zip", "invoice",
         "Northwind Q1 invoices placeholder.", False),
        (CLIENT_SEEDS[1]["_client_id"], "VAT_summary_2026Q1.pdf", "report",
         "Northwind VAT summary Q1 2026.", True),
        (CLIENT_SEEDS[2]["_client_id"], "Studio_payroll_April.csv", "payroll",
         "name,role,gross\nA. Alvarez,Instructor,2400\nB. Chen,Instructor,2200", False),
        (CLIENT_SEEDS[2]["_client_id"], "Cash_flow_forecast.pdf", "report",
         "Sunset Yoga — 12-month cash flow forecast (draft).", True),
        (CLIENT_SEEDS[3]["_client_id"], "Expense_receipts_April.zip", "receipt",
         "Bright Pixels April expense receipts.", False),
    ]

    for cid, name, doc_type, content, visible in fixtures:
        storage_dir = UPLOAD_DIR / str(firm.id) / str(cid)
        storage_dir.mkdir(parents=True, exist_ok=True)
        path = storage_dir / f"{uuid4().hex}_{name}"
        path.write_text(content, encoding="utf-8")
        db.add(Document(
            firm_id=firm.id, client_id=cid, uploaded_by_id=accountant.id,
            name=name, document_type=doc_type, file_path=str(path),
            size_bytes=len(content.encode("utf-8")), mime_type="text/plain",
            period=period, visible_to_client=visible,
        ))
    print(f"Created {len(fixtures)} document fixtures")


def seed_task_progress(db: Session, firm: AccountingFirm):
    set_firm_context(db, str(firm.id))
    period = current_period()
    prev = previous_period(period)

    # Generate this month + last month for every client
    for seed in CLIENT_SEEDS:
        generate_tasks_for_client_period(db, firm.id, seed["_client_id"], prev)
        generate_tasks_for_client_period(db, firm.id, seed["_client_id"], period)
    db.flush()

    # Last month: mark all complete
    last_month_tasks = db.scalars(
        select(ClientMonthlyTask).where(ClientMonthlyTask.period == prev)
    ).all()
    accountant = db.scalar(select(User).where(User.email == ACCOUNTANT_EMAIL))
    for t in last_month_tasks:
        t.status = "done"
        t.completed_at = datetime.utcnow() - timedelta(days=15)
        t.completed_by_id = accountant.id

    # Current month: realistic mix — mark earlier-due tasks as complete or in progress
    today = date.today()
    current_tasks = db.scalars(
        select(ClientMonthlyTask).where(ClientMonthlyTask.period == period)
        .order_by(ClientMonthlyTask.due_date)
    ).all()
    # Per-client: complete ~half, in progress ~quarter, leave the rest pending
    by_client = {}
    for t in current_tasks:
        by_client.setdefault(t.client_id, []).append(t)
    for cid, tasks in by_client.items():
        tasks.sort(key=lambda t: t.due_date)
        n = len(tasks)
        done_n = n // 2
        in_progress_n = max(1, n // 5)
        for i, t in enumerate(tasks):
            if i < done_n:
                t.status = "done"
                t.completed_at = datetime.utcnow() - timedelta(days=3)
                t.completed_by_id = accountant.id
            elif i < done_n + in_progress_n:
                t.status = "in_progress"
            # else pending (default)
    db.flush()
    total_complete = sum(1 for t in current_tasks if t.status == "done")
    print(f"Seeded task progress: {total_complete}/{len(current_tasks)} complete this month, all of last month complete")


def seed_demo_transactions(db: Session, firm: AccountingFirm):
    """Create approved transactions for Maple Café for the current period
    and the previous period, so the Reports view has real data to render."""
    from decimal import Decimal
    from app.db.models import Account, AccountingPeriod, Transaction
    from app.tasks.workflow import previous_period as _prev_period

    set_firm_context(db, str(firm.id))
    accountant = db.scalar(select(User).where(User.email == ACCOUNTANT_EMAIL))

    maple = db.scalar(
        select(Client).where(Client.firm_id == firm.id).where(Client.name == "Maple Café Ltd")
    )
    if not maple:
        return

    # Find a few accounts to code transactions against
    def acc(code: str) -> Account | None:
        return db.scalar(
            select(Account)
            .where(Account.client_id == maple.id)
            .where(Account.code == code)
        )

    sales = acc("4010") or acc("4000")
    cogs = acc("5010")
    rent = acc("6200")
    utilities = acc("6210")
    wages = acc("6100")
    software = acc("6240")
    bank_charges = acc("6700")

    today = date.today()
    cur_period_str = current_period()
    prev_period_str = _prev_period(cur_period_str)

    def _ensure_period(period_str: str) -> AccountingPeriod:
        y, m = period_str.split("-")
        y, m = int(y), int(m)
        p = db.scalar(
            select(AccountingPeriod)
            .where(AccountingPeriod.client_id == maple.id)
            .where(AccountingPeriod.year == y)
            .where(AccountingPeriod.month == m)
        )
        if p:
            return p
        p = AccountingPeriod(
            firm_id=firm.id, client_id=maple.id, year=y, month=m, status="open",
        )
        db.add(p)
        db.flush()
        return p

    def _approved(date_: date, desc: str, amount, account, period):
        return Transaction(
            firm_id=firm.id, client_id=maple.id,
            period_id=period.id, account_id=account.id if account else None,
            date=date_, description=desc,
            amount=Decimal(amount),
            source="pdf_extraction", approval_status="approved",
            created_by_id=accountant.id,
            approved_by_id=accountant.id, approved_at=datetime.utcnow(),
        )

    def _seed_period(period_str: str, y: int, m: int, scale: float = 1.0):
        period = _ensure_period(period_str)
        # Sales lines (positive)
        rows = [
            (date(y, m, 3),  "Card sales — week 1",            Decimal("3200.50") * Decimal(str(scale)), sales),
            (date(y, m, 10), "Card sales — week 2",            Decimal("3550.20") * Decimal(str(scale)), sales),
            (date(y, m, 17), "Card sales — week 3",            Decimal("3010.00") * Decimal(str(scale)), sales),
            (date(y, m, 24), "Card sales — week 4",            Decimal("3420.75") * Decimal(str(scale)), sales),
            # COGS (negative)
            (date(y, m, 4),  "Wholesale coffee beans",         Decimal("-820.00") * Decimal(str(scale)), cogs),
            (date(y, m, 18), "Wholesale milk & dairy",         Decimal("-410.00") * Decimal(str(scale)), cogs),
            # Operating expenses
            (date(y, m, 1),  "Monthly rent",                   Decimal("-1800.00"), rent),
            (date(y, m, 5),  "Electricity & gas",              Decimal("-285.50"),  utilities),
            (date(y, m, 25), "Wages — Apr",                    Decimal("-2400.00") * Decimal(str(scale)), wages),
            (date(y, m, 12), "POS software subscription",      Decimal("-49.00"),   software),
            (date(y, m, 28), "Bank charges",                   Decimal("-12.50"),   bank_charges),
        ]
        # Add some uncategorised ones to demonstrate review state on current period
        if period_str == cur_period_str:
            rows.append((date(y, m, 20), "Misc supplier — needs review",
                        Decimal("-67.30"), None))  # uncategorised + approved (rare but supported)
        for tx in rows:
            d, desc, amt, account = tx
            db.add(_approved(d, desc, amt, account, period))

    # Previous period: complete and clean
    py, pm = prev_period_str.split("-")
    _seed_period(prev_period_str, int(py), int(pm), scale=1.0)
    # Current period: similar pattern at slightly higher scale
    cy, cm = cur_period_str.split("-")
    _seed_period(cur_period_str, int(cy), int(cm), scale=1.1)

    # Also stage some unapproved rows on Maple to demonstrate the review UI
    period = _ensure_period(cur_period_str)
    db.add(Transaction(
        firm_id=firm.id, client_id=maple.id, period_id=period.id, account_id=None,
        date=date(int(cy), int(cm), 22),
        description="Card sales — pending bank confirmation",
        amount=Decimal("2980.00"),
        source="pdf_extraction", approval_status="unapproved",
        created_by_id=accountant.id,
    ))
    db.add(Transaction(
        firm_id=firm.id, client_id=maple.id, period_id=period.id, account_id=None,
        date=date(int(cy), int(cm), 26),
        description="Cleaning supplies — Tesco",
        amount=Decimal("-43.20"),
        source="pdf_extraction", approval_status="unapproved",
        created_by_id=accountant.id,
    ))
    db.flush()
    print(f"Seeded spine: Maple Café — 2 periods of approved transactions + 2 pending for review")


if __name__ == "__main__":
    main()
