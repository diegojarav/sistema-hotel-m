"""
Hotel PMS API - User Management Endpoints
==========================================

Admin endpoints for user CRUD operations.
All endpoints require authentication and admin role.

V9 FIX: Created to replace direct database access in Admin_Users.py
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Import from API deps
from api.deps import get_db, get_current_user, require_role

# Import security utilities
from api.core.security import get_password_hash

# Service layer
from services import AuthService

# IMPORT FROM ROOT - Single Source of Truth
from database import User, SessionLog

router = APIRouter()


# ==========================================
# SCHEMAS
# ==========================================

class UserDTO(BaseModel):
    """User information (no password hash)."""
    id: int
    username: str
    real_name: Optional[str] = None
    role: Optional[str] = None
    is_password_hashed: bool


class CreateUserRequest(BaseModel):
    """Request to create a new user."""
    username: str
    password: str
    role: str
    real_name: str


class ResetPasswordRequest(BaseModel):
    """Request to reset a user's password."""
    new_password: str


class SessionLogDTO(BaseModel):
    """Session log information."""
    session_id: Optional[str] = None
    username: str
    login_time: Optional[str] = None
    logout_time: Optional[str] = None
    device_type: Optional[str] = None
    status: Optional[str] = None


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "",
    response_model=List[UserDTO],
    summary="List All Users",
    description="Get all users. Admin only."
)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Get all users (without password hashes)."""

    users = db.query(User).all()

    return [
        UserDTO(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            role=u.role,
            is_password_hashed=u.password.startswith('$2') if u.password else False
        )
        for u in users
    ]


@router.post(
    "",
    response_model=dict,
    summary="Create User",
    description="Create a new user with hashed password. Admin only."
)
def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Create a new user with bcrypt-hashed password."""

    # Check if username already exists
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Validate input
    if len(request.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")

    # Hash password and create user
    hashed_password = get_password_hash(request.password)

    new_user = User(
        username=request.username,
        password=hashed_password,
        role=request.role,
        real_name=request.real_name
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"success": True, "message": "User created", "id": new_user.id}


@router.patch(
    "/{user_id}/password",
    response_model=dict,
    summary="Reset Password",
    description="Reset a user's password. Admin only."
)
def reset_password(
    user_id: int,
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Reset a user's password with a new bcrypt hash."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if len(request.new_password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    # Hash and update password
    user.password = get_password_hash(request.new_password)

    # VULN-004: Invalidate all existing sessions (force re-login with new password)
    AuthService.close_user_sessions(db, user.username, reason="password_reset")

    db.commit()

    return {"success": True, "message": f"Password reset for {user.username}"}


@router.delete(
    "/{user_id}",
    response_model=dict,
    summary="Delete User",
    description="Delete a user. Admin only."
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete a user from the database."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    username = user.username

    # VULN-004: Close all active sessions before deleting user
    AuthService.close_user_sessions(db, username, reason="user_deleted")

    db.delete(user)
    db.commit()

    return {"success": True, "message": f"User {username} deleted"}


@router.get(
    "/sessions",
    response_model=List[SessionLogDTO],
    summary="Get Session Logs",
    description="Get recent session logs. Admin only."
)
def get_session_logs(
    username: Optional[str] = Query(None, description="Filter by username"),
    limit: int = Query(100, description="Max results to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Get session logs for monitoring user activity."""

    query = db.query(SessionLog).order_by(SessionLog.login_time.desc())

    if username:
        query = query.filter(SessionLog.username == username)

    sessions = query.limit(limit).all()

    return [
        SessionLogDTO(
            session_id=s.session_id,
            username=s.username,
            login_time=s.login_time.isoformat() if s.login_time else None,
            logout_time=s.logout_time.isoformat() if s.logout_time else None,
            device_type=s.device_type,
            status=s.status
        )
        for s in sessions
    ]
