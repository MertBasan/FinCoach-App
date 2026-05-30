"""Approved-transaction query helpers.

CRITICAL DESIGN RULE: all reporting / KPI / analytical code MUST go
through `approved_transactions_for_period(...)` (or `for_client(...)`)
to fetch transactions. Never write a raw `select(Transaction)` in a
reporting code path — it will accidentally include unapproved rows.

If you find yourself writing such a query, stop and add the
approval_status='approved' filter, or extend this module with a new
helper that bakes it in.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.db.models import Transaction


def approved_transactions_for_period(
    period_id: UUID,
) -> Select:
    """Return a Select statement for all approved transactions in a period.
    Caller executes with their db session."""
    return (
        select(Transaction)
        .where(Transaction.period_id == period_id)
        .where(Transaction.approval_status == "approved")
        .order_by(Transaction.date, Transaction.created_at)
    )


def approved_transactions_for_client(
    client_id: UUID,
) -> Select:
    """All approved transactions for a client (all periods)."""
    return (
        select(Transaction)
        .where(Transaction.client_id == client_id)
        .where(Transaction.approval_status == "approved")
        .order_by(Transaction.date, Transaction.created_at)
    )


def all_transactions_for_period(period_id: UUID) -> Select:
    """Unfiltered Select — for the review/approve UI ONLY. Do not use
    this in reporting code."""
    return (
        select(Transaction)
        .where(Transaction.period_id == period_id)
        .order_by(Transaction.date, Transaction.created_at)
    )
