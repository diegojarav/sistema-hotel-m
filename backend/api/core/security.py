"""
Hotel PMS API - Security Utilities
======================================

Password hashing, verification, and JWT token management.

SECURITY HARDENED: Removed legacy plaintext password support.
All passwords MUST be bcrypt hashed.
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from api.core.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


# ==========================================
# PASSWORD HASHING
# ==========================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its bcrypt hash.
    
    SECURITY: Only bcrypt hashes are accepted.
    Legacy plaintext passwords will fail authentication.
    Users with plaintext passwords must reset their password.
    
    Args:
        plain_password: The password provided by the user
        hashed_password: The stored bcrypt hash (must start with $2)
        
    Returns:
        True if password matches the bcrypt hash, False otherwise
    """
    try:
        # Check if it's a valid bcrypt hash (starts with $2a$, $2b$, or $2y$)
        if not hashed_password.startswith('$2'):
            # NOT a bcrypt hash - reject immediately
            # This forces password reset for legacy plaintext passwords
            return False
        
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except (ValueError, TypeError):
        # Invalid hash format
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    All new passwords should be hashed with this function.
    
    Args:
        password: The plain text password to hash
        
    Returns:
        Bcrypt hash of the password
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


# ==========================================
# JWT TOKEN MANAGEMENT
# ==========================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data (should include 'sub' for username)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": "access"
    })
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    Create a JWT refresh token for biometric/persistent login.
    
    Refresh tokens have a longer expiration (7 days by default)
    and are used to obtain new access tokens without re-authentication.
    
    Args:
        data: Payload data (should include 'sub' for username)
        
    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })
    
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string

    Returns:
        Decoded payload if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ==========================================
# SYMMETRIC ENCRYPTION (v1.8.0 — Phase 5)
# ==========================================
# Used to protect SMTP credentials stored in system_settings. The master key
# is derived deterministically from SECRET_KEY via PBKDF2HMAC-SHA256 so that
# (a) no extra secret needs to be managed and (b) rotating SECRET_KEY also
# invalidates stored secrets (operator must re-enter SMTP password after rotation).

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_FERNET_SALT = b"hotel-munich-smtp-v1"
_FERNET_ITERATIONS = 200_000


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY. Cached for the process lifetime."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_FERNET_SALT,
        iterations=_FERNET_ITERATIONS,
    )
    key_material = kdf.derive(SECRET_KEY.encode("utf-8"))
    fernet_key = base64.urlsafe_b64encode(key_material)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a short string (e.g. SMTP password). Returns a base64 blob safe to store in DB."""
    if plaintext is None:
        raise ValueError("plaintext no puede ser None")
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a blob produced by encrypt_secret(). Raises ValueError on invalid/tampered token."""
    if not ciphertext:
        raise ValueError("ciphertext vacío")
    try:
        plain = _fernet().decrypt(ciphertext.encode("ascii"))
    except InvalidToken as e:
        raise ValueError("No se pudo desencriptar el valor (token inválido o SECRET_KEY rotada).") from e
    return plain.decode("utf-8")
