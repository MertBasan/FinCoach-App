from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Client, User, ClientMonthlyTask, Document, Note
from app.auth.dependencies import require_accountant
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
    rows = db.scalars(select(Client).order_by(Client.name)).all()
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
    base_currency: str = Form("GBP"),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city: str = Form(""),
    postcode: str = Form(""),
    country_code: str = Form(""),
    submission_day_of_month: int = Form(10),
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = Client(
        firm_id=user.firm_id,
        name=name.strip(),
        industry=industry.strip() or None,
        base_currency=base_currency.strip().upper()[:3] or "GBP",
        address_line1=address_line1.strip() or None,
        address_line2=address_line2.strip() or None,
        city=city.strip() or None,
        postcode=postcode.strip() or None,
        country_code=country_code.strip().upper()[:2] or None,
        submission_day_of_month=max(1, min(28, submission_day_of_month)),
    )
    db.add(client)
    db.flush()
    # Seed the default UK SME chart of accounts for this client
    seed_default_coa(db, user.firm_id, client.id)
    # Auto-generate this month's tasks for the new client
    generate_tasks_for_client_period(db, user.firm_id, client.id, current_period())
    db.commit()
    return RedirectResponse(f"/clients/{client.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{client_id}", response_class=HTMLResponse)
def client_detail(
    client_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_accountant),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

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

    return templates.TemplateResponse(
        request, "clients/detail.html",
        {
            "user": user, "client": client,
            "tasks": tasks, "documents": docs, "notes": notes,
            "total": total, "done": done, "pct": pct,
            "country_name": country_name,
            "period": period,
        },
    )
