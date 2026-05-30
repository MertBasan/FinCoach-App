"""
Reports routes — accountant view, scoped to a client.

URL pattern: /clients/{client_id}/reports?period=YYYY-MM
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import User, Client, AccountingPeriod, Transaction
from app.auth.dependencies import require_accountant
from app.spine.periods import parse_period_str
from app.reporting.engine import (
    compute_comparison, compute_cash, compute_kpis, find_period,
)
from app.ui.templates import templates


router = APIRouter(prefix="/clients/{client_id}/reports", tags=["reports"])


def _resolve_period(db: Session, client_id: UUID, period_str: str | None) -> AccountingPeriod | None:
    if period_str:
        try:
            y, m = parse_period_str(period_str)
            return find_period(db, client_id, y, m)
        except (ValueError, AttributeError):
            return None
    # Default to the latest period with any approved transactions
    return db.scalar(
        select(AccountingPeriod)
        .join(Transaction, Transaction.period_id == AccountingPeriod.id)
        .where(AccountingPeriod.client_id == client_id)
        .where(Transaction.approval_status == "approved")
        .group_by(AccountingPeriod.id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    ) or db.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    )


@router.get("", response_class=HTMLResponse)
def reports_home(
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
    all_periods = db.scalars(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
    ).all()

    pl_comp = compute_comparison(db, current_p) if current_p else None
    cash = compute_cash(db, current_p) if current_p else None
    kpis = compute_kpis(db, current_p) if current_p else None

    return templates.TemplateResponse(
        request, "reports/home.html",
        {
            "user": user, "client": client,
            "current_period": current_p,
            "all_periods": all_periods,
            "pl": pl_comp,
            "cash": cash,
            "kpis": kpis,
        },
    )
