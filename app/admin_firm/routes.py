"""Firm-admin routes: user management and audit log.

Accessible only to accountants with is_firm_admin=True. Distinct from
the platform /admin route which is superuser-only.

Routes:
  GET  /manage/users            — list all firm users
  GET  /manage/users/new        — form to add a user
  POST /manage/users/new        — create user
  GET  /manage/users/{id}       — user detail / edit
  POST /manage/users/{id}/edit  — save email / password
  POST /manage/users/{id}/toggle-active — enable / disable user
  GET  /manage/audit            — audit log
"""
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import User, Client, ClientAssignment, AdminAuditLog
from app.auth.dependencies import require_firm_admin
from app.auth.security import hash_password
from app.ui.templates import templates


router = APIRouter(prefix="/manage", tags=["firm-admin"])


# ---------- User list ----------

@router.get("/users", response_class=HTMLResponse)
def users_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    firm_users = db.scalars(
        select(User)
        .where(User.firm_id == user.firm_id)
        .order_by(User.name)
    ).all()

    # For each accountant, load their assigned clients
    assignments_by_user: dict[UUID, list[Client]] = {}
    all_assignments = db.scalars(
        select(ClientAssignment)
    ).all()
    for a in all_assignments:
        if a.user and a.client:
            assignments_by_user.setdefault(a.user_id, []).append(a.client)

    return templates.TemplateResponse(
        request, "admin_firm/users.html",
        {
            "user": user,
            "firm_users": firm_users,
            "assignments_by_user": assignments_by_user,
        },
    )


# ---------- Add user ----------

@router.get("/users/new", response_class=HTMLResponse)
def add_user_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    return templates.TemplateResponse(
        request, "admin_firm/user_form.html",
        {"user": user, "clients": clients, "edit_user": None, "error": None},
    )


@router.post("/users/new")
def add_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(..., min_length=8),
    role: str = Form("accountant"),
    client_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    email = email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        clients = db.scalars(select(Client).order_by(Client.name)).all()
        return templates.TemplateResponse(
            request, "admin_firm/user_form.html",
            {"user": user, "clients": clients, "edit_user": None,
             "error": "Bu e-posta zaten kullanımda"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if role not in ("accountant", "client"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Geçersiz rol")

    linked_client_id = UUID(client_id) if (role == "client" and client_id) else None

    new_user = User(
        firm_id=user.firm_id,
        client_id=linked_client_id,
        email=email,
        name=name.strip(),
        password_hash=hash_password(password),
        role=role,
        is_firm_admin=False,
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    db.add(AdminAuditLog(
        firm_id=user.firm_id,
        actor_user_id=user.id,
        target_user_id=new_user.id,
        action="create_user",
        details={"email": email, "role": role},
    ))
    db.commit()
    return RedirectResponse("/manage/users", status_code=status.HTTP_303_SEE_OTHER)


# ---------- User detail / edit ----------

@router.get("/users/{target_id}", response_class=HTMLResponse)
def user_detail(
    target_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    target = db.get(User, target_id)
    if not target or target.firm_id != user.firm_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    clients = db.scalars(select(Client).order_by(Client.name)).all()
    assigned_clients: list[Client] = []
    if target.role == "accountant":
        assignments = db.scalars(
            select(ClientAssignment).where(ClientAssignment.user_id == target_id)
        ).all()
        assigned_clients = [a.client for a in assignments if a.client]

    return templates.TemplateResponse(
        request, "admin_firm/user_form.html",
        {
            "user": user,
            "edit_user": target,
            "clients": clients,
            "assigned_clients": assigned_clients,
            "error": None,
        },
    )


@router.post("/users/{target_id}/edit")
def edit_user(
    target_id: UUID,
    name: str = Form(...),
    email: str = Form(...),
    new_password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    target = db.get(User, target_id)
    if not target or target.firm_id != user.firm_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    email = email.lower().strip()
    changes: dict = {}

    if email != target.email:
        if db.scalar(select(User).where(User.email == email).where(User.id != target_id)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "E-posta zaten kullanımda")
        changes["old_email"] = target.email
        changes["new_email"] = email
        target.email = email
        db.add(AdminAuditLog(
            firm_id=user.firm_id,
            actor_user_id=user.id,
            target_user_id=target_id,
            action="change_email",
            details=changes,
        ))

    if name.strip() != target.name:
        target.name = name.strip()

    if new_password:
        target.password_hash = hash_password(new_password)
        db.add(AdminAuditLog(
            firm_id=user.firm_id,
            actor_user_id=user.id,
            target_user_id=target_id,
            action="reset_password",
            details={},
        ))

    db.commit()
    return RedirectResponse(f"/manage/users/{target_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{target_id}/toggle-active")
def toggle_active(
    target_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    target = db.get(User, target_id)
    if not target or target.firm_id != user.firm_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if target.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kendi hesabınızı devre dışı bırakamazsınız")

    target.is_active = not target.is_active
    action = "enable_user" if target.is_active else "disable_user"
    db.add(AdminAuditLog(
        firm_id=user.firm_id,
        actor_user_id=user.id,
        target_user_id=target_id,
        action=action,
        details={"email": target.email},
    ))
    db.commit()
    return RedirectResponse("/manage/users", status_code=status.HTTP_303_SEE_OTHER)


# ---------- Audit log ----------

@router.get("/audit", response_class=HTMLResponse)
def audit_log(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_firm_admin),
):
    entries = db.scalars(
        select(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(200)
    ).all()

    action_labels = {
        "create_user": "Kullanıcı Oluşturuldu",
        "disable_user": "Kullanıcı Devre Dışı Bırakıldı",
        "enable_user": "Kullanıcı Etkinleştirildi",
        "reset_password": "Şifre Sıfırlandı",
        "change_email": "E-posta Değiştirildi",
        "assign_client": "Müşteri Atandı",
        "unassign_client": "Müşteri Ataması Kaldırıldı",
        "create_task": "Görev Oluşturuldu",
        "delete_task": "Görev Silindi",
    }

    return templates.TemplateResponse(
        request, "admin_firm/audit.html",
        {"user": user, "entries": entries, "action_labels": action_labels},
    )
