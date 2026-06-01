"""Period snapshot routes.

URL pattern: /clients/{client_id}/snapshots[/{period_id}]

A snapshot holds aggregated period-level financial data from external
systems (ETASQL, Logo, Mikro, Netsis) or manual entry. Reports prefer
an approved snapshot over transaction-computed numbers.

Phase 3 ships manual entry only. Import-from-file is stubbed.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import (
    User, Client, AccountingPeriod, PeriodSnapshot,
)
from app.auth.dependencies import require_accountant
from app.clients.scope import get_visible_client_or_404
from app.ui.templates import templates


router = APIRouter(prefix="/clients/{client_id}/snapshots", tags=["snapshots"])

SOURCE_LABELS = {
    "manual": "Manuel",
    "eta_sql_import": "ETASQL",
    "logo_import": "Logo",
    "mikro_import": "Mikro",
    "netsis_import": "Netsis",
    "csv_import": "CSV",
}


def _get_snapshot(db: Session, client_id: UUID, period_id: UUID) -> PeriodSnapshot | None:
    return db.scalar(
        select(PeriodSnapshot)
        .where(PeriodSnapshot.client_id == client_id)
        .where(PeriodSnapshot.period_id == period_id)
    )


def _dec(value: str) -> Decimal | None:
    s = value.strip() if value else ""
    if not s:
        return None
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return None


# ---------- Snapshot list ----------

@router.get("", response_class=HTMLResponse)
def snapshots_list(
    client_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = get_visible_client_or_404(client_id, user, db)

    periods = db.scalars(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id == client_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
    ).all()

    snapshots_by_period = {}
    for p in periods:
        snap = _get_snapshot(db, client_id, p.id)
        snapshots_by_period[p.id] = snap

    return templates.TemplateResponse(
        request, "snapshots/list.html",
        {
            "user": user,
            "client": client,
            "periods": periods,
            "snapshots_by_period": snapshots_by_period,
            "source_labels": SOURCE_LABELS,
        },
    )


# ---------- Create / edit snapshot ----------

@router.get("/{period_id}", response_class=HTMLResponse)
def snapshot_form(
    client_id: UUID,
    period_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = get_visible_client_or_404(client_id, user, db)
    period = db.get(AccountingPeriod, period_id)
    if not period or period.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    snapshot = _get_snapshot(db, client_id, period_id)
    expense_rows = list((snapshot.expense_breakdown or {}).items()) if snapshot else []

    return templates.TemplateResponse(
        request, "snapshots/form.html",
        {
            "user": user,
            "client": client,
            "period": period,
            "snapshot": snapshot,
            "expense_rows": expense_rows,
            "source_labels": SOURCE_LABELS,
            "error": None,
        },
    )


@router.post("/{period_id}")
async def save_snapshot(
    client_id: UUID,
    period_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = get_visible_client_or_404(client_id, user, db)
    period = db.get(AccountingPeriod, period_id)
    if not period or period.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    form = await request.form()

    def f(key: str) -> Decimal | None:
        return _dec(form.get(key, ""))

    # Parse dynamic expense breakdown rows
    expense_breakdown: dict[str, float] = {}
    keys = form.getlist("expense_key")
    vals = form.getlist("expense_value")
    for k, v in zip(keys, vals):
        k = k.strip()
        if k:
            d = _dec(v)
            if d is not None:
                expense_breakdown[k] = float(d)

    snapshot = _get_snapshot(db, client_id, period_id)
    if snapshot:
        snapshot.revenue = f("revenue")
        snapshot.cogs = f("cogs")
        snapshot.gross_profit = f("gross_profit")
        snapshot.operating_expenses = f("operating_expenses")
        snapshot.net_profit = f("net_profit")
        snapshot.cash_balance_opening = f("cash_balance_opening")
        snapshot.cash_balance_closing = f("cash_balance_closing")
        snapshot.cash_inflows = f("cash_inflows")
        snapshot.cash_outflows = f("cash_outflows")
        snapshot.ar_total = f("ar_total")
        snapshot.ap_total = f("ap_total")
        snapshot.vat_input = f("vat_input")
        snapshot.vat_output = f("vat_output")
        snapshot.expense_breakdown = expense_breakdown or None
        snapshot.notes = form.get("notes", "").strip() or None
        snapshot.source = form.get("source", "manual")
        snapshot.updated_at = datetime.utcnow()
    else:
        snapshot = PeriodSnapshot(
            firm_id=user.firm_id,
            client_id=client_id,
            period_id=period_id,
            source=form.get("source", "manual"),
            approval_status="unapproved",
            created_by=user.id,
            revenue=f("revenue"),
            cogs=f("cogs"),
            gross_profit=f("gross_profit"),
            operating_expenses=f("operating_expenses"),
            net_profit=f("net_profit"),
            cash_balance_opening=f("cash_balance_opening"),
            cash_balance_closing=f("cash_balance_closing"),
            cash_inflows=f("cash_inflows"),
            cash_outflows=f("cash_outflows"),
            ar_total=f("ar_total"),
            ap_total=f("ap_total"),
            vat_input=f("vat_input"),
            vat_output=f("vat_output"),
            expense_breakdown=expense_breakdown or None,
            notes=form.get("notes", "").strip() or None,
        )
        db.add(snapshot)

    db.commit()
    return RedirectResponse(
        f"/clients/{client_id}/snapshots",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------- Approve snapshot ----------

@router.post("/{period_id}/approve")
def approve_snapshot(
    client_id: UUID,
    period_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = get_visible_client_or_404(client_id, user, db)
    snapshot = _get_snapshot(db, client_id, period_id)
    if not snapshot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dönem özeti bulunamadı")

    snapshot.approval_status = "approved"
    snapshot.approved_by = user.id
    snapshot.approved_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(
        f"/clients/{client_id}/snapshots",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ---------- Import stub ----------

@router.post("/{period_id}/import")
def import_stub(
    client_id: UUID,
    period_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    """Phase 3 stub — parser logic deferred until real export files are available."""
    get_visible_client_or_404(client_id, user, db)
    return RedirectResponse(
        f"/clients/{client_id}/snapshots/{period_id}?import_stub=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )
