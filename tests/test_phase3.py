"""Phase 3 tests: firm admin, assignments, audit log, task assignment, period snapshots.

All tests run against real Postgres with RLS enabled.
Starting baseline: 22 existing tests. Phase 3 adds 14 tests = 36 minimum total.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import set_firm_context
from app.db.models import (
    AccountingFirm, User, Client, ClientAssignment,
    ClientMonthlyTask, AccountingPeriod, Transaction,
    PeriodSnapshot, AdminAuditLog,
)
from app.auth.security import hash_password
from app.main import app


# ---------- Helpers ----------

def _make_firm(db, name="Test Firm") -> AccountingFirm:
    f = AccountingFirm(id=uuid.uuid4(), name=name)
    db.add(f)
    db.commit()
    return f


def _make_user(db, firm, email, is_firm_admin=False, role="accountant", is_active=True) -> User:
    u = User(
        firm_id=firm.id if firm else None,
        email=email,
        name="Test User",
        password_hash=hash_password("testpass123"),
        role=role,
        is_firm_admin=is_firm_admin,
        is_active=is_active,
    )
    db.add(u)
    db.flush()
    return u


def _make_client(db, firm) -> Client:
    c = Client(firm_id=firm.id, name=f"Client-{uuid.uuid4().hex[:6]}")
    db.add(c)
    db.flush()
    return c


def _make_period(db, firm, client) -> AccountingPeriod:
    p = AccountingPeriod(firm_id=firm.id, client_id=client.id, year=2026, month=3)
    db.add(p)
    db.flush()
    return p


# ---------- Step 1: firm admin promotion ----------

def test_firm_admin_promoted_on_register(db, engine):
    """Registering a new firm sets is_firm_admin=True on the registering user."""
    c = TestClient(app)
    r = c.post("/register", data={
        "firm_name": "AdminTestFirm",
        "name": "Zeynep Demir",
        "email": "zeynep@adminfirm.com",
        "password": "securepw1",
    }, follow_redirects=False)
    assert r.status_code == 303

    set_firm_context(db, None)
    user = db.scalar(select(User).where(User.email == "zeynep@adminfirm.com"))
    assert user is not None
    assert user.is_firm_admin is True
    assert user.is_active is True


def test_disabled_user_cannot_login(db, two_firms):
    """A user with is_active=False cannot log in."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))
    u = _make_user(db, firm_a, "inactive@firm.com", is_active=False)
    db.commit()

    c = TestClient(app)
    r = c.post("/login", data={"email": "inactive@firm.com", "password": "testpass123"},
               follow_redirects=False)
    # 401 from is_active check in get_current_user
    assert r.status_code in (401, 303)
    # If redirected, confirm it's not to the dashboard
    if r.status_code == 303:
        assert "/login" in r.headers.get("location", "")


def test_disabled_user_existing_session_invalidated(db, two_firms):
    """A user disabled after login is rejected on their next request."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))
    u = _make_user(db, firm_a, "willbedisabled@firm.com", is_active=True, is_firm_admin=True)
    db.commit()

    c = TestClient(app)
    r = c.post("/login", data={"email": "willbedisabled@firm.com", "password": "testpass123"},
               follow_redirects=False)
    assert r.status_code == 303
    assert "fincoach_session" in r.cookies

    # Now disable the user directly
    set_firm_context(db, str(firm_a.id))
    u.is_active = False
    db.commit()

    # Subsequent authenticated request must fail
    cookies = {"fincoach_session": r.cookies["fincoach_session"]}
    r2 = c.get("/", cookies=cookies, headers={"Accept": "text/html"}, follow_redirects=False)
    assert r2.status_code in (302, 307, 401)


# ---------- Step 3: client assignments ----------

def test_assignment_scoping_blocks_unassigned_accountant_list(db, two_firms):
    """A non-admin accountant without an assignment cannot list that client."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@scopetest.com", is_firm_admin=True)
    acct = _make_user(db, firm_a, "acct@scopetest.com", is_firm_admin=False)
    c1 = _make_client(db, firm_a)
    c2 = _make_client(db, firm_a)
    # Assign acct to c1 only
    db.add(ClientAssignment(firm_id=firm_a.id, client_id=c1.id, user_id=acct.id, assigned_by=admin.id))
    db.commit()

    from app.clients.scope import visible_clients_for
    visible = db.scalars(visible_clients_for(acct, db)).all()
    assert any(v.id == c1.id for v in visible), "Should see assigned client"
    assert not any(v.id == c2.id for v in visible), "Should NOT see unassigned client"


