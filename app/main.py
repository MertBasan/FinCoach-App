from pathlib import Path
from fastapi import FastAPI, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth.routes import router as auth_router
from app.auth.dependencies import get_current_user_optional, landing_path_for
from app.clients.routes import router as clients_router
from app.notes.routes import router as notes_router
from app.tasks.routes import router as tasks_router
from app.documents.routes import router as documents_router
from app.services.routes import router as services_router
from app.portal.routes import router as portal_router
from app.admin.routes import router as admin_router
from app.dashboard.routes import router as dashboard_router
from app.transactions.routes import router as transactions_router
from app.reporting.routes import router as reporting_router
from app.db.models import User


app = FastAPI(title="fincoach")

STATIC_DIR = Path(__file__).parent / "ui" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Auth: /login, /register, /logout
app.include_router(auth_router)

# Dashboard owns /
app.include_router(dashboard_router)

# Feature routers
app.include_router(clients_router)
app.include_router(notes_router)
app.include_router(tasks_router)
app.include_router(documents_router)
app.include_router(services_router)
app.include_router(transactions_router)
app.include_router(reporting_router)
app.include_router(portal_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# When the dashboard is hit by a non-accountant role, redirect appropriately.
# The require_accountant guard on the dashboard handles unauthenticated -> 401,
# but we'd prefer to redirect, so we wrap with a softer check at /home.
@app.exception_handler(401)
async def unauthorized_redirect(request: Request, exc):
    # If they hit a UI page and aren't logged in, send them to login
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse("/login")
    raise exc
