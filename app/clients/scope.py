"""Client visibility scoping.

Every route that lists or fetches clients for an accountant must use
visible_clients_for() instead of a raw db.query(Client). The only
exception is the superuser /admin routes, which bypass RLS entirely.

Scoping is transitive: a user who cannot see a client must not see that
client's tasks, documents, notes, transactions, reports, or snapshots.
Direct URL access to a forbidden client resource returns 404, not 403.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Client, ClientAssignment, User


def visible_clients_for(user: User, db: Session):
    """Return a base Select for clients this user may see.

    RLS still further filters the result to the current firm — this
    function only adds the assignment filter on top.
    """
    if user.is_firm_admin:
        # Firm admins see all clients in their firm (RLS handles firm boundary)
        return select(Client)

    if user.role == "accountant":
        # Non-admin accountants see only clients they are assigned to
        return (
            select(Client)
            .join(ClientAssignment, ClientAssignment.client_id == Client.id)
            .where(ClientAssignment.user_id == user.id)
        )

    if user.role == "client":
        # Client-portal users see only their own linked client
        return select(Client).where(Client.id == user.client_id)

    # Safe default: nothing visible
    return select(Client).where(False)


def get_visible_client_or_404(client_id, user: User, db: Session) -> Client:
    """Fetch a single client the user is allowed to see, raising 404 otherwise.

    Returns 404 (not 403) to avoid leaking whether the client exists.
    """
    from fastapi import HTTPException, status
    stmt = visible_clients_for(user, db).where(Client.id == client_id)
    client = db.scalar(stmt)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return client
