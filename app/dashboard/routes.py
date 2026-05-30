from datetime import date, timedelta
from collections import defaultdict
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Client, ClientMonthlyTask, Document, Note, User
from app.auth.dependencies import require_accountant
from app.tasks.workflow import current_period, generate_tasks_for_all_clients
from app.ui.templates import templates


router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    period = current_period()

    # Auto-generate tasks for current period on dashboard hit (idempotent)
    generate_tasks_for_all_clients(db, user.firm_id, period)
    db.commit()

    clients = db.scalars(select(Client).order_by(Client.name)).all()
    tasks = db.scalars(
        select(ClientMonthlyTask)
        .where(ClientMonthlyTask.period == period)
    ).all()

    today = date.today()
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.status == "done")
    pending_tasks = sum(1 for t in tasks if t.status == "pending")
    in_progress_tasks = sum(1 for t in tasks if t.status == "in_progress")
    overdue_tasks = sum(1 for t in tasks if t.status != "done" and t.due_date < today)
    pct = int((done_tasks / total_tasks) * 100) if total_tasks else 0

    # Upcoming deadlines (next 7 days, not done)
    week_ahead = today + timedelta(days=7)
    upcoming = [
        t for t in tasks
        if t.status != "done" and today <= t.due_date <= week_ahead
    ]
    upcoming.sort(key=lambda t: t.due_date)
    client_by_id = {c.id: c for c in clients}

    # Per-client task completion for the bar chart
    per_client = defaultdict(lambda: {"total": 0, "done": 0})
    for t in tasks:
        per_client[t.client_id]["total"] += 1
        if t.status == "done":
            per_client[t.client_id]["done"] += 1

    chart_data = {
        "labels": [client_by_id[cid].name for cid in per_client if cid in client_by_id],
        "done": [per_client[cid]["done"] for cid in per_client if cid in client_by_id],
        "total": [per_client[cid]["total"] for cid in per_client if cid in client_by_id],
    }

    # Status doughnut data
    status_data = {
        "labels": ["Done", "In progress", "Pending", "Overdue (not done)"],
        "values": [done_tasks, in_progress_tasks,
                   pending_tasks - overdue_tasks if pending_tasks > overdue_tasks else max(0, pending_tasks - overdue_tasks),
                   overdue_tasks],
    }

    recent_docs = db.scalars(
        select(Document).order_by(Document.created_at.desc()).limit(5)
    ).all()
    recent_notes = db.scalars(
        select(Note).order_by(Note.updated_at.desc()).limit(5)
    ).all()

    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "user": user, "period": period,
            "total_clients": len(clients),
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "overdue_tasks": overdue_tasks,
            "pct": pct,
            "upcoming": upcoming[:10],
            "client_by_id": client_by_id,
            "chart_data_json": json.dumps(chart_data),
            "status_data_json": json.dumps(status_data),
            "recent_docs": recent_docs,
            "recent_notes": recent_notes,
            "today": today,
        },
    )
