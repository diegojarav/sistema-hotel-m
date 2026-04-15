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
from services import ReservationService, DocumentService
from schemas import (
    ReservationCreate,
    ReservationDTO,
    ReservationDetailDTO,
    StatusUpdateRequest,
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
        created_ids = ReservationService.create_reservations(db, data)
        # Auto-generate PDF confirmations
        for res_id in created_ids:
            try:
                DocumentService.generate_reservation_pdf(db, res_id)
            except Exception as pdf_err:
                logger.warning(f"PDF generation failed for reservation {res_id}: {pdf_err}")
        return created_ids
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
    "/monthly-view",
    summary="Monthly Room View",
    description="Get room x day matrix for a full month."
)
def get_monthly_view(
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get monthly room view matrix for the planning board."""
    return ReservationService.get_monthly_room_view(db, year, month)


@router.get(
    "/source-stats",
    summary="Source Distribution",
    description="Get reservation count and revenue grouped by booking source."
)
def get_source_stats(
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get booking source distribution stats."""
    return ReservationService.get_source_distribution(db, start_date, end_date)


@router.get(
    "/parking-usage",
    summary="Parking Usage",
    description="Get daily parking slot usage vs capacity."
)
def get_parking_usage(
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get parking utilization data."""
    return ReservationService.get_parking_usage(db, start_date, end_date)


@router.get(
    "/revenue-matrix",
    summary="Revenue Matrix",
    description="Get revenue by room and month for a full year."
)
def get_revenue_matrix(
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get annual revenue matrix by room x month."""
    return ReservationService.get_revenue_by_room_month(db, year)


@router.get(
    "/room-report",
    summary="Room Report",
    description="Get detailed reservation report for a specific room or all rooms in a date range."
)
def get_room_report(
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    room_id: str = Query(default=None, description="Room internal_code. Omit for all rooms."),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get per-room reservation report with summary stats."""
    return ReservationService.get_room_report(db, start_date, end_date, room_id)

@router.get(
    "/needs-review",
    summary="Reservations flagged for operator review (v1.5.0)",
    description="Lists reservations whose OTA UID disappeared from the source feed "
                "and need operator confirmation."
)
def list_needs_review_pre(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List reservations with needs_review=True. Defined before /{reservation_id}
    so the literal path matches first."""
    from database import Reservation
    rows = (
        db.query(Reservation)
        .filter(Reservation.needs_review == True)
        .order_by(Reservation.check_in_date.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "guest_name": r.guest_name,
            "check_in_date": r.check_in_date.isoformat() if r.check_in_date else None,
            "stay_days": r.stay_days,
            "room_id": r.room_id,
            "source": r.source,
            "status": r.status,
            "review_reason": r.review_reason,
            "price": r.price,
            "external_id": r.external_id,
            "ota_booking_id": r.ota_booking_id,
        }
        for r in rows
    ]


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
    reservation = ReservationService.get_reservation_detail(db, reservation_id)

    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found"
        )

    return reservation


@router.get(
    "/{reservation_id}/saldo",
    summary="Saldo de pagos de una reserva",
    description="Retorna total, pagado, pendiente y listado de transacciones activas."
)
def get_reservation_saldo(
    reservation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get payment balance for a reservation."""
    from services import TransaccionService
    saldo = TransaccionService.get_saldo(db, reservation_id)
    if not saldo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reservation {reservation_id} not found"
        )
    # Serialize transactions
    saldo["transacciones"] = [
        {
            "id": t.id,
            "amount": t.amount,
            "payment_method": t.payment_method,
            "reference_number": t.reference_number,
            "description": t.description,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "created_by": t.created_by,
            "voided": t.voided,
        }
        for t in saldo["transacciones"]
    ]
    return saldo


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


@router.put(
    "/{reservation_id}/status",
    summary="Update Reservation Status",
    description="Change reservation status. Valid: Pendiente, Confirmada, Completada, Cancelada."
)
def update_reservation_status(
    reservation_id: str,
    data: StatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update reservation status."""
    success = ReservationService.update_status(
        db, reservation_id, data.status, data.reason, current_user.username
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo cambiar el estado de la reserva {reservation_id}. Verifique que existe y que el cambio es valido."
        )

    return {"message": f"Estado actualizado a {data.status}", "id": reservation_id}


# ==========================================
# v1.5.0 — Channel Manager v2: review/cancellation endpoints
# (Note: GET /needs-review is defined above, before /{reservation_id})
# ==========================================

@router.post(
    "/{reservation_id}/acknowledge-review",
    summary="Acknowledge review (keep reservation active)",
    description="Operator confirms the reservation should remain active despite "
                "having been flagged by the OTA sync. Clears needs_review."
)
def acknowledge_review(
    reservation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Clear needs_review flag for a reservation."""
    from database import Reservation
    r = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Reserva {reservation_id} no encontrada")
    if not r.needs_review:
        return {"message": "Reservation was not flagged for review", "id": reservation_id}
    r.needs_review = False
    r.review_reason = None
    db.commit()
    logger.info(
        f"Review acknowledged: reservation {reservation_id} kept active by {current_user.username}"
    )
    return {"message": "Acknowledged — reservation kept active", "id": reservation_id}


@router.post(
    "/{reservation_id}/confirm-ota-cancellation",
    summary="Confirm OTA-initiated cancellation",
    description="Operator confirms the reservation was cancelled by the guest via OTA. "
                "Sets status=CANCELADA with the review reason."
)
def confirm_ota_cancellation(
    reservation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark a flagged reservation as CANCELADA."""
    from database import Reservation
    r = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Reserva {reservation_id} no encontrada")
    reason = r.review_reason or "Cancelada por OTA (confirmada por operador)"
    success = ReservationService.cancel_reservation(
        reservation_id, reason, current_user.username
    )
    if not success:
        raise HTTPException(status_code=400, detail="No se pudo cancelar la reserva")
    # Clear review flag (cancel_reservation may not touch it)
    r2 = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if r2:
        r2.needs_review = False
        db.commit()
    logger.info(
        f"OTA cancellation confirmed: reservation {reservation_id} cancelled by {current_user.username}"
    )
    return {"message": "Reservation cancelled (CANCELADA)", "id": reservation_id}
