from datetime import date

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, set_firm_context
from app.db.models import Document, ClientMonthlyTask, Client, User
from app.auth.dependencies import require_client
from app.ui.templates import templates
from app.tasks.workflow import current_period


router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("", response_class=HTMLResponse)
def client_home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_client),
):
    # Client users belong to a firm and a client; we set firm context
    set_firm_context(db, str(user.firm_id))

    client = db.get(Client, user.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Linked client not found")

    # Documents visible to this client
    docs = db.scalars(
        select(Document)
        .where(Document.client_id == user.client_id)
        .where(Document.visible_to_client.is_(True))
        .order_by(Document.created_at.desc())
    ).all()

    # Tasks for current period
    tasks = db.scalars(
        select(ClientMonthlyTask)
        .where(ClientMonthlyTask.client_id == user.client_id)
        .where(ClientMonthlyTask.period == current_period())
        .order_by(ClientMonthlyTask.due_date)
    ).all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status == "done")
    pct = int((done / total) * 100) if total else 0

    today = date.today()
    next_deadline = next(
        (t for t in tasks if t.status != "done" and t.due_date >= today),
        None,
    )

    return templates.TemplateResponse(
        request, "portal/home.html",
        {
            "user": user, "client": client, "docs": docs, "tasks": tasks,
            "total": total, "done": done, "pct": pct,
            "next_deadline": next_deadline,
            "today": today,
            "current_period": current_period(),
        },
    )


@router.get("/insights", response_class=HTMLResponse)
def client_insights(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_client),
):
    set_firm_context(db, str(user.firm_id))
    client = db.get(Client, user.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Linked client not found")

    # Pick the most recent period with any approved transactions.
    from app.db.models import AccountingPeriod, Transaction
    from app.reporting.engine import compute_pl, compute_cash, compute_kpis
    from sqlalchemy import select

    latest_period = db.scalar(
        select(AccountingPeriod)
        .join(Transaction, Transaction.period_id == AccountingPeriod.id)
        .where(AccountingPeriod.client_id == user.client_id)
        .where(Transaction.approval_status == "approved")
        .group_by(AccountingPeriod.id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
        .limit(1)
    )

    pl = compute_pl(db, latest_period) if latest_period else None
    cash = compute_cash(db, latest_period) if latest_period else None
    kpis = compute_kpis(db, latest_period) if latest_period else None

    return templates.TemplateResponse(
        request, "portal/insights.html",
        {
            "user": user, "client": client,
            "period": latest_period,
            "pl": pl, "cash": cash, "kpis": kpis,
        },
    )


@router.get("/assistant", response_class=HTMLResponse)
def client_assistant(
    request: Request,
    user: User = Depends(require_client),
):
    return templates.TemplateResponse(
        request, "portal/assistant.html",
        {"user": user},
    )