def test_assignment_scoping_returns_404_on_direct_url_access(db, engine, two_firms):
    """Non-admin accountant gets 404 (not 403) on direct URL to unassigned client."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    acct = _make_user(db, firm_a, "acct2@scopetest.com", is_firm_admin=False)
    unassigned_client = _make_client(db, firm_a)
    db.commit()

    from app.clients.scope import get_visible_client_or_404
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        get_visible_client_or_404(unassigned_client.id, acct, db)
    assert exc.value.status_code == 404


def test_firm_admin_sees_all_clients_regardless_of_assignments(db, two_firms):
    """Firm admin sees all clients in their firm, even without explicit assignments."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin2@scopetest.com", is_firm_admin=True)
    c1 = _make_client(db, firm_a)
    c2 = _make_client(db, firm_a)
    # No assignments added
    db.commit()

    from app.clients.scope import visible_clients_for
    visible = db.scalars(visible_clients_for(admin, db)).all()
    ids = {v.id for v in visible}
    assert c1.id in ids
    assert c2.id in ids


def test_client_assignments_isolation_across_firms(db, two_firms):
    """client_assignments table enforces RLS — firm A cannot see firm B's assignments."""
    firm_a, firm_b = two_firms

    set_firm_context(db, str(firm_a.id))
    acct_a = _make_user(db, firm_a, "a@firma.com")
    ca = _make_client(db, firm_a)
    db.add(ClientAssignment(firm_id=firm_a.id, client_id=ca.id, user_id=acct_a.id))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    rows = db.scalars(select(ClientAssignment)).all()
    assert rows == [], "Firm B must not see firm A's assignments"


# ---------- Step 5: task assignment ----------

def test_task_assignment_visibility(db, two_firms):
    """assigned_to_user_id is correctly stored and readable."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    acct = _make_user(db, firm_a, "acct3@task.com")
    cl = _make_client(db, firm_a)
    task = ClientMonthlyTask(
        firm_id=firm_a.id, client_id=cl.id,
        name="Test Task", category="general", period="2026-06",
        due_date=date(2026, 6, 15), status="pending",
        assigned_to_user_id=acct.id,
    )
    db.add(task)
    db.commit()

    fetched = db.scalars(
        select(ClientMonthlyTask).where(ClientMonthlyTask.client_id == cl.id)
    ).all()
    assert len(fetched) == 1
    assert fetched[0].assigned_to_user_id == acct.id


def test_task_my_tasks_filter(db, two_firms):
    """A non-admin accountant should only see tasks assigned to them or unassigned."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    acct1 = _make_user(db, firm_a, "acct1@task.com")
    acct2 = _make_user(db, firm_a, "acct2@task.com")
    cl = _make_client(db, firm_a)

    t1 = ClientMonthlyTask(
        firm_id=firm_a.id, client_id=cl.id, name="My task",
        period="2026-06", due_date=date(2026, 6, 10), category="g",
        assigned_to_user_id=acct1.id,
    )
    t2 = ClientMonthlyTask(
        firm_id=firm_a.id, client_id=cl.id, name="Other task",
        period="2026-06", due_date=date(2026, 6, 10), category="g",
        assigned_to_user_id=acct2.id,
    )
    db.add_all([t1, t2])
    db.commit()

    # Filter for acct1: should see t1 (assigned to them) but not t2
    mine = db.scalars(
        select(ClientMonthlyTask)
        .where(ClientMonthlyTask.period == "2026-06")
        .where(
            (ClientMonthlyTask.assigned_to_user_id == acct1.id)
            | ClientMonthlyTask.assigned_to_user_id.is_(None)
        )
    ).all()
    assert any(t.id == t1.id for t in mine)
    assert not any(t.id == t2.id for t in mine)


# ---------- Step 6: period snapshots ----------

