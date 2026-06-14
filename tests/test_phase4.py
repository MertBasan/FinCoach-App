"""Phase 4 tests: publish flow, SME portal, comparison labels, cross-firm isolation.

All tests run against real Postgres with RLS enabled.
Starting baseline: 37 tests. Phase 4 adds 11 tests = 48 minimum total.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import set_firm_context
from app.db.models import (
    AccountingFirm, User, Client, AccountingPeriod,
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


def _make_user(db, firm, email, role="accountant", is_firm_admin=False, is_active=True,
               client_id=None) -> User:
    u = User(
        firm_id=firm.id if firm else None,
        client_id=client_id,
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


def _make_period(db, firm, client, year=2026, month=5) -> AccountingPeriod:
    p = AccountingPeriod(firm_id=firm.id, client_id=client.id, year=year, month=month)
    db.add(p)
    db.flush()
    return p


def _make_snapshot(db, firm, client, period, approval_status="unapproved",
                   published=False, **kwargs) -> PeriodSnapshot:
    snap = PeriodSnapshot(
        firm_id=firm.id,
        client_id=client.id,
        period_id=period.id,
        source="manual",
        approval_status=approval_status,
        published=published,
        revenue=kwargs.get("revenue", Decimal("100000")),
        cogs=kwargs.get("cogs", Decimal("60000")),
        gross_profit=kwargs.get("gross_profit", Decimal("40000")),
        operating_expenses=kwargs.get("operating_expenses", Decimal("20000")),
        net_profit=kwargs.get("net_profit", Decimal("20000")),
        cash_inflows=kwargs.get("cash_inflows"),
        cash_outflows=kwargs.get("cash_outflows"),
        ar_total=kwargs.get("ar_total"),
        ap_total=kwargs.get("ap_total"),
        expense_breakdown=kwargs.get("expense_breakdown"),
        accountant_note=kwargs.get("accountant_note"),
        published_at=kwargs.get("published_at"),
        published_by_id=kwargs.get("published_by_id"),
    )
    db.add(snap)
    db.flush()
    return snap


def _login(client_http, email, password="testpass123"):
    r = client_http.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return r


# ---------- Step 3: publish flow ----------

def test_publish_requires_approved_snapshot(db, two_firms):
    """Attempting to publish an unapproved snapshot returns 400."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@pub1.com", is_firm_admin=True)
    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    _make_snapshot(db, firm_a, cl, period, approval_status="unapproved")
    db.commit()

    c = TestClient(app)
    _login(c, "admin@pub1.com")
    r = c.post(
        f"/clients/{cl.id}/snapshots/{period.id}/publish",
        data={"accountant_note": "test note"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "onaylanmalıdır" in r.text


def test_publish_sets_published_flag(db, two_firms):
    """Approving then publishing a snapshot sets all publish fields correctly."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@pub2.com", is_firm_admin=True)
    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    snap = _make_snapshot(db, firm_a, cl, period, approval_status="approved")
    db.commit()

    c = TestClient(app)
    _login(c, "admin@pub2.com")
    r = c.post(
        f"/clients/{cl.id}/snapshots/{period.id}/publish",
        data={"accountant_note": "Sayın Müşteri, istatistikleriniz hazır."},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Yayınlandı" in r.text

    set_firm_context(db, str(firm_a.id))
    db.expire_all()
    updated = db.get(PeriodSnapshot, snap.id)
    assert updated.published is True
    assert updated.published_at is not None
    assert updated.published_by_id == admin.id
    assert updated.accountant_note == "Sayın Müşteri, istatistikleriniz hazır."


def test_cannot_publish_twice(db, two_firms):
    """Publishing an already-published snapshot returns 400."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@pub3.com", is_firm_admin=True)
    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    _make_snapshot(db, firm_a, cl, period, approval_status="approved",
                   published=True, published_at=datetime.utcnow(),
                   published_by_id=admin.id)
    db.commit()

    c = TestClient(app)
    _login(c, "admin@pub3.com")
    r = c.post(
        f"/clients/{cl.id}/snapshots/{period.id}/publish",
        data={"accountant_note": "again"},
        follow_redirects=False,
    )
    assert r.status_code == 400


# ---------- Step 4: SME portal ----------

def test_sme_portal_only_sees_published_snapshots(db, two_firms):
    """A client portal user sees empty state when snapshot exists but is not published."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    client_user = _make_user(db, firm_a, "sme@portal1.com", role="client",
                             client_id=cl.id)
    period = _make_period(db, firm_a, cl)
    # approved but NOT published
    _make_snapshot(db, firm_a, cl, period, approval_status="approved", published=False)
    db.commit()

    c = TestClient(app)
    _login(c, "sme@portal1.com")
    r = c.get("/portal/monthly", follow_redirects=False)
    assert r.status_code == 200
    assert "hazır değil" in r.text


def test_sme_portal_sees_published_snapshot(db, two_firms):
    """A client portal user sees the published snapshot data."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    admin = _make_user(db, firm_a, "admin@portal2.com", is_firm_admin=True)
    client_user = _make_user(db, firm_a, "sme@portal2.com", role="client",
                             client_id=cl.id)
    period = _make_period(db, firm_a, cl)
    _make_snapshot(
        db, firm_a, cl, period,
        approval_status="approved",
        published=True,
        published_at=datetime.utcnow(),
        published_by_id=admin.id,
        accountant_note="Sayın Müşteri test notu.",
        revenue=Decimal("250000"),
    )
    db.commit()

    c = TestClient(app)
    _login(c, "sme@portal2.com")
    r = c.get("/portal/monthly", follow_redirects=False)
    assert r.status_code == 200
    assert "Sayın Müşteri test notu." in r.text
    assert "250" in r.text  # revenue present somewhere in formatted output


def test_sme_portal_direct_url_unpublished_returns_404(db, two_firms):
    """Direct URL to an unpublished snapshot period_id returns 404."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    cl = _make_client(db, firm_a)
    _make_user(db, firm_a, "sme@portal3.com", role="client", client_id=cl.id)
    period = _make_period(db, firm_a, cl)
    snap = _make_snapshot(db, firm_a, cl, period, approval_status="approved", published=False)
    db.commit()

    c = TestClient(app)
    _login(c, "sme@portal3.com")
    r = c.get(f"/portal/monthly?period_id={snap.period_id}", follow_redirects=False)
    assert r.status_code == 404


# ---------- Step 5: comparison labels ----------

def test_comparison_labels_with_prior_period(db, two_firms):
    """Two consecutive published snapshots produce correct comparison labels."""
    from app.portal.insights import compute_comparison_labels

    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))
    cl = _make_client(db, firm_a)
    p_prior = _make_period(db, firm_a, cl, year=2026, month=4)
    p_cur = _make_period(db, firm_a, cl, year=2026, month=5)

    prior_snap = _make_snapshot(
        db, firm_a, cl, p_prior,
        approval_status="approved", published=True,
        revenue=Decimal("100000"),
        gross_profit=Decimal("40000"),
        net_profit=Decimal("20000"),
    )
    cur_snap = _make_snapshot(
        db, firm_a, cl, p_cur,
        approval_status="approved", published=True,
        revenue=Decimal("112000"),   # +12%
        gross_profit=Decimal("45000"),
        net_profit=Decimal("18000"),  # -10%
    )
    db.commit()

    labels = compute_comparison_labels(cur_snap, prior_snap)

    # Revenue +12%
    assert labels["revenue"]["direction"] == "up"
    assert "artış" in labels["revenue"]["text"]
    assert "12" in labels["revenue"]["text"]

    # Net profit -10%
    assert labels["net_profit"]["direction"] == "down"
    assert "düşüş" in labels["net_profit"]["text"]

    # Gross margin: prior=40%, current≈40.2% → up
    assert labels["gross_margin"]["direction"] == "up"


def test_comparison_labels_no_prior_period(db, two_firms):
    """Single published snapshot — all tiles show 'Karşılaştırma için önceki dönem bekleniyor'."""
    from app.portal.insights import compute_comparison_labels

    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))
    cl = _make_client(db, firm_a)
    p = _make_period(db, firm_a, cl, year=2026, month=5)
    snap = _make_snapshot(db, firm_a, cl, p, approval_status="approved", published=True)
    db.commit()

    labels = compute_comparison_labels(snap, None)
    for key in ("revenue", "net_profit", "gross_margin"):
        assert labels[key]["direction"] == "none"
        assert "bekleniyor" in labels[key]["text"]


# ---------- Audit log ----------

def test_publish_writes_audit_log(db, two_firms):
    """Publishing a snapshot writes an admin_audit_log entry with action='publish_snapshot'."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@audit1.com", is_firm_admin=True)
    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    _make_snapshot(db, firm_a, cl, period, approval_status="approved")
    db.commit()

    c = TestClient(app)
    _login(c, "admin@audit1.com")
    c.post(
        f"/clients/{cl.id}/snapshots/{period.id}/publish",
        data={"accountant_note": "Audit test"},
        follow_redirects=False,
    )

    set_firm_context(db, str(firm_a.id))
    db.expire_all()
    logs = db.scalars(
        select(AdminAuditLog)
        .where(AdminAuditLog.firm_id == firm_a.id)
        .where(AdminAuditLog.action == "publish_snapshot")
    ).all()
    assert len(logs) >= 1
    assert logs[0].actor_user_id == admin.id


