"""
Hotel API — Kitchen Reports Endpoints (v1.7.0 — Phase 4)
=========================================================

Daily kitchen report: total breakfast count + per-room breakdown + PDF export.

Access is granted to admin, recepcion, supervisor, gerencia, and the new
COCINA role (read-only kitchen staff — sees this page only).
"""

from datetime import date as _date, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_db, require_role
from database import User
from logging_config import get_logger
from services import KitchenReportService, DocumentService

logger = get_logger(__name__)
router = APIRouter()


# Roles that may view the kitchen report
KITCHEN_ROLES = ("admin", "recepcion", "supervisor", "gerencia", "cocina")


# ==========================================
# SCHEMAS
# ==========================================

class KitchenReportRoomDTO(BaseModel):
    reservation_id: str
    room_id: str
    internal_code: str
    room_type: str
    guest_name: str
    guests_count: int
    breakfast_guests: int
    plan_id: Optional[str] = None
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    checkout_date: str
    checkout_today: bool
    check_in_date: Optional[str] = None


class KitchenReportDTO(BaseModel):
    enabled: bool
    fecha: str
    property_id: str
    mode: Optional[str] = None
    total_with_breakfast: int
    total_without: int
    rooms: List[KitchenReportRoomDTO]


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "/cocina",
    response_model=KitchenReportDTO,
    summary="Kitchen Daily Report",
    description=(
        "Returns total breakfast count + per-room detail for the given date. "
        "When meals are disabled for the hotel, returns enabled=false and "
        "empty rooms list (callers should render 'Servicio no habilitado')."
    ),
)
def get_kitchen_report(
    fecha: Optional[str] = Query(
        None,
        description="Fecha YYYY-MM-DD. Default: mañana (modo planificación).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*KITCHEN_ROLES)),
):
    try:
        target = _date.fromisoformat(fecha) if fecha else _date.today() + timedelta(days=1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de fecha inválido. Use YYYY-MM-DD.",
        )
    report = KitchenReportService.get_daily_report(db=db, fecha=target)
    return report


@router.get(
    "/cocina/pdf",
    summary="Kitchen Daily Report PDF",
    description="Generate and download the kitchen report PDF for the given date.",
)
def get_kitchen_report_pdf(
    fecha: Optional[str] = Query(None, description="Fecha YYYY-MM-DD. Default: mañana."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*KITCHEN_ROLES)),
):
    try:
        target = _date.fromisoformat(fecha) if fecha else _date.today() + timedelta(days=1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de fecha inválido. Use YYYY-MM-DD.",
        )
    path = DocumentService.generate_kitchen_report_pdf(db=db, fecha=target)
    if not path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servicio de comidas no habilitado.",
        )
    filename = f"cocina_{target.strftime('%Y%m%d')}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)
