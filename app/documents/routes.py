import os
import uuid as uuid_lib
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile, File, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Document, Client, User
from app.auth.dependencies import require_accountant, get_current_user
from app.clients.scope import visible_clients_for
from app.ui.templates import templates


router = APIRouter(prefix="/documents", tags=["documents"])

# Upload directory. In production this would be S3 or similar.
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/code/uploaded_files"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


DOCUMENT_TYPES = [
    "bank_statement",
    "invoice",
    "receipt",
    "payroll",
    "report",
    "extraction_output",
    "other",
]


@router.get("", response_class=HTMLResponse)
def list_documents(
    request: Request,
    client_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    q = select(Document).order_by(Document.created_at.desc())
    selected_client = None
    if client_id:
        cid = UUID(client_id)
        q = q.where(Document.client_id == cid)
        selected_client = db.get(Client, cid)
    rows = db.scalars(q).all()
    clients = db.scalars(visible_clients_for(user, db).order_by(Client.name)).all()
    return templates.TemplateResponse(
        request, "documents/list.html",
        {
            "user": user, "documents": rows, "clients": clients,
            "selected_client": selected_client,
            "document_types": DOCUMENT_TYPES,
        },
    )


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    document_type: str = Form("other"),
    period: str = Form(""),
    visible_to_client: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    cid = UUID(client_id)
    # Confirm the client belongs to this firm (RLS guarantees it, but double check)
    client = db.get(Client, cid)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    # Store file on disk. Path namespaced by firm and client.
    storage_dir = UPLOAD_DIR / str(user.firm_id) / str(cid)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid_lib.uuid4().hex}_{file.filename}"
    storage_path = storage_dir / stored_name

    contents = await file.read()
    storage_path.write_bytes(contents)

    doc = Document(
        firm_id=user.firm_id,
        client_id=cid,
        uploaded_by_id=user.id,
        name=file.filename,
        document_type=document_type if document_type in DOCUMENT_TYPES else "other",
        file_path=str(storage_path),
        size_bytes=len(contents),
        mime_type=file.content_type,
        period=period.strip() or None,
        visible_to_client=bool(visible_to_client),
    )
    db.add(doc)
    db.commit()

    redirect = f"/documents?client_id={cid}" if client_id else "/documents"
    return RedirectResponse(redirect, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{doc_id}/download")
def download_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    # Authorization: accountants/superusers in same firm OR the client themselves
    if user.role == "client":
        if not doc.visible_to_client or doc.client_id != user.client_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN)
    elif user.role == "accountant":
        if doc.firm_id != user.firm_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN)
    # superuser allowed all

    if not Path(doc.file_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing on disk")
    return FileResponse(
        doc.file_path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.name,
    )


@router.post("/{doc_id}/toggle-visibility")
def toggle_visibility(
    doc_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    doc.visible_to_client = not doc.visible_to_client
    db.commit()
    return RedirectResponse(
        f"/documents?client_id={doc.client_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{doc_id}/delete")
def delete_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(doc)
    db.commit()
    return RedirectResponse("/documents", status_code=status.HTTP_303_SEE_OTHER)