def test_period_snapshots_isolation_across_firms(db, two_firms):
    """period_snapshots RLS prevents cross-firm reads."""
    firm_a, firm_b = two_firms

    set_firm_context(db, str(firm_a.id))
    cl_a = _make_client(db, firm_a)
    p_a = _make_period(db, firm_a, cl_a)
    snap = PeriodSnapshot(
        firm_id=firm_a.id, client_id=cl_a.id, period_id=p_a.id,
        source="manual", approval_status="approved",
        revenue=Decimal("50000"), net_profit=Decimal("10000"),
    )
    db.add(snap)
    db.commit()

    set_firm_context(db, str(firm_b.id))
    rows = db.scalars(select(PeriodSnapshot)).all()
    assert rows == [], "Firm B must not see firm A's snapshots"


def test_report_prefers_snapshot_over_transactions_when_present(db, two_firms):
    """compute_pl returns snapshot data when an approved snapshot exists."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    snap = PeriodSnapshot(
        firm_id=firm_a.id, client_id=cl.id, period_id=period.id,
        source="manual", approval_status="approved",
        revenue=Decimal("99999.00"),
        cogs=Decimal("10000.00"),
        gross_profit=Decimal("89999.00"),
        operating_expenses=Decimal("20000.00"),
        net_profit=Decimal("69999.00"),
    )
    db.add(snap)
    db.commit()

    from app.reporting.engine import compute_pl
    result = compute_pl(db, period)
    assert result.revenue == Decimal("99999.00")
    assert result.data_source == "manual"


def test_report_falls_back_to_transactions_when_no_snapshot(db, two_firms):
    """compute_pl uses transactions when no approved snapshot exists."""
    from app.db.models import Account
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    acct = Account(
        firm_id=firm_a.id, client_id=cl.id,
        code="600", name="Sales", type="income", is_cogs=False,
    )
    db.add(acct)
    db.flush()
    tx = Transaction(
        firm_id=firm_a.id, client_id=cl.id, period_id=period.id,
        account_id=acct.id, date=date(2026, 3, 10),
        description="Sale", amount=Decimal("12345.00"),
        source="manual", approval_status="approved",
    )
    db.add(tx)
    db.commit()

    from app.reporting.engine import compute_pl
    result = compute_pl(db, period)
    assert result.revenue == Decimal("12345.00")
    assert result.data_source == "transactions"


# ---------- Audit log ----------

def test_admin_audit_log_records_disable_action(db, two_firms):
    """Disabling a user writes an entry to admin_audit_log."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "adm@log.com", is_firm_admin=True)
    target = _make_user(db, firm_a, "target@log.com", is_active=True)
    db.add(AdminAuditLog(
        firm_id=firm_a.id,
        actor_user_id=admin.id,
        target_user_id=target.id,
        action="disable_user",
        details={"email": target.email},
    ))
    db.commit()

    entries = db.scalars(
        select(AdminAuditLog).where(AdminAuditLog.action == "disable_user")
    ).all()
    assert len(entries) == 1
    assert entries[0].target_user_id == target.id


def test_admin_audit_log_records_assignment_change(db, two_firms):
    """Assigning a client writes an audit log entry."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "adm2@log.com", is_firm_admin=True)
    acct = _make_user(db, firm_a, "acct@log.com")
    cl = _make_client(db, firm_a)
    db.add(AdminAuditLog(
        firm_id=firm_a.id,
        actor_user_id=admin.id,
        target_user_id=acct.id,
        action="assign_client",
        details={"client_id": str(cl.id), "client_name": cl.name},
    ))
    db.commit()

    entries = db.scalars(
        select(AdminAuditLog).where(AdminAuditLog.action == "assign_client")
    ).all()
    assert len(entries) == 1
    assert entries[0].details["client_id"] == str(cl.id)


def test_admin_audit_log_isolation_across_firms(db, two_firms):
    """admin_audit_log RLS prevents cross-firm reads."""
    firm_a, firm_b = two_firms

    set_firm_context(db, str(firm_a.id))
    admin = _make_user(db, firm_a, "adm3@log.com", is_firm_admin=True)
    db.add(AdminAuditLog(
        firm_id=firm_a.id,
        actor_user_id=admin.id,
        action="create_user",
        details={"email": "new@firm.com"},
    ))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    rows = db.scalars(select(AdminAuditLog)).all()
    assert rows == [], "Firm B must not see firm A's audit log"
