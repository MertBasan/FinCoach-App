from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.db.models import AccountingFirm, User
from app.auth.security import hash_password, verify_password, make_session_token
from app.auth.dependencies import landing_path_for
from app.ui.templates import templates


router = APIRouter(tags=["auth"])
_settings = get_settings()


def _set_session_cookie(response, user: User) -> None:
    fid = str(user.firm_id) if user.firm_id else ""
    token = make_session_token(str(user.id), fid)
    response.set_cookie(
        _settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=_settings.environment != "development",
        max_age=60 * 60 * 24 * 7,
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"error": None, "user": None})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid email or password", "user": None},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse(landing_path_for(user), status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, user)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(request, "auth/register.html", {"error": None, "user": None})


@router.post("/register")
def register(
    request: Request,
    firm_name: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(..., min_length=8),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        return templates.TemplateResponse(
            request, "auth/register.html",
            {"error": "An account with this email already exists", "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    firm = AccountingFirm(name=firm_name.strip())
    db.add(firm)
    db.flush()

    # The firm exists; set RLS context so we can write firm-scoped rows below.
    from app.db import set_firm_context
    set_firm_context(db, str(firm.id))

    user = User(
        firm_id=firm.id,
        email=email,
        name=name.strip(),
        password_hash=hash_password(password),
        role="accountant",
    )
    db.add(user)

    # Seed default task templates so the new firm has a working monthly workflow
    from app.db.models import TaskTemplate
    for tpl in _DEFAULT_TASK_TEMPLATES:
        db.add(TaskTemplate(firm_id=firm.id, **tpl))

    db.commit()

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, user)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(_settings.session_cookie_name)
    return response


_DEFAULT_TASK_TEMPLATES = [
    {"name": "Collect bank statements", "category": "ingestion", "day_of_month": 5,
     "description": "Request bank statements for the prior month from the client."},
    {"name": "Collect invoices & receipts", "category": "ingestion", "day_of_month": 7,
     "description": "Receive and verify all sales invoices and expense receipts."},
    {"name": "Categorise transactions", "category": "bookkeeping", "day_of_month": 12,
     "description": "Code all transactions to the correct expense accounts."},
    {"name": "Bank reconciliation", "category": "bookkeeping", "day_of_month": 14,
     "description": "Reconcile bank statements against the ledger."},
    {"name": "Aged receivables review", "category": "receivables", "day_of_month": 16,
     "description": "Review overdue invoices and flag chase actions."},
    {"name": "VAT preparation", "category": "tax", "day_of_month": 20,
     "description": "Calculate VAT liability and prepare return."},
    {"name": "Monthly management report", "category": "reporting", "day_of_month": 25,
     "description": "Produce and send the monthly report to the client."},
]
