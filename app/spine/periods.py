"""Accounting period helpers.

A period is one calendar month per client. Periods are created on demand
when a transaction's date is first encountered. Closing a period prevents
further transactions from being added — that's the accountant's lever to
freeze the books.
"""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AccountingPeriod


def get_or_create_period(
    db: Session,
    firm_id: UUID,
    client_id: UUID,
    for_date: date,
) -> AccountingPeriod:
    """Return the AccountingPeriod for the month containing for_date,
    creating it if needed. RLS context must already be set to firm_id."""
    p = db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .where(AccountingPeriod.year == for_date.year)
        .where(AccountingPeriod.month == for_date.month)
    )
    if p is not None:
        return p
    p = AccountingPeriod(
        firm_id=firm_id,
        client_id=client_id,
        year=for_date.year,
        month=for_date.month,
        status="open",
    )
    db.add(p)
    db.flush()
    return p


def period_str(p: AccountingPeriod) -> str:
    return f"{p.year}-{p.month:02d}"


def parse_period_str(s: str) -> tuple[int, int]:
    """'2026-05' -> (2026, 5)."""
    y, m = s.split("-")
    return int(y), int(m)
