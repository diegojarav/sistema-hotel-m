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
