"""
Hotel PMS API - Dependency Injection
========================================

Provides database session and authentication dependencies for FastAPI endpoints.
Works with the Hybrid Monolith pattern - imports from root.
"""

from typing import Generator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

# Import from ROOT - Single Source of Truth
from database import session_factory, User, SessionLog

# Import security utilities
from api.core.security import decode_token


# ==========================================
# DATABASE DEPENDENCY
# ==========================================

def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency for FastAPI.
    
    Yields a session that is properly closed after use.
    The smart @with_db decorator in services.py will detect this
    injected session and use it instead of creating its own.
    
    Usage:
        @router.post("/")
        def create_item(db: Session = Depends(get_db)):
            return SomeService.some_method(db=db, ...)
    """
    # Use session_factory() directly — NOT SessionLocal (scoped_session).
    # scoped_session uses thread-local storage which causes concurrency bugs
    # when FastAPI's threadpool reuses threads across requests.
    # session_factory() creates a fresh, independent session per request.
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# AUTHENTICATION DEPENDENCIES
# ==========================================

# OAuth2 scheme pointing to the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Validate JWT token and return current user.
    
    This dependency:
    1. Extracts the Bearer token from Authorization header
    2. Decodes and validates the JWT
    3. Checks token expiration
    4. Queries the database for the user
    5. Returns the User model or raises 401
    
    Usage:
        @router.post("/protected")
        def protected_endpoint(current_user: User = Depends(get_current_user)):
            # current_user is guaranteed to be valid
            return {"user": current_user.username}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    
    # Validate token type (should be access token)
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Use access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract username from 'sub' claim
    username: Optional[str] = payload.get("sub")
    if username is None:
        raise credentials_exception

    # VULN-004: Session revocation check
    session_id = payload.get("sid")
    if session_id:
        session = db.query(SessionLog).filter(
            SessionLog.session_id == session_id
        ).first()
        if session is None or session.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Query database for user
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


def get_current_user_optional(
    token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication - returns user if token valid, None otherwise.
    
    Useful for endpoints that have different behavior for authenticated
    vs anonymous users but don't require authentication.
    """
    if token is None:
        return None

    payload = decode_token(token)
    if payload is None:
        return None

    username = payload.get("sub")
    if username is None:
        return None

    # VULN-004: Session revocation check
    session_id = payload.get("sid")
    if session_id:
        session = db.query(SessionLog).filter(
            SessionLog.session_id == session_id
        ).first()
        if session is None or session.status != "active":
            return None

    return db.query(User).filter(User.username == username).first()


# ==========================================
# ROLE-BASED ACCESS CONTROL (RBAC)
# ==========================================

def require_role(*allowed_roles: str):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.post("/admin-only")
        def endpoint(current_user: User = Depends(require_role("admin"))):
            ...

        @router.patch("/admin-or-supervisor")
        def endpoint(current_user: User = Depends(require_role("admin", "supervisor"))):
            ...
    """
    def _role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = (current_user.role or "").lower().strip()
        if user_role not in {r.lower() for r in allowed_roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return _role_checker
