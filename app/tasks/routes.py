from datetime import datetime, date
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import User, Client, ClientMonthlyTask, ClientAssignment, AdminAuditLog
from app.auth.dependencies import require_accountant
from app.clients.scope import visible_clients_for
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
    view: str = "mine",   # "mine" | "all" — filter mode
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    p = period or current_period()

    # Auto-generate tasks for current period on first visit
    if p == current_period():
        generate_tasks_for_all_clients(db, user.firm_id, p)
        db.commit()

    # Load all visible clients for this user
    visible_client_ids = {
        c.id for c in db.scalars(visible_clients_for(user, db)).all()
    }

    # Determine effective view mode
    # - Firm admins default to "all"; can toggle to "mine"
    # - Regular accountants default to "mine"; can toggle to "all"
    if user.is_firm_admin and view != "mine":
        view = "all"

    tasks_query = (
        select(ClientMonthlyTask)
        .where(ClientMonthlyTask.period == p)
        .where(ClientMonthlyTask.client_id.in_(visible_client_ids))
        .order_by(ClientMonthlyTask.due_date, ClientMonthlyTask.name)
    )

    if view == "mine" and not user.is_firm_admin:
        tasks_query = tasks_query.where(
            (ClientMonthlyTask.assigned_to_user_id == user.id)
            | ClientMonthlyTask.assigned_to_user_id.is_(None)
        )

    rows = db.scalars(tasks_query).all()

    clients_by_id = {
        c.id: c for c in db.scalars(visible_clients_for(user, db)).all()
    }
    grouped: dict[UUID, list[ClientMonthlyTask]] = {}
    for t in rows:
        if t.client_id in visible_client_ids:
            grouped.setdefault(t.client_id, []).append(t)

    today = date.today()
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
            "view": view,
        },
    )


@router.post("/{task_id}/status")
def update_task_status(
    task_id: UUID,
    request: Request,
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
        f"/tasks?period={task.period}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{task_id}/assign")
def assign_task(
    task_id: UUID,
    assigned_to: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    """Firm admin reassigns a task."""
    if not user.is_firm_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    task = db.get(ClientMonthlyTask, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    task.assigned_to_user_id = UUID(assigned_to) if assigned_to else None
    db.commit()
    return RedirectResponse(
        f"/tasks?period={task.period}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/new", response_class=HTMLResponse)
def create_task_form(
    request: Request,
    client_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    from app.clients.scope import visible_clients_for
    clients = db.scalars(visible_clients_for(user, db).order_by(Client.name)).all()

    # Accountants assigned to the pre-selected client (if any)
    assignable_users: list[User] = []
    if client_id:
        assignments = db.scalars(
            select(ClientAssignment).where(ClientAssignment.client_id == client_id)
        ).all()
        assignable_users = [a.user for a in assignments if a.user and a.user.is_active]
        if user not in assignable_users and user.is_firm_admin:
            assignable_users.insert(0, user)

    return templates.TemplateResponse(
        request, "tasks/create.html",
        {
            "user": user,
            "clients": clients,
            "pre_client_id": client_id,
            "assignable_users": assignable_users,
            "today": date.today(),
        },
    )


@router.post("/new")
def create_task(
    title: str = Form(...),
    notes: str = Form(""),
    due_date_str: str = Form(..., alias="due_date"),
    client_id: UUID = Form(...),
    assigned_to: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    from app.clients.scope import get_visible_client_or_404
    client = get_visible_client_or_404(client_id, user, db)

    try:
        due = date.fromisoformat(due_date_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz tarih")

    # Determine assigned user — firm admin can assign anyone; others only themselves
    assigned_user_id: UUID | None = None
    if assigned_to:
        assigned_user_id = UUID(assigned_to)
    elif not user.is_firm_admin:
        assigned_user_id = user.id

    # Verify assignee is assigned to this client (or is firm admin)
    if assigned_user_id and not user.is_firm_admin:
        is_assigned = db.scalar(
            select(ClientAssignment.id)
            .where(ClientAssignment.client_id == client_id)
            .where(ClientAssignment.user_id == assigned_user_id)
            .limit(1)
        )
        if not is_assigned:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu müşteriyle ilişkiniz yok")

    period_str = f"{due.year}-{due.month:02d}"
    task = ClientMonthlyTask(
        firm_id=user.firm_id,
        client_id=client_id,
        template_id=None,  # ad-hoc
        name=title.strip(),
        category="genel",
        period=period_str,
        due_date=due,
        status="pending",
        assigned_to_user_id=assigned_user_id,
        notes=notes.strip() or None,
    )
    db.add(task)
    db.add(AdminAuditLog(
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="create_task",
        details={"title": title.strip(), "client": client.name, "due_date": str(due)},
    ))
    db.commit()
    return RedirectResponse(f"/tasks?period={period_str}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/generate")
def generate_for_period(
    period: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    generate_tasks_for_all_clients(db, user.firm_id, period)
    db.commit()
    return RedirectResponse(f"/tasks?period={period}", status_code=status.HTTP_303_SEE_OTHER)
