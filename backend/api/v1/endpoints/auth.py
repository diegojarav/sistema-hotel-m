"""
Hotel PMS API - Authentication Endpoints
============================================

OAuth2 Password Flow with JWT tokens.
Includes robust session tracking with device detection and beacon logout.

SECURITY HARDENED:
- Rate limiting: 5 login attempts per minute per IP
- Bcrypt-only password verification (no plaintext)
"""

from datetime import timedelta, datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Import from API deps
from api.deps import get_db

# Rate limiting
from api.main import limiter

# Import security utilities
from api.core.security import decode_token, create_access_token, create_refresh_token
from api.core.config import ACCESS_TOKEN_EXPIRE_MINUTES

# Service layer
from services import AuthService

# IMPORT FROM ROOT - Single Source of Truth
from database import User, SessionLog

router = APIRouter()


# ==========================================
# SCHEMAS
# ==========================================

class Token(BaseModel):
    """OAuth2 token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    """Request to refresh tokens."""
    refresh_token: str


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def detect_device_type(user_agent: str) -> str:
    """
    Detect device type from User-Agent header.
    Returns 'Mobile' for mobile devices, 'PC' otherwise.
    """
    ua_lower = user_agent.lower()
    mobile_keywords = ['android', 'iphone', 'mobile', 'ipad', 'ipod', 'blackberry', 'windows phone']
    if any(keyword in ua_lower for keyword in mobile_keywords):
        return 'Mobile'
    return 'PC'


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/login",
    response_model=Token,
    summary="User Login (OAuth2 Password Flow)",
    description="Authenticate with username and password. Returns JWT access and refresh tokens. Rate limited to 5 attempts per minute."
)
@limiter.limit("5/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    OAuth2 compatible login endpoint.

    Accepts form data (username, password) and returns JWT tokens.
    V1 FIX: Delegates to AuthService.login() (service layer pattern).
    """
    # Device detection from User-Agent (HTTP-layer logic stays here)
    user_agent = request.headers.get('user-agent', '')
    device_type = detect_device_type(user_agent)
    client_ip = request.client.host if request.client else None

    # Delegate to service layer
    result = AuthService.login(
        db,
        username=form_data.username,
        password=form_data.password,
        ip_address=client_ip,
        user_agent=user_agent,
        device_type=device_type
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(**result)


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh Tokens",
    description="Get new access and refresh tokens using a valid refresh token."
)
def refresh_tokens(
    request: TokenRefreshRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    
    Used for biometric login and session persistence.
    """
    # Decode and validate refresh token
    payload = decode_token(request.refresh_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify token type
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get username from token
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # VULN-004: Check session is still active before refreshing
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

    # Verify user still exists
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create new tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "sid": session_id},
        expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.username, "sid": session_id}
    )
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer"
    )


@router.post(
    "/logout",
    status_code=200,
    summary="Manual Logout",
    description="Explicitly log out and close the session."
)
def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Close session on manual logout.
    Sets closed_reason to 'manual_logout'.
    """
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header[7:]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    session_id = payload.get("sid")
    if session_id:
        db.query(SessionLog).filter(
            SessionLog.session_id == session_id
        ).update({
            "status": "closed",
            "logout_time": datetime.now(),
            "closed_reason": "manual_logout"
        })
        db.commit()
    
    return {"message": "Logged out successfully"}


@router.post(
    "/logout-beacon",
    status_code=204,
    summary="Beacon Logout (Tab Close)",
    description="Called by navigator.sendBeacon when browser tab closes. Returns immediately."
)
def logout_beacon(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Close session when browser tab is closed.
    
    Designed for navigator.sendBeacon - returns 204 No Content immediately.
    This endpoint is fire-and-forget; errors are silently ignored.
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_token(token)
            
            if payload and "sid" in payload:
                db.query(SessionLog).filter(
                    SessionLog.session_id == payload["sid"]
                ).update({
                    "status": "closed",
                    "logout_time": datetime.now(),
                    "closed_reason": "tab_closed"
                })
                db.commit()
    except Exception:
        # Beacon endpoints should never fail - just ignore errors
        pass
    
    return  # 204 No Content

