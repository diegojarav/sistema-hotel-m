"""
Hotel Munich API - Authentication Endpoints
============================================

HYBRID MONOLITH: Imports from root services.py and schemas.py
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Import from API deps
from api.deps import get_db

# IMPORT FROM ROOT - Single Source of Truth
from services import AuthService
from schemas import UserDTO

router = APIRouter()


# ==========================================
# SCHEMAS (API-specific, not in root schemas.py)
# ==========================================

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request body for login endpoint."""
    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class LoginResponse(BaseModel):
    """Response from successful login."""
    user: UserDTO
    message: str = "Login successful"


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login",
    description="Authenticate a user with username and password."
)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return user data.
    
    The smart @with_db decorator in services.py will detect the
    injected db session and use it directly (FastAPI mode).
    """
    # Call the ORIGINAL service, passing db explicitly
    user = AuthService.authenticate(db, credentials.username, credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    return LoginResponse(user=user, message="Login successful")
