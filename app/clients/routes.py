from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import (
    Client, User, ClientMonthlyTask, Document, Note,
    ClientAssignment, AdminAuditLog,
)
from app.auth.dependencies import require_accountant
from app.clients.scope import visible_clients_for, get_visible_client_or_404
from app.reference import CURRENCIES, COUNTRIES
from app.ui.templates import templates
from app.tasks.workflow import current_period, generate_tasks_for_client_period
from app.spine.chart_of_accounts import seed_default_coa


router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_class=HTMLResponse)
def list_clients(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    rows = db.scalars(
        visible_clients_for(user, db).order_by(Client.name)
    ).all()
    return templates.TemplateResponse(
        request, "clients/list.html",
        {"user": user, "clients": rows, "countries": dict(COUNTRIES)},
    )


@router.get("/new", response_class=HTMLResponse)
def new_client_form(
    request: Request,
    user: User = Depends(require_accountant),
):
    return templates.TemplateResponse(
        request, "clients/new.html",
        {"user": user, "error": None,
         "currencies": CURRENCIES, "countries": COUNTRIES},
    )


@router.post("/new")
def create_client(
    name: str = Form(...),
    industry: str = Form(""),
    base_currency: str = Form("TRY"),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city: str = Form(""),
    postcode: str = Form(""),
    country_code: str = Form("TR"),
    vkn: str = Form(""),
    tckn: str = Form(""),
    submission_day_of_month: int = Form(10),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    from app.locale import validate_vkn, validate_tckn, clean_tax_id

    vkn_clean = clean_tax_id(vkn) if vkn.strip() else ""
    tckn_clean = clean_tax_id(tckn) if tckn.strip() else ""
    if vkn_clean and not validate_vkn(vkn_clean):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "VKN 10 haneli sayı olmalıdır.")
    if tckn_clean and not validate_tckn(tckn_clean):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "TCKN 11 haneli sayı olmalı ve sıfır ile başlamamalıdır.",
        )

    client = Client(
        firm_id=user.firm_id,
        name=name.strip(),
        industry=industry.strip() or None,
        base_currency=base_currency.strip().upper()[:3] or "TRY",
        address_line1=address_line1.strip() or None,
        address_line2=address_line2.strip() or None,
        city=city.strip() or None,
        postcode=postcode.strip() or None,
        country_code=country_code.strip().upper()[:2] or "TR",
        vkn=vkn_clean or None,
        tckn=tckn_clean or None,
        submission_day_of_month=max(1, min(28, submission_day_of_month)),
    )
    db.add(client)
    db.flush()
    seed_default_coa(db, user.firm_id, client.id)
    generate_tasks_for_client_period(db, user.firm_id, client.id, current_period())

    # Auto-assign the creating accountant to the new client
    db.add(ClientAssignment(
        firm_id=user.firm_id,
        client_id=client.id,
        user_id=user.id,
        assigned_by=user.id,
    ))

    db.commit()
    return RedirectResponse(f"/clients/{client.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{client_id}", response_class=HTMLResponse)
def client_detail(
    client_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = get_visible_client_or_404(client_id, user, db)

    period = current_period()
    tasks = db.scalars(
        select(ClientMonthlyTask)
        .where(ClientMonthlyTask.client_id == client_id)
        .where(ClientMonthlyTask.period == period)
        .order_by(ClientMonthlyTask.due_date)
    ).all()
    docs = db.scalars(
        select(Document)
        .where(Document.client_id == client_id)
        .order_by(Document.created_at.desc())
        .limit(10)
    ).all()
    notes = db.scalars(
        select(Note)
        .where(Note.client_id == client_id)
        .order_by(Note.updated_at.desc())
        .limit(5)
    ).all()
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == "done")
    pct = int((done / total) * 100) if total else 0

    country_name = dict(COUNTRIES).get(client.country_code) if client.country_code else None

    # Phase 3: assignments (firm admins only)
    assigned_users = []
    all_accountants = []
    assigned_user_ids = set()
    if user.is_firm_admin:
        assignments = db.scalars(
            select(ClientAssignment).where(ClientAssignment.client_id == client_id)
        ).all()
        assigned_users = [a.user for a in assignments if a.user]
        assigned_user_ids = {a.user_id for a in assignments}
        all_accountants = db.scalars(
            select(User)
            .where(User.firm_id == user.firm_id)
            .where(User.role == "accountant")
            .where(User.is_active.is_(True))
            .order_by(User.name)
        ).all()

    return templates.TemplateResponse(
        request, "clients/detail.html",
        {
            "user": user, "client": client,
            "tasks": tasks, "documents": docs, "notes": notes,
            "total": total, "done": done, "pct": pct,
            "country_name": country_name,
            "period": period,
            "assigned_users": assigned_users,
            "all_accountants": all_accountants,
            "assigned_user_ids": assigned_user_ids,
        },
    )


@router.post("/{client_id}/assignments")
async def update_assignments(
    client_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    """Firm admin updates which accountants are assigned to a client."""
    if not user.is_firm_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Firma yöneticisi yetkisi gereklidir")

    client = get_visible_client_or_404(client_id, user, db)

    form_data = await request.form()
    new_user_ids = set(UUID(v) for v in form_data.getlist("assigned_user_ids") if v)

    existing = db.scalars(
        select(ClientAssignment).where(ClientAssignment.client_id == client_id)
    ).all()
    existing_by_user = {a.user_id: a for a in existing}
    existing_ids = set(existing_by_user.keys())

    to_add = new_user_ids - existing_ids
    to_remove = existing_ids - new_user_ids

    for uid in to_add:
        db.add(ClientAssignment(
            firm_id=user.firm_id,
            client_id=client_id,
            user_id=uid,
            assigned_by=user.id,
        ))
        db.add(AdminAuditLog(
            firm_id=user.firm_id,
            actor_user_id=user.id,
            target_user_id=uid,
            action="assign_client",
            details={"client_id": str(client_id), "client_name": client.name},
        ))

    for uid in to_remove:
        db.delete(existing_by_user[uid])
        db.add(AdminAuditLog(
            firm_id=user.firm_id,
            actor_user_id=user.id,
            target_user_id=uid,
            action="unassign_client",
            details={"client_id": str(client_id), "client_name": client.name},
        ))

    db.commit()
    return RedirectResponse(f"/clients/{client_id}", status_code=status.HTTP_303_SEE_OTHER)
