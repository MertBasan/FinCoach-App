"""Workflow helpers: generate monthly task lists from templates."""
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AccountingFirm, Client, TaskTemplate, ClientMonthlyTask,
)


def current_period() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def previous_period(period: str) -> str:
    y, m = period.split("-")
    y, m = int(y), int(m)
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    return f"{y}-{m:02d}"


def next_period(period: str) -> str:
    y, m = period.split("-")
    y, m = int(y), int(m)
    m += 1
    if m == 13:
        m = 1
        y += 1
    return f"{y}-{m:02d}"


def _due_date_for(period: str, day: int) -> date:
    y, m = period.split("-")
    y, m = int(y), int(m)
    # cap day to 28 to avoid month-end edge cases
    return date(y, m, min(day, 28))


def generate_tasks_for_client_period(
    db: Session,
    firm_id,
    client_id,
    period: str,
) -> int:
    """Generate (or skip if existing) monthly tasks for a client for one period.
    Returns count of newly created tasks."""
    existing = db.scalar(
        select(ClientMonthlyTask.id)
        .where(ClientMonthlyTask.client_id == client_id)
        .where(ClientMonthlyTask.period == period)
        .limit(1)
    )
    if existing:
        return 0

    templates = db.scalars(
        select(TaskTemplate)
        .where(TaskTemplate.firm_id == firm_id)
        .where(TaskTemplate.active.is_(True))
    ).all()
    created = 0
    for tpl in templates:
        db.add(ClientMonthlyTask(
            firm_id=firm_id,
            client_id=client_id,
            template_id=tpl.id,
            name=tpl.name,
            category=tpl.category,
            period=period,
            due_date=_due_date_for(period, tpl.day_of_month),
            status="pending",
        ))
        created += 1
    return created


def generate_tasks_for_all_clients(db: Session, firm_id, period: str) -> int:
    """For every client in the firm, ensure tasks exist for `period`."""
    clients = db.scalars(select(Client).where(Client.firm_id == firm_id)).all()
    total = 0
    for c in clients:
        total += generate_tasks_for_client_period(db, firm_id, c.id, period)
    return total
