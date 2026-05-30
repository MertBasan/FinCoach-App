from datetime import datetime, date
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import User, Client, ClientMonthlyTask
from app.auth.dependencies import require_accountant
from app.ui.templates import templates
from app.tasks.workflow import (
    current_period, next_period, previous_period,
    generate_tasks_for_all_clients,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_class=HTMLResponse)
def tasks_board(
    request: Request,
    period: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    p = period or current_period()

    # Ensure tasks exist for current period (auto-generate on first visit)
    if p == current_period():
        generate_tasks_for_all_clients(db, user.firm_id, p)
        db.commit()

    rows = db.scalars(
        select(ClientMonthlyTask)
        .where(ClientMonthlyTask.period == p)
        .order_by(ClientMonthlyTask.due_date, ClientMonthlyTask.name)
    ).all()

    # Group by client
    clients_by_id = {
        c.id: c for c in db.scalars(select(Client)).all()
    }
    grouped = {}
    for t in rows:
        grouped.setdefault(t.client_id, []).append(t)

    today = date.today()
    # Summary numbers
    total = len(rows)
    done = sum(1 for t in rows if t.status == "done")
    overdue = sum(1 for t in rows if t.status != "done" and t.due_date < today)
    pct = int((done / total) * 100) if total else 0

    return templates.TemplateResponse(
        request, "tasks/board.html",
        {
            "user": user, "period": p,
            "prev_period": previous_period(p),
            "next_period_str": next_period(p),
            "current_period": current_period(),
            "grouped": grouped, "clients_by_id": clients_by_id,
            "total": total, "done": done, "overdue": overdue, "pct": pct,
            "today": today,
        },
    )


@router.post("/{task_id}/status")
def update_task_status(
    task_id: UUID,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    task = db.get(ClientMonthlyTask, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    if new_status not in ("pending", "in_progress", "done"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad status")
    task.status = new_status
    if new_status == "done":
        task.completed_at = datetime.utcnow()
        task.completed_by_id = user.id
    else:
        task.completed_at = None
        task.completed_by_id = None
    db.commit()
    return RedirectResponse(
        request_url(task.period), status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/generate")
def generate_for_period(
    period: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    generate_tasks_for_all_clients(db, user.firm_id, period)
    db.commit()
    return RedirectResponse(f"/tasks?period={period}", status_code=status.HTTP_303_SEE_OTHER)


def request_url(period: str) -> str:
    return f"/tasks?period={period}"
