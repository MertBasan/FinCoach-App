from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Client, Transaction, AccountingPeriod
from app.auth.dependencies import require_accountant
from app.clients.scope import visible_clients_for
from app.tasks.workflow import current_period
from app.ui.templates import templates

router = APIRouter(tags=["overview"])


@router.get("/transactions", response_class=HTMLResponse)
def transactions_overview(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_accountant),
):
    visible_stmt = visible_clients_for(user, db)
    clients = db.scalars(visible_stmt).all()
    client_ids = [c.id for c in clients]

    if not client_ids:
        return templates.TemplateResponse(
            request, "overview/list.html",
            {
                "user": user,
                "client_cards": [],
                "total_pending": 0,
                "approved_this_month": 0,
                "clients_with_pending": 0,
            },
        )

    # Pending counts per client
    pending_rows = db.execute(
        select(Transaction.client_id, func.count(Transaction.id).label("cnt"))
        .where(Transaction.client_id.in_(client_ids))
        .where(Transaction.approval_status == "unapproved")
        .group_by(Transaction.client_id)
    ).all()
    pending_by_client: dict[UUID, int] = {r.client_id: r.cnt for r in pending_rows}

    # Approved count this calendar month across all visible clients
    today = date.today()
    approved_this_month = db.scalar(
        select(func.count(Transaction.id))
        .where(Transaction.client_id.in_(client_ids))
        .where(Transaction.approval_status == "approved")
        .where(func.extract("year", Transaction.date) == today.year)
        .where(func.extract("month", Transaction.date) == today.month)
    ) or 0

    # Approved counts per client for current period label
    period_str = current_period()
    year, month = int(period_str[:4]), int(period_str[5:])

    # Get current accounting periods for visible clients
    periods = db.scalars(
        select(AccountingPeriod)
        .where(AccountingPeriod.client_id.in_(client_ids))
        .where(AccountingPeriod.year == year)
        .where(AccountingPeriod.month == month)
    ).all()
    period_by_client: dict[UUID, AccountingPeriod] = {p.client_id: p for p in periods}

    # Approved count per client in current period
    approved_by_client: dict[UUID, int] = {}
    if periods:
        period_ids = [p.id for p in periods]
        approved_rows = db.execute(
            select(Transaction.client_id, func.count(Transaction.id).label("cnt"))
            .where(Transaction.period_id.in_(period_ids))
            .where(Transaction.approval_status == "approved")
            .group_by(Transaction.client_id)
        ).all()
        approved_by_client = {r.client_id: r.cnt for r in approved_rows}

    client_map: dict[UUID, Client] = {c.id: c for c in clients}

    # Build cards only for clients that have pending transactions
    client_cards = []
    for client_id, pending_count in sorted(pending_by_client.items(), key=lambda x: -x[1]):
        client = client_map.get(client_id)
        if not client:
            continue
        period = period_by_client.get(client_id)
        period_label = f"{year}-{month:02d}" if period else "—"
        approved_count = approved_by_client.get(client_id, 0)
        client_cards.append({
            "client": client,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "period_label": period_label,
        })

    total_pending = sum(pending_by_client.values())
    clients_with_pending = len(pending_by_client)

    return templates.TemplateResponse(
        request, "overview/list.html",
        {
            "user": user,
            "client_cards": client_cards,
            "total_pending": total_pending,
            "approved_this_month": approved_this_month,
            "clients_with_pending": clients_with_pending,
        },
    )


@router.get("/transactions/pending-count")
def transactions_pending_count(
    db: Session = Depends(get_db),
    user=Depends(require_accountant),
):
    visible_stmt = visible_clients_for(user, db)
    clients = db.scalars(visible_stmt).all()
    client_ids = [c.id for c in clients]
    if not client_ids:
        count = 0
    else:
        count = db.scalar(
            select(func.count(Transaction.id))
            .where(Transaction.client_id.in_(client_ids))
            .where(Transaction.approval_status == "unapproved")
        ) or 0
    if count > 0:
        return HTMLResponse(f'<span class="badge-count">{count}</span>')
    return HTMLResponse("")
