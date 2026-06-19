"""Phase 5 tests: İşlem İnceleme sidebar + n8n AI Assistant.

All tests run against real Postgres with RLS enabled.
Starting baseline: 48 tests. Phase 5 adds 7 tests = 55 minimum total.
httpx calls to n8n are mocked — no live n8n instance required.
"""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import set_firm_context
from app.db.models import (
    AccountingFirm, User, Client, AccountingPeriod,
    PeriodSnapshot, Transaction, ClientAssignment,
)
from app.auth.security import hash_password
from app.main import app


# ---------- Helpers ----------

def _make_firm(db, name="Test Firm") -> AccountingFirm:
    f = AccountingFirm(id=uuid.uuid4(), name=name)
    db.add(f)
    db.commit()
    return f


def _make_user(db, firm, email, role="accountant", is_firm_admin=False,
               client_id=None) -> User:
    u = User(
        firm_id=firm.id if firm else None,
        client_id=client_id,
        email=email,
        name="Test User",
        password_hash=hash_password("testpass123"),
        role=role,
        is_firm_admin=is_firm_admin,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def _make_client(db, firm) -> Client:
    c = Client(firm_id=firm.id, name=f"Client-{uuid.uuid4().hex[:6]}")
    db.add(c)
    db.flush()
    return c


def _make_period(db, firm, client, year=2026, month=6) -> AccountingPeriod:
    p = AccountingPeriod(firm_id=firm.id, client_id=client.id, year=year, month=month)
    db.add(p)
    db.flush()
    return p


def _make_transaction(db, firm, client, period, status="unapproved",
                      amount=Decimal("1000"), description="Test") -> Transaction:
    t = Transaction(
        firm_id=firm.id,
        client_id=client.id,
        period_id=period.id,
        date=date(period.year, period.month, 1),
        description=description,
        amount=amount,
        source="manual",
        approval_status=status,
    )
    db.add(t)
    db.flush()
    return t


def _make_snapshot(db, firm, client, period, approval_status="approved",
                   published=True, **kwargs) -> PeriodSnapshot:
    snap = PeriodSnapshot(
        firm_id=firm.id,
        client_id=client.id,
        period_id=period.id,
        source="manual",
        approval_status=approval_status,
        published=published,
        revenue=kwargs.get("revenue", Decimal("100000")),
        cogs=kwargs.get("cogs", Decimal("20000")),
        gross_profit=kwargs.get("gross_profit", Decimal("80000")),
        operating_expenses=kwargs.get("operating_expenses", Decimal("30000")),
        net_profit=kwargs.get("net_profit", Decimal("50000")),
        cash_inflows=kwargs.get("cash_inflows", Decimal("100000")),
        cash_outflows=kwargs.get("cash_outflows", Decimal("50000")),
    )
    db.add(snap)
    db.flush()
    return snap


def _login(http_client, email, password="testpass123"):
    r = http_client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return r


# ---------- Test 1: /transactions shows pending count ----------

def test_transactions_sidebar_shows_pending_count(db, two_firms):
    """GET /transactions returns 200 and shows pending transactions count."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@p5t1.com", is_firm_admin=True)
    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    _make_transaction(db, firm_a, cl, period, status="unapproved")
    _make_transaction(db, firm_a, cl, period, status="unapproved")
    _make_transaction(db, firm_a, cl, period, status="approved")
    db.commit()

    c = TestClient(app)
    _login(c, "admin@p5t1.com")
    r = c.get("/transactions")
    assert r.status_code == 200
    # 2 pending transactions should appear on the page
    assert "2" in r.text
    assert "bekliyor" in r.text


# ---------- Test 2: assignment scope respected ----------

def test_transactions_sidebar_respects_assignment_scope(db, two_firms):
    """Non-admin accountant only sees pending transactions for assigned clients."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    acct = _make_user(db, firm_a, "acct@p5t2.com", role="accountant", is_firm_admin=False)
    cl_assigned = _make_client(db, firm_a)
    cl_other = _make_client(db, firm_a)

    # Assign accountant only to cl_assigned
    db.add(ClientAssignment(
        firm_id=firm_a.id,
        client_id=cl_assigned.id,
        user_id=acct.id,
    ))

    period_a = _make_period(db, firm_a, cl_assigned)
    period_b = _make_period(db, firm_a, cl_other)

    # Both clients have pending transactions
    _make_transaction(db, firm_a, cl_assigned, period_a, status="unapproved",
                      description="AssignedPending")
    _make_transaction(db, firm_a, cl_other, period_b, status="unapproved",
                      description="OtherPending")
    db.commit()

    c = TestClient(app)
    _login(c, "acct@p5t2.com")
    r = c.get("/transactions")
    assert r.status_code == 200
    # Should see assigned client's pending, not the other client's
    assert cl_assigned.name in r.text
    assert cl_other.name not in r.text


# ---------- Test 3: context API returns only approved data ----------

def test_context_api_returns_approved_data_only(db, two_firms):
    """Context endpoint includes only approved transactions, not unapproved ones."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    client_user = _make_user(db, firm_a, "client@p5t3.com", role="client", client_id=cl.id)
    period = _make_period(db, firm_a, cl)

    _make_transaction(db, firm_a, cl, period, status="approved", description="ApprovedTx")
    _make_transaction(db, firm_a, cl, period, status="unapproved", description="UnapprovedTx")
    db.commit()

    c = TestClient(app)
    _login(c, "client@p5t3.com")
    r = c.get("/api/v1/assistant/context")
    assert r.status_code == 200
    data = r.json()
    tx_descriptions = [t["description"] for t in data["transactions"]]
    assert "ApprovedTx" in tx_descriptions
    assert "UnapprovedTx" not in tx_descriptions


# ---------- Test 4: context API client isolation ----------

def test_context_api_client_isolation(db, two_firms):
    """Client user cannot fetch context for a different client's period."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl_a = _make_client(db, firm_a)
    cl_b = _make_client(db, firm_a)
    user_a = _make_user(db, firm_a, "clienta@p5t4.com", role="client", client_id=cl_a.id)

    period_b = _make_period(db, firm_a, cl_b)
    db.commit()

    c = TestClient(app)
    _login(c, "clienta@p5t4.com")
    # Try to fetch context for cl_b's period
    r = c.get(f"/api/v1/assistant/context?period_id={period_b.id}")
    assert r.status_code == 404


# ---------- Test 5: context API requires authentication ----------

def test_context_api_unauthenticated_returns_401(db, two_firms):
    """Unauthenticated request to context endpoint rejects without valid session."""
    from fastapi.exceptions import HTTPException
    import pytest
    c = TestClient(app, raise_server_exceptions=True, follow_redirects=False)
    # The 401 handler re-raises for non-HTML clients; catch the raised exception
    with pytest.raises(HTTPException) as exc_info:
        c.get("/api/v1/assistant/context")
    assert exc_info.value.status_code == 401


# ---------- Test 6: portal assistant disabled when no webhook URL ----------

def test_portal_assistant_disabled_when_no_webhook_url(db, two_firms):
    """When N8N_WEBHOOK_URL is empty, GET /portal/assistant shows disabled message."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    client_user = _make_user(db, firm_a, "client@p5t6.com", role="client", client_id=cl.id)
    db.commit()

    from app.config import get_settings
    from app import config as config_module

    # Patch settings to return empty webhook URL
    original_settings = config_module.get_settings.cache_clear if hasattr(
        config_module.get_settings, 'cache_clear') else None

    with patch("app.portal.routes.get_settings") as mock_settings:
        mock_settings.return_value.n8n_webhook_url = ""
        c = TestClient(app)
        _login(c, "client@p5t6.com")
        r = c.get("/portal/assistant")
        assert r.status_code == 200
        # Should show disabled state, not the chat input form
        assert "yapılandırılmamış" in r.text
        # Should not render the input form
        assert 'name="question"' not in r.text


# ---------- Test 7: portal assistant ask requires client role ----------

def test_portal_assistant_ask_requires_client_role(db, two_firms):
    """POST /portal/assistant/ask returns 403 for accountant users."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    acct = _make_user(db, firm_a, "acct@p5t7.com", role="accountant")
    db.commit()

    c = TestClient(app)
    _login(c, "acct@p5t7.com")
    r = c.post(
        "/portal/assistant/ask",
        data={"question": "Bu ay ne kadar kazandım?"},
        follow_redirects=False,
    )
    assert r.status_code == 403
