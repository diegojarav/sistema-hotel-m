"""
Phase 3 - Auth API Endpoint Tests
=======================================

Tests for the authentication flow via HTTP endpoints (mobile/Next.js path).
Uses FastAPI TestClient with JWT auth headers.

Endpoints tested:
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- POST /api/v1/auth/logout-beacon
"""

import pytest
from api.core.security import decode_token
from database import SessionLog


# ==========================================
# LOGIN
# ==========================================

def test_login_success(client, seed_users):
    """POST /login with valid credentials returns 200 + tokens."""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_invalid_credentials(client, seed_users):
    """POST /login with wrong password returns 401."""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_login_nonexistent_user(client, seed_users):
    """POST /login with unknown username returns 401."""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody", "password": "nope"},
    )
    assert resp.status_code == 401


def test_login_response_structure(client, seed_users):
    """Login response must contain exactly the expected fields."""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    body = resp.json()
    assert set(body.keys()) == {"access_token", "refresh_token", "token_type"}


# ==========================================
# REFRESH
# ==========================================

def test_refresh_valid_token(client, seed_users):
    """POST /refresh with valid refresh_token returns new tokens."""
    # First, login to get a refresh token
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Use the refresh token
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_refresh_invalid_token(client, seed_users):
    """POST /refresh with garbage token returns 401."""
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "this.is.garbage"},
    )
    assert resp.status_code == 401


def test_refresh_access_token_rejected(client, seed_users):
    """POST /refresh with an access_token (not refresh) returns 401."""
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    access_token = login_resp.json()["access_token"]

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert resp.status_code == 401


# ==========================================
# LOGOUT
# ==========================================

def test_logout_success(client, seed_users):
    """POST /logout with valid token returns 200."""
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    token = login_resp.json()["access_token"]

    resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_logout_no_auth(client, seed_users):
    """POST /logout without Authorization header returns 401."""
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 401


# ==========================================
# LOGOUT BEACON
# ==========================================

def test_logout_beacon_success(client, seed_users):
    """POST /logout-beacon with valid token returns 204."""
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    token = login_resp.json()["access_token"]

    resp = client.post(
        "/api/v1/auth/logout-beacon",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


def test_logout_beacon_no_auth(client, seed_users):
    """POST /logout-beacon without auth returns 204 (never fails by design)."""
    resp = client.post("/api/v1/auth/logout-beacon")
    assert resp.status_code == 204


# ==========================================
# SESSION REVOCATION
# ==========================================

def test_session_revocation(client, db_session, seed_users):
    """After manually closing a session in DB, the token should be rejected."""
    # Login to create a session
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Decode the token to get the session_id
    payload = decode_token(token)
    session_id = payload.get("sid")
    assert session_id is not None, "Token must contain a session ID (sid)"

    # Verify the token works before revocation
    check_resp = client.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert check_resp.status_code == 200

    # Manually close the session in the database
    db_session.query(SessionLog).filter(
        SessionLog.session_id == session_id
    ).update({"status": "closed"})
    db_session.commit()

    # Now the token should be rejected
    resp = client.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# ==========================================
# PROTECTED ENDPOINT ACCESS
# ==========================================

def test_protected_endpoint_no_auth(client, seed_full):
    """GET /reservations without token returns 401."""
    resp = client.get("/api/v1/reservations")
    assert resp.status_code == 401


def test_protected_endpoint_valid_auth(client, seed_full, auth_headers_admin):
    """GET /reservations with valid token returns 200."""
    resp = client.get("/api/v1/reservations", headers=auth_headers_admin)
    assert resp.status_code == 200
