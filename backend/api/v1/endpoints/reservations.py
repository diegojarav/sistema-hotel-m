"""
Hotel PMS API - Reservation Endpoints
=========================================

HYBRID MONOLITH: Imports from root services.py and schemas.py

SECURITY: All endpoints require authentication (VULN-003 fix)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import date

# Import from API deps
from api.deps import get_db, get_current_user
from logging_config import get_logger

logger = get_logger(__name__)

# IMPORT FROM ROOT - Single Source of Truth
from services import ReservationService
from schemas import (
    ReservationCreate,
    ReservationDTO,
    CalendarEventDTO,
    TodaySummaryDTO
)

router = APIRouter()


# ==========================================
# API-SPECIFIC SCHEMAS
# ==========================================

from pydantic import BaseModel, Field


class CancelReservationRequest(BaseModel):
    """Request to cancel a reservation."""
    reason: str = Field(default="", description="Cancellation reason")
    cancelled_by: str = Field(..., description="User who cancelled")


class ReservationDetailDTO(BaseModel):
    """Detailed reservation for editing."""
    id: str
    check_in_date: date
    stay_days: int
    guest_name: str
    room_id: str
    room_type: str
    price: float
    arrival_time: str | None
    reserved_by: str
    contact_phone: str
    received_by: str
    status: str


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "",
    response_model=List[ReservationDTO],
    summary="List Reservations",
    description="Get all reservations ordered by creation date. Supports pagination. Requires authentication."
)
def list_reservations(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all reservations with pagination using the original ReservationService."""
    # PERF-004: Add pagination support
    all_reservations = ReservationService.get_all_reservations(db)
    return all_reservations[skip:skip + limit]


@router.post(
    "",
    response_model=List[str],
    status_code=status.HTTP_201_CREATED,
    summary="Create Reservation",
    description="Create a new reservation. Creates one reservation per room if multiple rooms selected."
)
def create_reservation(
    data: ReservationCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # 🔒 Protected
):
    """
    Create a new reservation using the original ReservationService.
    
    Requires authentication.
    """
    try:
        return ReservationService.create_reservations(db, data)
    except Exception as e:
        logger.error(f"Failed to create reservation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la reserva. Intente de nuevo."
        )


@router.get(
    "/weekly",
    response_model=Dict[str, Dict[str, str]],
    summary="Get Weekly View",
    description="Get room occupancy matrix for a week. Requires authentication."
)
def get_weekly_view(
    start_date: date = Query(default=None, description="First day of the week"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get weekly room occupancy matrix."""
    check_date = start_date or date.today()
    return ReservationService.get_weekly_view(db, check_date)


@router.get(
    "/{reservation_id}",
    summary="Get Reservation",
    description="Get detailed information about a specific reservation. Requires authentication."
)
def get_reservation(
    reservation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get reservation details by ID."""
    reservation = ReservationService.get_reservation(db, reservation_id)
    
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found"
        )
    
    return reservation


@router.put(
    "/{reservation_id}",
    summary="Update Reservation",
    description="Update an existing reservation."
)
def update_reservation(
    reservation_id: str,
    data: ReservationCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # 🔒 Protected
):
    """Update a reservation."""
    success = ReservationService.update_reservation(db, reservation_id, data)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found"
        )
    
    return {"message": "Reservation updated successfully", "id": reservation_id}


@router.post(
    "/{reservation_id}/cancel",
    summary="Cancel Reservation",
    description="Cancel an existing reservation."
)
def cancel_reservation(
    reservation_id: str,
    data: CancelReservationRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # 🔒 Protected
):
    """Cancel a reservation."""
    success = ReservationService.cancel_reservation(
        db, reservation_id, data.reason, data.cancelled_by
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found"
        )
    
    return {"message": "Reservation cancelled successfully", "id": reservation_id}
