from typing import Iterator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    pass


def set_firm_context(db: Session, firm_id: str | None) -> None:
    """
    Set the current firm_id for the database session. All Row Level Security
    policies on tenant tables filter by this value.

    IMPLEMENTATION NOTES — read before changing.

    Uses `set_config(..., is_local=false)`, which writes the setting at the
    SESSION level (not transaction level). The setting persists across COMMIT
    and across subsequent transactions on the same connection. That is the
    property we need: a request that commits work mid-flight (e.g. approve a
    transaction, then re-query reports) must not lose its RLS context.

    Caveats:

    1. The set_config call is itself transactional. A ROLLBACK of the
       transaction containing the set_config will undo the set. In practice
       this is fine: `get_current_user` calls this at the start of every
       authenticated request, before the handler does any work, and any
       subsequent rollback inside the handler doesn't roll back the
       implicit transaction in which the set was made (it was already
       committed by the time the handler started its own transaction, OR
       it gets committed alongside the handler's first write).

    2. This function does NOT commit on its own. Calling it does not flush
       pending work in the session. If you call it twice in one session
       with uncommitted work between, the second call doesn't disturb that
       work; only when the caller next commits (or rolls back) does the
       session settle.

    3. When the connection returns to the pool, this value is still set.
       `get_db` clears it in its `finally` block to prevent leakage. RLS
       policies treat an empty value as "deny all", so a leaked-clean
       connection is safe even before the next user authenticates.
    """
    if firm_id is None:
        db.execute(text("SELECT set_config('app.current_firm_id', '', false)"))
    else:
        db.execute(
            text("SELECT set_config('app.current_firm_id', :fid, false)"),
            {"fid": str(firm_id)},
        )


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session.

    On exit, always clears the firm context before closing — preventing
    stale values from leaking to the next consumer of the pooled
    connection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            # Clear the firm context. Use a fresh transaction so we don't
            # interact with whatever the handler may have left open.
            db.rollback()  # drop any uncommitted handler work
            db.execute(text("SELECT set_config('app.current_firm_id', '', false)"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()
