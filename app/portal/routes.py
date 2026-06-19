from datetime import date
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, set_firm_context
from app.db.models import Document, ClientMonthlyTask, Client, User, AccountingPeriod, PeriodSnapshot
from app.auth.dependencies import require_client
from app.portal.insights import compute_comparison_labels, period_label_tr
from app.assistant.routes import _build_context
from app.ui.templates import templates
from app.tasks.workflow import current_period


router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("", response_class=HTMLResponse)
def client_home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_client),
):
    set_firm_context(db, str(user.firm_id))

    client = db.get(Client, user.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Linked client not found")

    docs = db.scalars(
        select(Document)
        .where(Document.client_id == user.client_id)
        .where(Document.visible_to_client.is_(True))
        .order_by(Document.created_at.desc())
    ).all()

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


@router.get("/monthly", response_class=HTMLResponse)
def portal_monthly(
    request: Request,
    period_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_client),
):
    set_firm_context(db, str(user.firm_id))

    client = db.get(Client, user.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Linked client not found")

    # All published snapshots for this client (for month picker)
    published_snapshots = db.scalars(
        select(PeriodSnapshot)
        .where(PeriodSnapshot.client_id == user.client_id)
        .where(PeriodSnapshot.published.is_(True))
        .join(AccountingPeriod, AccountingPeriod.id == PeriodSnapshot.period_id)
        .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
    ).all()

    if not published_snapshots:
        return templates.TemplateResponse(
            request, "portal/monthly.html",
            {"user": user, "client": client, "snapshot": None, "published_snapshots": []},
        )

    # Resolve which snapshot to show
    if period_id is not None:
        snapshot = next(
            (s for s in published_snapshots if s.period_id == period_id), None
        )
        if snapshot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
    else:
        snapshot = published_snapshots[0]  # most recent (already sorted desc)

    period = db.get(AccountingPeriod, snapshot.period_id)

    # Find immediately prior calendar month's published snapshot
    if period.month == 1:
        prior_year, prior_month = period.year - 1, 12
    else:
        prior_year, prior_month = period.year, period.month - 1

    prior_snapshot = db.scalar(
        select(PeriodSnapshot)
        .join(AccountingPeriod, AccountingPeriod.id == PeriodSnapshot.period_id)
        .where(PeriodSnapshot.client_id == user.client_id)
        .where(PeriodSnapshot.published.is_(True))
        .where(AccountingPeriod.year == prior_year)
        .where(AccountingPeriod.month == prior_month)
    )

    comparison = compute_comparison_labels(snapshot, prior_snapshot)

    # Gross margin value for the current period
    gross_margin_pct = None
    try:
        if snapshot.revenue and float(snapshot.revenue) != 0:
            gross_margin_pct = float(snapshot.gross_profit) / float(snapshot.revenue) * 100
    except (TypeError, AttributeError):
        pass

    # Cash net change
    cash_net = None
    try:
        if snapshot.cash_inflows is not None and snapshot.cash_outflows is not None:
            cash_net = float(snapshot.cash_inflows) - float(snapshot.cash_outflows)
    except (TypeError, AttributeError):
        pass

    # Expense breakdown sorted descending by amount
    expense_rows = []
    if snapshot.expense_breakdown:
        expense_rows = sorted(
            snapshot.expense_breakdown.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )

    return templates.TemplateResponse(
        request, "portal/monthly.html",
        {
            "user": user,
            "client": client,
            "snapshot": snapshot,
            "period": period,
            "published_snapshots": published_snapshots,
            "comparison": comparison,
            "gross_margin_pct": gross_margin_pct,
            "cash_net": cash_net,
            "expense_rows": expense_rows,
            "period_label": period_label_tr(period.year, period.month),
        },
    )


@router.get("/insights", response_class=HTMLResponse)
def client_insights_redirect(request: Request):
    return RedirectResponse("/portal/monthly", status_code=302)


@router.get("/assistant", response_class=HTMLResponse)
def client_assistant(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_client),
):
    settings = get_settings()
    client = db.get(Client, user.client_id)
    return templates.TemplateResponse(
        request, "portal/assistant.html",
        {
            "user": user,
            "client": client,
            "assistant_enabled": bool(settings.n8n_webhook_url),
        },
    )


@router.post("/assistant/ask", response_class=HTMLResponse)
async def portal_assistant_ask(
    request: Request,
    question: str = Form(..., max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_client),
):
    settings = get_settings()

    if not settings.n8n_webhook_url:
        return HTMLResponse(_chat_pair(question, "Asistan şu an kullanılamıyor."))

    if not question.strip():
        return HTMLResponse(_chat_pair(question, "Lütfen bir soru yazın."))

    client = db.get(Client, user.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    context = _build_context(db, client)
    payload = {
        "question": question,
        "client_name": context["client_name"],
        "period_label": context["period_label"],
        "snapshot": context["snapshot"],
        "transactions": context["transactions"],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(settings.n8n_webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer") or data.get("output") or str(data)
    except Exception:
        answer = "Asistan şu an kullanılamıyor. Lütfen daha sonra tekrar deneyin."

    return HTMLResponse(_chat_pair(question, answer))


def _chat_pair(question: str, answer: str) -> str:
    import html
    q = html.escape(question)
    a = html.escape(answer).replace("\n", "<br>")
    return (
        f'<div class="chat-pair">'
        f'<div class="chat-bubble user">{q}</div>'
        f'<div class="chat-bubble assistant">{a}</div>'
        f'</div>'
    )
