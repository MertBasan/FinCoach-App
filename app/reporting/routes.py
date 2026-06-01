"""Reports routes — accountant view, scoped to a client.

URL pattern: /clients/{client_id}/reports?period=YYYY-MM
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import User, AccountingPeriod, Transaction
from app.auth.dependencies import require_accountant
from app.clients.scope import get_visible_client_or_404
from app.spine.periods import parse_period_str
from app.reporting.engine import (
    compute_comparison, compute_cash, compute_kpis, find_period,
    get_approved_snapshot,
)
from app.ui.templates import templates


router = APIRouter(prefix="/clients/{client_id}/reports", tags=["reports"])

_SOURCE_LABELS = {
    "manual": "Manuel",
    "eta_sql_import": "ETASQL",
    "logo_import": "Logo",
    "mikro_import": "Mikro",
    "netsis_import": "Netsis",
    "csv_import": "CSV",
    "transactions": None,  # no banner for transaction-computed
}


def _resolve_period(db: Session, client_id: UUID, period_str: str | None) -> AccountingPeriod | None:
    if period_str:
        try:
            y, m = parse_period_str(period_str)
            return find_period(db, client_id, y, m)
        except (ValueError, AttributeError):
            return None
    # Default: latest period with approved transactions OR approved snapshot
    from app.db.models import PeriodSnapshot
    # Try snapshot first
    snap_period = db.scalar(
        select(AccountingPeriod)
        .join(PeriodSnapshot, PeriodSnapshot.period_id == AccountingPeriod.id)
        .where(AccountingPeriod.client_id == client_id)
        .where(PeriodSnapshot.approval_status == "approved")
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    )
    if snap_period:
        return snap_period
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
    # 404 if user can't see this client
    client = get_visible_client_or_404(client_id, user, db)

    current_p = _resolve_period(db, client_id, period)
    all_periods = db.scalars(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
    ).all()

    pl_comp = compute_comparison(db, current_p) if current_p else None
    cash = compute_cash(db, current_p) if current_p else None
    kpis = compute_kpis(db, current_p) if current_p else None

    # Phase 3: snapshot source banner
    snapshot_source: str | None = None
    snapshot_source_label: str | None = None
    if current_p:
        snapshot = get_approved_snapshot(db, current_p)
        if snapshot:
            snapshot_source = snapshot.source
            snapshot_source_label = _SOURCE_LABELS.get(snapshot.source, snapshot.source)

    return templates.TemplateResponse(
        request, "reports/home.html",
        {
            "user": user, "client": client,
            "current_period": current_p,
            "all_periods": all_periods,
            "pl": pl_comp,
            "cash": cash,
            "kpis": kpis,
            "snapshot_source": snapshot_source,
            "snapshot_source_label": snapshot_source_label,
        },
    )
