"""
Tenancy isolation tests. These verify that PostgreSQL Row Level Security
prevents any cross-firm data access on every tenant-scoped table.

If any of these fail, do not deploy. Every new tenant table requires both
an RLS policy in its migration AND a test in this file.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.db import set_firm_context
from app.db.models import (
    Client, Note, TaskTemplate, ClientMonthlyTask, Document,
    Account, AccountingPeriod, Transaction,
)


# ---------- Clients ----------

def test_rls_clients_read_isolation(db, two_firms):
    firm_a, firm_b = two_firms
    set_firm_context(db, str(firm_a.id))
    db.add(Client(firm_id=firm_a.id, name="Acme")); db.commit()
    set_firm_context(db, str(firm_b.id))
    db.add(Client(firm_id=firm_b.id, name="Beta")); db.commit()

    set_firm_context(db, str(firm_a.id))
    rows = db.scalars(select(Client)).all()
    assert len(rows) == 1 and rows[0].name == "Acme"


def test_rls_clients_no_context_no_rows(db, two_firms):
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))
    db.add(Client(firm_id=firm_a.id, name="Visible")); db.commit()
    set_firm_context(db, None)
    assert db.scalars(select(Client)).all() == []


def test_rls_clients_cross_write_rejected(db, two_firms):
    firm_a, firm_b = two_firms
    set_firm_context(db, str(firm_a.id))
    db.add(Client(firm_id=firm_b.id, name="Stolen"))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_rls_clients_cross_update_blocked(db, two_firms):
    firm_a, firm_b = two_firms
    set_firm_context(db, str(firm_b.id))
    c = Client(firm_id=firm_b.id, name="Original"); db.add(c); db.commit()
    cid = c.id
    set_firm_context(db, str(firm_a.id))
    res = db.execute(
        text("UPDATE clients SET name='Hijacked' WHERE id = :id"),
        {"id": str(cid)},
    )
    db.commit()
    assert res.rowcount == 0


# ---------- Notes ----------

def test_rls_notes_read_isolation(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    db.add(Note(firm_id=firm_a.id, client_id=ca.id, title="A's note")); db.commit()
    set_firm_context(db, str(firm_b.id))
    db.add(Note(firm_id=firm_b.id, client_id=cb.id, title="B's note")); db.commit()

    set_firm_context(db, str(firm_a.id))
    rows = db.scalars(select(Note)).all()
    assert len(rows) == 1 and rows[0].title == "A's note"


# ---------- Tasks ----------

def test_rls_task_templates_isolation(db, two_firms):
    firm_a, firm_b = two_firms
    set_firm_context(db, str(firm_a.id))
    db.add(TaskTemplate(firm_id=firm_a.id, name="A-tpl")); db.commit()
    set_firm_context(db, str(firm_b.id))
    db.add(TaskTemplate(firm_id=firm_b.id, name="B-tpl")); db.commit()

    set_firm_context(db, str(firm_a.id))
    assert [t.name for t in db.scalars(select(TaskTemplate))] == ["A-tpl"]


def test_rls_monthly_tasks_isolation(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    db.add(ClientMonthlyTask(
        firm_id=firm_a.id, client_id=ca.id, name="VAT",
        period="2026-05", due_date=date(2026, 5, 20),
    ))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    assert db.scalars(select(ClientMonthlyTask)).all() == []


# ---------- Documents ----------

def test_rls_documents_isolation(db, two_clients):
    (firm_a, ca), (firm_b, _cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    db.add(Document(
        firm_id=firm_a.id, client_id=ca.id,
        name="doc.pdf", file_path="/tmp/x",
    ))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    assert db.scalars(select(Document)).all() == []


# ---------- Accounts (spine) ----------

def test_rls_accounts_isolation(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    db.add(Account(firm_id=firm_a.id, client_id=ca.id,
                   code="4000", name="Sales", type="income"))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    assert db.scalars(select(Account)).all() == []


def test_rls_accounts_cross_write_rejected(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    db.add(Account(firm_id=firm_b.id, client_id=cb.id,
                   code="X", name="Stolen", type="income"))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# ---------- Accounting periods (spine) ----------

def test_rls_periods_isolation(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    db.add(AccountingPeriod(
        firm_id=firm_a.id, client_id=ca.id, year=2026, month=5,
    ))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    assert db.scalars(select(AccountingPeriod)).all() == []


# ---------- Transactions (spine) ----------

def test_rls_transactions_isolation(db, two_clients):
    (firm_a, ca), (firm_b, _cb) = two_clients
    set_firm_context(db, str(firm_a.id))
    p = AccountingPeriod(firm_id=firm_a.id, client_id=ca.id, year=2026, month=5)
    db.add(p); db.flush()
    db.add(Transaction(
        firm_id=firm_a.id, client_id=ca.id, period_id=p.id,
        date=date(2026, 5, 15), description="Test",
        amount=Decimal("100.00"), source="manual",
    ))
    db.commit()

    set_firm_context(db, str(firm_b.id))
    assert db.scalars(select(Transaction)).all() == []


def test_rls_transactions_cross_write_rejected(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_b.id))
    pb = AccountingPeriod(firm_id=firm_b.id, client_id=cb.id, year=2026, month=5)
    db.add(pb); db.commit()

    set_firm_context(db, str(firm_a.id))
    db.add(Transaction(
        firm_id=firm_b.id, client_id=cb.id, period_id=pb.id,
        date=date(2026, 5, 15), description="Cross-firm injection",
        amount=Decimal("999.00"), source="manual",
    ))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_rls_transactions_cross_update_blocked(db, two_clients):
    (firm_a, ca), (firm_b, cb) = two_clients
    set_firm_context(db, str(firm_b.id))
    pb = AccountingPeriod(firm_id=firm_b.id, client_id=cb.id, year=2026, month=5)
    db.add(pb); db.flush()
    t = Transaction(
        firm_id=firm_b.id, client_id=cb.id, period_id=pb.id,
        date=date(2026, 5, 15), description="Original",
        amount=Decimal("50.00"), source="manual",
    )
    db.add(t); db.commit()
    tid = t.id

    set_firm_context(db, str(firm_a.id))
    res = db.execute(
        text("UPDATE transactions SET description='Hijacked' WHERE id = :id"),
        {"id": str(tid)},
    )
    db.commit()
    assert res.rowcount == 0


def test_no_context_blocks_all_spine_tables(db, two_clients):
    """Without RLS context set, no rows in any spine table should be visible."""
    (firm_a, ca), _ = two_clients
    set_firm_context(db, str(firm_a.id))
    p = AccountingPeriod(firm_id=firm_a.id, client_id=ca.id, year=2026, month=5)
    db.add(p)
    db.add(Account(firm_id=firm_a.id, client_id=ca.id,
                   code="4000", name="Sales", type="income"))
    db.flush()
    db.add(Transaction(
        firm_id=firm_a.id, client_id=ca.id, period_id=p.id,
        date=date(2026, 5, 1), description="x",
        amount=Decimal("1.00"), source="manual",
    ))
    db.commit()

    set_firm_context(db, None)
    assert db.scalars(select(Account)).all() == []
    assert db.scalars(select(AccountingPeriod)).all() == []
    assert db.scalars(select(Transaction)).all() == []


# ---------- Context survives COMMIT (regression test) ----------
#
# A previous implementation used SET LOCAL semantics, which wiped the RLS
# context on every commit. The fix uses session-scoped config; this test
# locks in the invariant.

def test_firm_context_survives_commit(db, two_clients):
    (firm_a, ca), _ = two_clients
    set_firm_context(db, str(firm_a.id))

    # Insert + commit
    db.add(Client(firm_id=firm_a.id, name="Survives-1"))
    db.commit()

    # Without re-setting context, we should STILL see firm A's rows
    rows = db.scalars(select(Client)).all()
    names = sorted(c.name for c in rows)
    assert "Client A" in names
    assert "Survives-1" in names

    # And one more commit + read
    db.add(Client(firm_id=firm_a.id, name="Survives-2"))
    db.commit()
    rows = db.scalars(select(Client)).all()
    assert any(c.name == "Survives-2" for c in rows)


def test_firm_context_survives_rollback(db, two_firms):
    """After a rollback, the firm context should still be set — PROVIDED
    the context was set in a prior transaction that has already committed.
    Per the documented contract: a rollback of the transaction that
    contained the set_config call will undo the set, so we commit first
    to lock the setting in."""
    firm_a, _ = two_firms
    set_firm_context(db, str(firm_a.id))
    # Lock the setting into a committed state
    db.commit()

    # Now do some work and roll it back
    db.add(Client(firm_id=firm_a.id, name="will-be-rolled-back"))
    db.rollback()

    # Context still holds — write again under context
    db.add(Client(firm_id=firm_a.id, name="after-rollback"))
    db.commit()
    rows = db.scalars(select(Client)).all()
    assert any(c.name == "after-rollback" for c in rows)


def test_explicit_context_clear_blocks_access(db, two_clients):
    """Setting context to None must immediately deny tenant-table access,
    even mid-session after previous reads."""
    (firm_a, ca), _ = two_clients
    set_firm_context(db, str(firm_a.id))
    assert db.scalars(select(Client)).all() != []  # baseline: visible

    set_firm_context(db, None)
    assert db.scalars(select(Client)).all() == []


def test_get_db_resets_context_on_exit(engine):
    """The get_db dependency must clear the firm context when its session
    closes, so that the next consumer of the pooled connection doesn't
    inherit the previous firm's context."""
    from app.db.session import get_db, set_firm_context
    import uuid
    from app.db.models import AccountingFirm

    # First request: set context to firm A, do some work
    firm_a_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO accounting_firms (id, name) VALUES (:id, :n)"),
            {"id": str(firm_a_id), "n": "RegressionFirm"},
        )

    gen = get_db()
    db = next(gen)
    set_firm_context(db, str(firm_a_id))
    # Insert a client visible only to firm A
    db.add(Client(firm_id=firm_a_id, name="A's client"))
    db.commit()
    # Simulate end-of-request: drive the generator to completion
    try:
        next(gen)
    except StopIteration:
        pass

    # Second "request": new get_db, no context set. Should see ZERO clients.
    gen2 = get_db()
    db2 = next(gen2)
    # We are deliberately NOT calling set_firm_context here — simulating
    # an unauthenticated endpoint or a bug where context wasn't set.
    visible = db2.scalars(select(Client)).all()
    try:
        next(gen2)
    except StopIteration:
        pass
    assert visible == [], (
        f"Pool leaked firm context — saw {len(visible)} client(s) without setting context"
    )
