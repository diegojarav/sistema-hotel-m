"""
Hotel PMS API - Guest Endpoints
===================================

HYBRID MONOLITH: Imports from root services.py and schemas.py

SECURITY: All endpoints require authentication (VULN-003 fix)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List

# Import from API deps
from api.deps import get_db, get_current_user
from logging_config import get_logger

logger = get_logger(__name__)
from database import User

# IMPORT FROM ROOT - Single Source of Truth
from services import GuestService
from schemas import CheckInCreate

router = APIRouter()


# ==========================================
# API-SPECIFIC SCHEMAS
# ==========================================

from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


class CheckInDTO(BaseModel):
    """Check-in record for listing."""
    id: int
    room_id: Optional[str]
    last_name: str
    first_name: str
    document_number: str
    created_at: Optional[date]


class CheckInSearchResult(BaseModel):
    """Search result for check-ins."""
    id: int
    label: str


class BillingProfileDTO(BaseModel):
    """Billing profile from history."""
    name: str
    ruc: str


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "",
    response_model=List[dict],
    summary="List Check-Ins",
    description="Get all guest check-in records. Supports pagination. Requires authentication."
)
def list_checkins(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all check-ins with pagination using original GuestService."""
    # PERF-004: Add pagination support
    all_checkins = GuestService.search_checkins(db, "")
    return all_checkins[skip:skip + limit]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create Check-In",
    description="Register a new guest check-in (ficha). Requires authentication."
)
def create_checkin(
    data: CheckInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Register a new guest check-in."""
    try:
        checkin_id = GuestService.register_checkin(db, data)
        return {"message": "Check-in registered successfully", "id": checkin_id}
    except Exception as e:
        logger.error(f"Failed to register check-in: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar el check-in. Intente de nuevo."
        )


@router.get(
    "/search",
    response_model=List[dict],
    summary="Search Check-Ins",
    description="Search check-ins by name or document number. Requires authentication."
)
def search_checkins(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search check-ins by name, document, or billing name."""
    return GuestService.search_checkins(db, q)


@router.get(
    "/names",
    response_model=List[str],
    summary="Get All Guest Names",
    description="Get all guest names for autocomplete. Requires authentication."
)
def get_guest_names(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all guest names formatted for autocomplete."""
    return GuestService.get_all_guest_names(db)


@router.get(
    "/billing-profiles",
    response_model=List[dict],
    summary="Get Billing Profiles",
    description="Get all unique billing profiles for quick selection. Requires authentication."
)
def get_billing_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unique billing profiles."""
    return GuestService.get_all_billing_profiles(db)


@router.get(
    "/unlinked-reservations",
    response_model=List[dict],
    summary="Get Unlinked Reservations",
    description="Get reservations without a linked check-in. Used for linking in check-in form."
)
def get_unlinked_reservations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get reservations that can be linked to a check-in."""
    return GuestService.get_unlinked_reservations(db)


@router.get(
    "/billing-history/{document_number}",
    response_model=List[dict],
    summary="Get Billing History",
    description="Get billing history for a specific document number. Requires authentication."
)
def get_billing_history(
    document_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get billing profiles associated with a document number."""
    return GuestService.get_billing_history(db, document_number)


@router.get(
    "/{checkin_id}",
    summary="Get Check-In",
    description="Get check-in details by ID. Requires authentication."
)
def get_checkin(
    checkin_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get check-in details for editing."""
    checkin = GuestService.get_checkin(db, checkin_id)
    
    if not checkin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found"
        )
    
    return checkin


@router.put(
    "/{checkin_id}",
    summary="Update Check-In",
    description="Update an existing check-in record. Requires authentication."
)
def update_checkin(
    checkin_id: int,
    data: CheckInCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a check-in record."""
    success = GuestService.update_checkin(db, checkin_id, data)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in {checkin_id} not found"
        )
    
    return {"message": "Check-in updated successfully", "id": checkin_id}
