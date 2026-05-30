from uuid import UUID
from fastapi import Depends, Request, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, set_firm_context
from app.db.models import User
from app.auth.security import read_session_token


_settings = get_settings()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(_settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = read_session_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    user = db.get(User, UUID(payload["uid"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session no longer valid")

    # Set RLS context. Superusers don't have a firm; they bypass RLS by
    # operating without a firm_id setting (and only the /admin routes
    # work for them).
    if user.firm_id:
        set_firm_context(db, str(user.firm_id))
    else:
        set_firm_context(db, None)
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def require_accountant(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("accountant", "superuser"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accountant access required")
    return user


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if user.role != "superuser":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Superuser access required")
    return user


def require_client(user: User = Depends(get_current_user)) -> User:
    if user.role != "client":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Client access required")
    if not user.client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client user has no client linked")
    return user


def landing_path_for(user: User) -> str:
    """Where to send a user after login."""
    if user.role == "superuser":
        return "/admin"
    if user.role == "client":
        return "/portal"
    return "/"
