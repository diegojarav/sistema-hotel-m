"""
Tests for security primitives: bcrypt password hashing and JWT tokens.

These are the building blocks for all auth tests.
"""

from datetime import timedelta
from api.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)


# ==========================================
# PASSWORD HASHING
# ==========================================

def test_get_password_hash_returns_bcrypt():
    hashed = get_password_hash("mypassword")
    assert hashed.startswith("$2"), f"Expected bcrypt hash, got: {hashed[:10]}"


def test_verify_password_correct():
    hashed = get_password_hash("correctpass")
    assert verify_password("correctpass", hashed) is True


def test_verify_password_incorrect():
    hashed = get_password_hash("correctpass")
    assert verify_password("wrongpass", hashed) is False


def test_verify_password_plaintext_rejected():
    """Non-bcrypt hash (legacy plaintext) must be rejected."""
    assert verify_password("admin", "admin") is False


def test_verify_password_empty_hash():
    assert verify_password("anything", "") is False


# ==========================================
# JWT TOKENS
# ==========================================

def test_create_access_token_decodable():
    token = create_access_token(data={"sub": "testuser", "role": "admin"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "testuser"
    assert payload["role"] == "admin"


def test_access_token_has_type():
    token = create_access_token(data={"sub": "testuser"})
    payload = decode_token(token)
    assert payload["type"] == "access"


def test_refresh_token_has_type():
    token = create_refresh_token(data={"sub": "testuser"})
    payload = decode_token(token)
    assert payload["type"] == "refresh"


def test_decode_token_expired():
    """Token with negative expiration should return None."""
    token = create_access_token(
        data={"sub": "testuser"},
        expires_delta=timedelta(seconds=-10),
    )
    assert decode_token(token) is None


def test_decode_token_invalid():
    assert decode_token("not.a.valid.token") is None
    assert decode_token("") is None
    assert decode_token("garbage") is None
