"""
Default chart of accounts for UK SMEs. Cloned into each new client's
own `accounts` table so they can customise without affecting others.

Codes follow common UK SME bookkeeping conventions (1000=current asset,
2000=liability, 3000=equity, 4000=income, 5000-7000=expense). Codes are
NOT a regulatory standard — they're a convenient default that an accountant
will recognise. Renaming or extending is expected.

Structure: list of (code, name, type, parent_code_or_None).
"""

DEFAULT_UK_SME_COA: list[tuple[str, str, str, str | None]] = [
    # ---- Assets (1000s) ----
    ("1000", "Bank Accounts",                    "asset",     None),
    ("1100", "Current Account",                  "asset",     "1000"),
    ("1110", "Savings Account",                  "asset",     "1000"),
    ("1200", "Accounts Receivable",              "asset",     None),
    ("1300", "Inventory",                        "asset",     None),
    ("1400", "Prepayments",                      "asset",     None),
    ("1500", "Fixed Assets",                     "asset",     None),
    ("1510", "Equipment",                        "asset",     "1500"),
    ("1520", "Office Furniture",                 "asset",     "1500"),

    # ---- Liabilities (2000s) ----
    ("2000", "Accounts Payable",                 "liability", None),
    ("2100", "VAT Liability",                    "liability", None),
    ("2200", "PAYE / NIC Liability",             "liability", None),
    ("2300", "Corporation Tax Payable",          "liability", None),
    ("2400", "Loans Payable",                    "liability", None),
    ("2500", "Credit Card",                      "liability", None),

    # ---- Equity (3000s) ----
    ("3000", "Share Capital",                    "equity",    None),
    ("3100", "Retained Earnings",                "equity",    None),
    ("3200", "Director's Loan",                  "equity",    None),

    # ---- Income (4000s) ----
    ("4000", "Sales",                            "income",    None),
    ("4010", "Product Sales",                    "income",    "4000"),
    ("4020", "Services Income",                  "income",    "4000"),
    ("4100", "Other Income",                     "income",    None),
    ("4110", "Interest Received",                "income",    "4100"),
    ("4120", "Refunds Received",                 "income",    "4100"),

    # ---- Cost of Sales (5000s) ----
    ("5000", "Cost of Sales",                    "expense",   None),
    ("5010", "Materials / Stock Purchases",      "expense",   "5000"),
    ("5020", "Subcontractor Costs",              "expense",   "5000"),

    # ---- Operating expenses (6000s) ----
    ("6000", "Operating Expenses",               "expense",   None),
    ("6100", "Wages & Salaries",                 "expense",   "6000"),
    ("6110", "Employer NIC",                     "expense",   "6000"),
    ("6120", "Pension Contributions",            "expense",   "6000"),
    ("6200", "Rent",                             "expense",   "6000"),
    ("6210", "Utilities",                        "expense",   "6000"),
    ("6220", "Telephone & Internet",             "expense",   "6000"),
    ("6230", "Office Supplies",                  "expense",   "6000"),
    ("6240", "Software Subscriptions",           "expense",   "6000"),
    ("6300", "Marketing & Advertising",          "expense",   "6000"),
    ("6310", "Website Costs",                    "expense",   "6000"),
    ("6400", "Travel",                           "expense",   "6000"),
    ("6410", "Motor Expenses",                   "expense",   "6000"),
    ("6420", "Subsistence",                      "expense",   "6000"),
    ("6500", "Professional Fees",                "expense",   "6000"),
    ("6510", "Accountancy Fees",                 "expense",   "6500"),
    ("6520", "Legal Fees",                       "expense",   "6500"),
    ("6600", "Insurance",                        "expense",   "6000"),
    ("6700", "Bank Charges",                     "expense",   "6000"),
    ("6710", "Interest Paid",                    "expense",   "6000"),
    ("6800", "Depreciation",                     "expense",   "6000"),
    ("6900", "Repairs & Maintenance",            "expense",   "6000"),

    # ---- Misc / catch-alls (7000s) ----
    ("7000", "Sundry Expenses",                  "expense",   None),
    ("7100", "Uncategorised",                    "expense",   None),  # default landing
    ("9999", "Suspense Account",                 "asset",     None),  # for unresolved
]


def seed_default_coa(db, firm_id, client_id) -> int:
    """Create the default chart of accounts for `client_id`.
    Returns count of accounts created (0 if any already exist)."""
    from sqlalchemy import select
    from app.db.models import Account

    existing = db.scalar(
        select(Account.id).where(Account.client_id == client_id).limit(1)
    )
    if existing:
        return 0

    # Two-pass insert: first by code so we can resolve parent references
    by_code: dict[str, Account] = {}
    for code, name, type_, _parent in DEFAULT_UK_SME_COA:
        a = Account(
            firm_id=firm_id, client_id=client_id,
            code=code, name=name, type=type_,
        )
        db.add(a)
        db.flush()
        by_code[code] = a

    for code, _, _, parent_code in DEFAULT_UK_SME_COA:
        if parent_code and parent_code in by_code:
            by_code[code].parent_id = by_code[parent_code].id

    db.flush()
    return len(by_code)
