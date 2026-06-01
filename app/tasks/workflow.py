"""Workflow helpers: generate monthly task lists from templates."""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Client, TaskTemplate, ClientMonthlyTask, ClientAssignment,
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
    return date(y, m, min(day, 28))


def _get_assigned_accountant_ids(db: Session, client_id: UUID) -> list[UUID]:
    """Return user IDs of accountants currently assigned to this client."""
    rows = db.scalars(
        select(ClientAssignment.user_id)
        .where(ClientAssignment.client_id == client_id)
    ).all()
    return list(rows)


def generate_tasks_for_client_period(
    db: Session,
    firm_id,
    client_id,
    period: str,
) -> int:
    """Generate (or skip if existing) monthly tasks for a client for one period.

    Phase 3: if the client has assigned accountants, creates one task copy
    per accountant. If unassigned, creates one unassigned task per template.
    Idempotent — safe to call multiple times.
    """
    accountant_ids = _get_assigned_accountant_ids(db, client_id)

    templates = db.scalars(
        select(TaskTemplate)
        .where(TaskTemplate.firm_id == firm_id)
        .where(TaskTemplate.active.is_(True))
    ).all()

    created = 0
    for tpl in templates:
        due = _due_date_for(period, tpl.day_of_month)
        if accountant_ids:
            for acct_id in accountant_ids:
                # Idempotent: skip if this (template, period, assignee) already exists
                existing = db.scalar(
                    select(ClientMonthlyTask.id)
                    .where(ClientMonthlyTask.template_id == tpl.id)
                    .where(ClientMonthlyTask.client_id == client_id)
                    .where(ClientMonthlyTask.period == period)
                    .where(ClientMonthlyTask.assigned_to_user_id == acct_id)
                    .limit(1)
                )
                if not existing:
                    db.add(ClientMonthlyTask(
                        firm_id=firm_id,
                        client_id=client_id,
                        template_id=tpl.id,
                        name=tpl.name,
                        category=tpl.category,
                        period=period,
                        due_date=due,
                        status="pending",
                        assigned_to_user_id=acct_id,
                    ))
                    created += 1
        else:
            # No assignments — one unassigned task per template
            existing = db.scalar(
                select(ClientMonthlyTask.id)
                .where(ClientMonthlyTask.template_id == tpl.id)
                .where(ClientMonthlyTask.client_id == client_id)
                .where(ClientMonthlyTask.period == period)
                .where(ClientMonthlyTask.assigned_to_user_id.is_(None))
                .limit(1)
            )
            if not existing:
                db.add(ClientMonthlyTask(
                    firm_id=firm_id,
                    client_id=client_id,
                    template_id=tpl.id,
                    name=tpl.name,
                    category=tpl.category,
                    period=period,
                    due_date=due,
                    status="pending",
                    assigned_to_user_id=None,
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
