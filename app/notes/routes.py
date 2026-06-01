from uuid import UUID
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Note, User, Client
from app.auth.dependencies import require_accountant
from app.clients.scope import visible_clients_for
from app.ui.templates import templates


router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_class=HTMLResponse)
def list_notes(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    rows = db.scalars(select(Note).order_by(Note.updated_at.desc())).all()
    clients = db.scalars(visible_clients_for(user, db).order_by(Client.name)).all()
    return templates.TemplateResponse(
        request, "notes/list.html",
        {"user": user, "notes": rows, "clients": clients},
    )


@router.post("")
def create_note(
    title: str = Form(...),
    body: str = Form(""),
    client_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    cid = UUID(client_id) if client_id else None
    n = Note(
        firm_id=user.firm_id,
        author_id=user.id,
        client_id=cid,
        title=title.strip(),
        body=body.strip(),
    )
    db.add(n)
    db.commit()
    return RedirectResponse("/notes", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{note_id}/delete")
def delete_note(
    note_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    db.delete(n)
    db.commit()
    return RedirectResponse("/notes", status_code=status.HTTP_303_SEE_OTHER)
