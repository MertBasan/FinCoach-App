"""
Transaction review & approve UI.

Accountant-only. Lists unapproved transactions for a client + period, supports
inline edits, single-row approve, and bulk approve. Approved rows are the only
ones that flow into reports (filter is enforced in app.spine.queries).
"""
from datetime import datetime, date as _date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import (
    User, Client, Transaction, Account, AccountingPeriod,
)
from app.auth.dependencies import require_accountant
from app.spine.periods import parse_period_str
from app.ui.templates import templates


router = APIRouter(prefix="/clients/{client_id}/transactions", tags=["transactions"])


def _resolve_period(
    db: Session, client_id: UUID, period_str: str | None,
) -> AccountingPeriod | None:
    """Return the AccountingPeriod matching `period_str` (YYYY-MM). If None,
    pick the period with the most unapproved transactions; failing that, the
    most recent period; failing that, None."""
    if period_str:
        try:
            y, m = parse_period_str(period_str)
        except (ValueError, AttributeError):
            return None
        return db.scalar(
            select(AccountingPeriod)
            .where(AccountingPeriod.client_id == client_id)
            .where(AccountingPeriod.year == y)
            .where(AccountingPeriod.month == m)
        )

    # No period specified — pick the one with most unapproved rows
    period_with_pending = db.scalar(
        select(AccountingPeriod)
        .join(Transaction, Transaction.period_id == AccountingPeriod.id)
        .where(AccountingPeriod.client_id == client_id)
        .where(Transaction.approval_status != "approved")
        .group_by(AccountingPeriod.id)
        .order_by(func.count(Transaction.id).desc())
        .limit(1)
    )
    if period_with_pending:
        return period_with_pending

    return db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    )


@router.get("", response_class=HTMLResponse)
def review_transactions(
    client_id: UUID,
    request: Request,
    period: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    current_p = _resolve_period(db, client_id, period)

    # All periods for the period switcher
    all_periods = db.scalars(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
    ).all()

    # Chart of accounts for the dropdown
    accounts = db.scalars(
        select(Account)
        .where(Account.client_id == client_id)
        .where(Account.active.is_(True))
        .order_by(Account.code)
    ).all()

    txs: list[Transaction] = []
    pending_count = approved_count = 0
    if current_p:
        txs = db.scalars(
            select(Transaction)
            .where(Transaction.period_id == current_p.id)
            .order_by(Transaction.date, Transaction.created_at)
        ).all()
        pending_count = sum(1 for t in txs if t.approval_status != "approved")
        approved_count = sum(1 for t in txs if t.approval_status == "approved")

    return templates.TemplateResponse(
        request, "transactions/review.html",
        {
            "user": user, "client": client,
            "current_period": current_p,
            "all_periods": all_periods,
            "accounts": accounts,
            "transactions": txs,
            "pending_count": pending_count,
            "approved_count": approved_count,
        },
    )


@router.post("/{tx_id}/update")
def update_transaction(
    client_id: UUID,
    tx_id: UUID,
    description: str = Form(""),
    amount: str = Form(...),
    account_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    tx = db.get(Transaction, tx_id)
    if not tx or tx.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    try:
        new_amount = Decimal(amount)
    except (InvalidOperation, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid amount")

    tx.description = description.strip()
    tx.amount = new_amount
    if account_id:
        try:
            aid = UUID(account_id)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid account id")
        # Verify the account belongs to this client
        acc = db.get(Account, aid)
        if acc and acc.client_id == client_id:
            tx.account_id = aid
    else:
        tx.account_id = None

    db.commit()
    p_str = f"{tx.period.year}-{tx.period.month:02d}"
    return RedirectResponse(
        f"/clients/{client_id}/transactions?period={p_str}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tx_id}/approve")
def approve_transaction(
    client_id: UUID,
    tx_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    tx = db.get(Transaction, tx_id)
    if not tx or tx.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    tx.approval_status = "approved"
    tx.approved_by_id = user.id
    tx.approved_at = datetime.utcnow()
    db.commit()
    p_str = f"{tx.period.year}-{tx.period.month:02d}"
    return RedirectResponse(
        f"/clients/{client_id}/transactions?period={p_str}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tx_id}/unapprove")
def unapprove_transaction(
    client_id: UUID,
    tx_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    tx = db.get(Transaction, tx_id)
    if not tx or tx.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    tx.approval_status = "unapproved"
    tx.approved_by_id = None
    tx.approved_at = None
    db.commit()
    p_str = f"{tx.period.year}-{tx.period.month:02d}"
    return RedirectResponse(
        f"/clients/{client_id}/transactions?period={p_str}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/bulk-approve")
async def bulk_approve(
    client_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    """Approve every selected transaction. Form sends tx_ids as repeated
    'tx_id' checkbox fields plus a single 'period' field."""
    form = await request.form()
    period = form.get("period") or ""
    raw_ids = form.getlist("tx_id")
    if not raw_ids:
        return RedirectResponse(
            f"/clients/{client_id}/transactions?period={period}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    ids: list[UUID] = []
    for s in raw_ids:
        try:
            ids.append(UUID(s))
        except ValueError:
            continue

    now = datetime.utcnow()
    approved = 0
    for tx_id in ids:
        tx = db.get(Transaction, tx_id)
        if not tx or tx.client_id != client_id:
            continue
        tx.approval_status = "approved"
        tx.approved_by_id = user.id
        tx.approved_at = now
        approved += 1
    db.commit()
    return RedirectResponse(
        f"/clients/{client_id}/transactions?period={period}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
