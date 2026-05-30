"""
Auth happy-path tests via the FastAPI test client.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(engine):
    return TestClient(app)


def test_register_then_login(client, db):
    r = client.post(
        "/register",
        data={
            "firm_name": "Test Firm",
            "name": "Alice",
            "email": "alice@example.com",
            "password": "supersecret",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "fincoach_session" in r.cookies

    # Logout
    client.post("/logout")

    # Log back in
    r = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "supersecret"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_login_rejects_bad_password(client, db):
    client.post(
        "/register",
        data={
            "firm_name": "Test Firm",
            "name": "Alice",
            "email": "alice2@example.com",
            "password": "supersecret",
        },
    )
    r = client.post(
        "/login",
        data={"email": "alice2@example.com", "password": "wrongpass"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_root_redirects_when_unauthenticated(client):
    # raise_server_exceptions=False so the 401-handler's redirect surfaces
    # as a response rather than the HTTPException propagating.
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/", follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code in (302, 307)
