from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_db, set_firm_context
from app.db.models import AccountingFirm, User, Client
from app.auth.dependencies import require_superuser
from app.ui.templates import templates


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
):
    # Superuser operates with no firm context. RLS would block reads of
    # tenant tables. For platform overview we need to bypass that. We use
    # a session that disables RLS by temporarily setting all firm ids.
    # Simpler approach: query firms (not RLS-protected) and use raw counts.
    firms = db.scalars(select(AccountingFirm).order_by(AccountingFirm.name)).all()

    firm_summaries = []
    for f in firms:
        set_firm_context(db, str(f.id))
        client_count = db.scalar(select(func.count()).select_from(Client)) or 0
        user_count = db.scalar(
            select(func.count()).select_from(User).where(User.firm_id == f.id)
        ) or 0
        firm_summaries.append({
            "firm": f,
            "clients": client_count,
            "users": user_count,
        })
    set_firm_context(db, None)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    return templates.TemplateResponse(
        request, "admin/home.html",
        {
            "user": user,
            "firm_summaries": firm_summaries,
            "total_users": total_users,
            "total_firms": len(firms),
        },
    )
