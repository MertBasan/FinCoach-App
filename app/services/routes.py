import os
import uuid as uuid_lib
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import User, Client, Document
from app.auth.dependencies import require_accountant
from app.services.catalog import SERVICES, by_slug
from app.services.bank_extraction import (
    process_pdf,
    result_to_dataframe,
    df_to_xlsx_bytes,
    build_output_basename,
    OCR_AVAILABLE,
)
from app.ui.templates import templates


router = APIRouter(prefix="/services", tags=["services"])

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/code/uploaded_files"))


@router.get("", response_class=HTMLResponse)
def services_index(
    request: Request,
    user: User = Depends(require_accountant),
):
    by_cat: dict[str, list] = {}
    for s in SERVICES:
        by_cat.setdefault(s["category"], []).append(s)

    available_count = sum(1 for s in SERVICES if s["status"] == "available")
    return templates.TemplateResponse(
        request, "services/index.html",
        {
            "user": user,
            "by_category": by_cat,
            "total": len(SERVICES),
            "available": available_count,
        },
    )


@router.get("/pdf-extraction", response_class=HTMLResponse)
def pdf_extraction_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    clients = db.scalars(select(Client).order_by(Client.name)).all()
    return templates.TemplateResponse(
        request, "services/pdf_extraction.html",
        {
            "user": user,
            "service": by_slug("pdf_extraction"),
            "clients": clients,
            "ocr_available": OCR_AVAILABLE,
            "error": None,
        },
    )


def _store_document(
    db: Session,
    *,
    firm_id: UUID,
    client_id: UUID,
    uploaded_by_id: UUID | None,
    name: str,
    content: bytes,
    mime_type: str,
    document_type: str,
    source: str,
    period: str | None,
    visible_to_client: bool,
) -> Document:
    """Persist a file to /uploads/<firm>/<client>/<uuid_name> and record a
    Document row referencing it. Returns the committed Document."""
    storage_dir = UPLOAD_DIR / str(firm_id) / str(client_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid_lib.uuid4().hex}_{name}"
    storage_path = storage_dir / stored_name
    storage_path.write_bytes(content)

    doc = Document(
        firm_id=firm_id,
        client_id=client_id,
        uploaded_by_id=uploaded_by_id,
        name=name,
        document_type=document_type,
        source=source,
        file_path=str(storage_path),
        size_bytes=len(content),
        mime_type=mime_type,
        period=period,
        visible_to_client=visible_to_client,
    )
    db.add(doc)
    db.flush()
    return doc


@router.post("/pdf-extraction/run")
async def pdf_extraction_run(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    # Validate inputs
    if not client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A client must be selected")
    try:
        cid = UUID(client_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid client id")
    client = db.get(Client, cid)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please upload a PDF file")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    # Period defaults to current YYYY-MM; the extracted statement may span
    # multiple months, but for filing purposes we tag the document with the
    # period it was uploaded in. The transaction-staging phase (Phase 1c)
    # will assign each parsed row to its own period from the row date.
    today = date.today()
    period = f"{today.year}-{today.month:02d}"

    # 1. Save the source PDF as a Document. We do this BEFORE running the
    #    extractor so that even if extraction crashes, the accountant still
    #    has the PDF on file. visible_to_client=False by default.
    _store_document(
        db,
        firm_id=user.firm_id,
        client_id=cid,
        uploaded_by_id=user.id,
        name=file.filename,
        content=pdf_bytes,
        mime_type=file.content_type or "application/pdf",
        document_type="bank_statement",
        source="pdf_extraction_input",
        period=period,
        visible_to_client=False,
    )
    db.commit()

    # 2. Run extraction.
    try:
        result = process_pdf(pdf_bytes, file.filename)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Extraction crashed: {exc}",
        )

    if not result.rows:
        # Surface a useful error — the input is already saved so the accountant
        # can inspect it. Don't save an empty XLSX.
        warning_summary = "; ".join(result.parser_warnings[:3]) or "no rows parsed"
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"No transactions could be extracted from this PDF "
            f"({result.metadata.bank or 'unknown bank'}): {warning_summary}. "
            f"The source PDF has been saved to the client's documents.",
        )

    df = result_to_dataframe(result)
    xlsx_bytes = df_to_xlsx_bytes(df)

    out_basename = build_output_basename(result)
    out_filename = f"{out_basename}.xlsx"

    # 3. Save the output XLSX as a Document.
    output_doc = _store_document(
        db,
        firm_id=user.firm_id,
        client_id=cid,
        uploaded_by_id=user.id,
        name=out_filename,
        content=xlsx_bytes,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        document_type="extraction_output",
        source="pdf_extraction_output",
        period=period,
        visible_to_client=False,
    )

    # 4. Stage parsed rows as unapproved Transactions.
    #
    # We stage when extractor produced rows AND the balance chain has no
    # issues (or final-balance match is True). If the chain is broken we
    # save the documents but skip staging — accountant inspects manually.
    extraction_is_trustworthy = (
        len(result.rows) > 0
        and len(result.balance_issues) == 0
    )
    staged = skipped = 0
    if extraction_is_trustworthy:
        from app.spine.staging import stage_bank_statement_rows
        # We need the source PDF's document id. Re-fetch the most recently
        # inserted pdf_extraction_input for this client (the one we created
        # at step 1 in this same request).
        input_doc = db.scalar(
            select(Document)
            .where(Document.client_id == cid)
            .where(Document.source == "pdf_extraction_input")
            .order_by(Document.created_at.desc())
            .limit(1)
        )
        staged, skipped = stage_bank_statement_rows(
            db,
            firm_id=user.firm_id,
            client_id=cid,
            source_document_id=input_doc.id if input_doc else None,
            rows=result.rows,
            created_by_id=user.id,
        )
    db.commit()

    # 5. Return the XLSX as a download — the user-facing flow stays as
    #    promised: upload PDF, get Excel back. Staging happens silently;
    #    the accountant sees pending rows on /clients/{id}/transactions.
    headers = {"Content-Disposition": f'attachment; filename="{out_filename}"'}
    if staged > 0:
        headers["X-FinCoach-Staged-Rows"] = str(staged)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