# ---------- Form fields ----------

def test_ar_ap_fields_visible_on_snapshot_form(db, two_firms):
    """GET snapshot form returns HTML containing ar_total and ap_total inputs."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))

    admin = _make_user(db, firm_a, "admin@form1.com", is_firm_admin=True)
    cl = _make_client(db, firm_a)
    period = _make_period(db, firm_a, cl)
    db.commit()

    c = TestClient(app)
    _login(c, "admin@form1.com")
    r = c.get(f"/clients/{cl.id}/snapshots/{period.id}", follow_redirects=False)
    assert r.status_code == 200
    assert 'name="ar_total"' in r.text
    assert 'name="ap_total"' in r.text


# ---------- Cross-firm isolation ----------

def test_portal_monthly_cross_firm_isolation(db, two_firms):
    """A client from firm A cannot see a published snapshot from firm B via direct period_id."""
    firm_a, firm_b = two_firms

    set_firm_context(db, str(firm_a.id))
    cl_a = _make_client(db, firm_a)
    _make_user(db, firm_a, "sme@firmaA.com", role="client", client_id=cl_a.id)
    p_a = _make_period(db, firm_a, cl_a, year=2026, month=5)
    snap_a = _make_snapshot(db, firm_a, cl_a, p_a, approval_status="approved", published=True,
                             published_at=datetime.utcnow())
    db.commit()

    set_firm_context(db, str(firm_b.id))
    cl_b = _make_client(db, firm_b)
    _make_user(db, firm_b, "sme@firmaB.com", role="client", client_id=cl_b.id)
    p_b = _make_period(db, firm_b, cl_b, year=2026, month=5)
    snap_b = _make_snapshot(db, firm_b, cl_b, p_b, approval_status="approved", published=True,
                             published_at=datetime.utcnow())
    db.commit()

    # Client from firm B tries to access firm A's snapshot period_id
    c = TestClient(app)
    _login(c, "sme@firmaB.com")
    r = c.get(f"/portal/monthly?period_id={snap_a.period_id}", follow_redirects=False)
    # RLS + app filtering: firm B client sees nothing from firm A → 404
    assert r.status_code == 404
