"""
Test fixtures. Run via docker compose to get a working Postgres:

    docker compose up -d db
    docker compose exec db createdb -U fincoach fincoach_test
    docker compose run --rm -e POSTGRES_DB=fincoach_test app pytest -v
"""
import os
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.session import Base
from app.db import models  # noqa: F401 — register models


# Tables that have RLS policies — kept in sync with migrations.
RLS_TABLES = [
    "clients",
    "notes",
    "task_templates",
    "client_monthly_tasks",
    "documents",
    "accounts",
    "accounting_periods",
    "transactions",
    # Phase 3 additions
    "client_assignments",
    "admin_audit_log",
    "period_snapshots",
]


@pytest.fixture(scope="session")
def engine():
    settings = get_settings()
    test_db = os.getenv("POSTGRES_DB", settings.postgres_db)
    url = (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{test_db}"
    )
    eng = create_engine(url, future=True)
    with eng.begin() as conn:
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        # Apply RLS policies (Alembic does this in real deploys)
        for t in RLS_TABLES:
            conn.execute(text(f"""
                ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
                ALTER TABLE {t} FORCE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS {t}_firm_isolation ON {t};
                CREATE POLICY {t}_firm_isolation ON {t}
                USING (
                    firm_id::text = current_setting('app.current_firm_id', true)
                    AND current_setting('app.current_firm_id', true) <> ''
                )
                WITH CHECK (
                    firm_id::text = current_setting('app.current_firm_id', true)
                    AND current_setting('app.current_firm_id', true) <> ''
                );
            """))
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory, engine):
    s = session_factory()
    yield s
    s.rollback()
    s.close()
    # Truncate everything between tests
    with engine.begin() as conn:
        tables = ", ".join(RLS_TABLES + ["users", "accounting_firms"])
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def two_firms(db):
    from app.db.models import AccountingFirm
    a = AccountingFirm(id=uuid.uuid4(), name="Firm A")
    b = AccountingFirm(id=uuid.uuid4(), name="Firm B")
    db.add_all([a, b])
    db.commit()
    return a, b


@pytest.fixture
def two_clients(db, two_firms):
    """Create one client per firm under RLS context."""
    from app.db.models import Client
    from app.db import set_firm_context
    firm_a, firm_b = two_firms

    set_firm_context(db, str(firm_a.id))
    ca = Client(firm_id=firm_a.id, name="Client A")
    db.add(ca)
    db.commit()

    set_firm_context(db, str(firm_b.id))
    cb = Client(firm_id=firm_b.id, name="Client B")
    db.add(cb)
    db.commit()

    return (firm_a, ca), (firm_b, cb)
