"""Assistant context API and portal ask endpoint."""
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import AccountingPeriod, PeriodSnapshot, Transaction, Client
from app.auth.dependencies import require_client
from app.spine.queries import approved_transactions_for_period
from app.reporting.engine import get_approved_snapshot, compute_pl, compute_cash

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


def _find_best_period(db: Session, client_id: UUID) -> AccountingPeriod | None:
    """Return the most recent period that has published snapshot or approved transactions."""
    # Prefer most recent period with a published snapshot
    snap_period = db.scalar(
        select(AccountingPeriod)
        .join(PeriodSnapshot, PeriodSnapshot.period_id == AccountingPeriod.id)
        .where(AccountingPeriod.client_id == client_id)
        .where(PeriodSnapshot.published.is_(True))
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    )
    if snap_period:
        return snap_period

    # Fall back to period with approved transactions
    tx_period = db.scalar(
        select(AccountingPeriod)
        .join(Transaction, Transaction.period_id == AccountingPeriod.id)
        .where(AccountingPeriod.client_id == client_id)
        .where(Transaction.approval_status == "approved")
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    )
    return tx_period


def _tr_months():
    return ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def _build_context(db: Session, client: Client, period_id: UUID | None = None) -> dict:
    if period_id is not None:
        period = db.scalar(
            select(AccountingPeriod)
            .where(AccountingPeriod.id == period_id)
            .where(AccountingPeriod.client_id == client.id)
        )
        if not period:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
    else:
        period = _find_best_period(db, client.id)

    if not period:
        return {
            "client_name": client.name,
            "period_label": None,
            "snapshot": None,
            "transactions": [],
            "period_id": None,
        }

    months = _tr_months()
    period_label = f"{months[period.month]} {period.year}"

    # Snapshot — prefer published, fall back to approved
    published_snap = db.scalar(
        select(PeriodSnapshot)
        .where(PeriodSnapshot.period_id == period.id)
        .where(PeriodSnapshot.published.is_(True))
    )
    snap = published_snap or get_approved_snapshot(db, period)

    snapshot_dict = None
    if snap:
        rev = float(snap.revenue or 0)
        cogs = float(snap.cogs or 0)
        gross = float(snap.gross_profit) if snap.gross_profit is not None else (rev - cogs)
        opex = float(snap.operating_expenses or 0)
        net = float(snap.net_profit) if snap.net_profit is not None else (gross - opex)
        gm_pct = round(gross / rev * 100, 1) if rev > 0 else 0
        snapshot_dict = {
            "revenue": rev,
            "cogs": cogs,
            "gross_profit": round(gross, 2),
            "gross_margin_pct": gm_pct,
            "operating_expenses": opex,
            "net_profit": round(net, 2),
            "cash_inflows": float(snap.cash_inflows or 0),
            "cash_outflows": float(snap.cash_outflows or 0),
            "cash_net": float(snap.cash_inflows or 0) - float(snap.cash_outflows or 0),
            "ar_total": float(snap.ar_total) if snap.ar_total is not None else None,
            "ap_total": float(snap.ap_total) if snap.ap_total is not None else None,
            "expense_breakdown": snap.expense_breakdown or {},
            "source": snap.source,
        }
    else:
        # Build from transactions
        pl = compute_pl(db, period)
        cash = compute_cash(db, period)
        rev = float(pl.revenue)
        gross = float(pl.gross_profit)
        gm_pct = round(gross / rev * 100, 1) if rev > 0 else 0
        snapshot_dict = {
            "revenue": rev,
            "cogs": float(pl.cost_of_sales),
            "gross_profit": round(gross, 2),
            "gross_margin_pct": gm_pct,
            "operating_expenses": float(pl.operating_expenses),
            "net_profit": round(float(pl.net_profit), 2),
            "cash_inflows": float(cash.inflows),
            "cash_outflows": float(cash.outflows),
            "cash_net": round(float(cash.net_change), 2),
            "ar_total": None,
            "ap_total": None,
            "expense_breakdown": {l.account_name: float(l.total) for l in pl.opex_lines},
            "source": "transactions",
        }

    # Approved transactions for this period
    txs = db.scalars(approved_transactions_for_period(period.id)).all()
    tx_list = []
    for tx in txs:
        acc_code = tx.account.code if tx.account else ""
        acc_name = tx.account.name if tx.account else "Kategorisiz"
        tx_list.append({
            "date": tx.date.isoformat(),
            "description": tx.description,
            "amount": float(tx.amount),
            "account_code": acc_code,
            "account_name": acc_name,
        })

    return {
        "client_name": client.name,
        "period_label": period_label,
        "snapshot": snapshot_dict,
        "transactions": tx_list,
        "period_id": str(period.id),
    }


@router.get("/context")
def get_assistant_context(
    period_id: UUID | None = None,
    db: Session = Depends(get_db),
    user=Depends(require_client),
):
    client = db.get(Client, user.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    # Client users can only access their own data
    if period_id is not None:
        period = db.scalar(
            select(AccountingPeriod)
            .where(AccountingPeriod.id == period_id)
        )
        if not period or period.client_id != user.client_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

    return _build_context(db, client, period_id)
