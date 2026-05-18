"""
Hotel PMS API — Master Guest entity endpoints (v1.10.0 — Phase 2a)
====================================================================

Routes for the new `Guest` master entity (one row per person across stays).

URL convention
--------------
Path is Spanish (`/api/v1/huespedes/`) to keep this distinct from the
historical `/api/v1/guests/` URL which manages per-stay CheckIn records
(legacy naming preserved for mobile/PC compatibility — see `guests.py`
docstring).

Permissions
-----------
- All endpoints require authentication.
- Reads (GET) are accessible to admin / supervisor / gerencia / recepcion /
  recepcionista (every operator who books or assists guests). Cocina
  excluded — they don't interact with guests.
- Writes (POST/PUT) are accessible to admin / supervisor / gerencia /
  recepcion / recepcionista. Reception staff are routinely the ones who
  edit guest data when a guest's contact info changes during a stay.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.core.config import DEFAULT_PROPERTY_ID
from api.deps import get_db, require_role
from database import User
from logging_config import get_logger
from schemas import (
    GuestCreate,
    GuestDTO,
    GuestHistoryDTO,
    GuestReservationItemDTO,
    GuestSearchResult,
    GuestUpdate,
)
from services import GuestService, GuestServiceError

logger = get_logger(__name__)

router = APIRouter()


# Default property — single-tenant today. Per skill §4 the eventual
# multi-tenant migration will derive this from the authenticated user.
PROPERTY_ID = DEFAULT_PROPERTY_ID

# Common role tuples to keep the @router.get(...) signatures readable.
_READ_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")
_WRITE_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")


# ----------------------------------------------------------------------
# Response wrappers
# ----------------------------------------------------------------------
class GuestListResponse(BaseModel):
    items: List[GuestDTO]
    total: int
    skip: int
    limit: int


def _to_dto(guest) -> GuestDTO:
    return GuestDTO(
        id=guest.id,
        property_id=guest.property_id,
        first_name=guest.first_name,
        last_name=guest.last_name,
        document_type=guest.document_type,
        document_number=guest.document_number,
        email=guest.email,
        phone=guest.phone,
        nationality=guest.nationality,
        country=guest.country,
        city=guest.city,
        notes=guest.notes,
        source=guest.source,
        is_active=bool(guest.is_active),
        total_stays=guest.total_stays or 0,
        total_spent=float(guest.total_spent or 0.0),
        last_visit_at=guest.last_visit_at,
        created_at=guest.created_at,
        updated_at=guest.updated_at,
    )


def _to_search_result(guest) -> GuestSearchResult:
    label_parts = [guest.last_name or "", guest.first_name or ""]
    name_label = ", ".join(p for p in label_parts if p)
    if guest.document_number:
        name_label = f"{name_label} ({guest.document_number})"
    return GuestSearchResult(
        id=guest.id,
        first_name=guest.first_name,
        last_name=guest.last_name,
        document_number=guest.document_number,
        email=guest.email,
        phone=guest.phone,
        total_stays=guest.total_stays or 0,
        label=name_label or "(sin nombre)",
    )


# ----------------------------------------------------------------------
# Endpoints — placed in routing-priority order: static paths first, path
# params last (FastAPI matches in declaration order).
# ----------------------------------------------------------------------

@router.get(
    "/search",
    response_model=List[GuestSearchResult],
    summary="Buscar huéspedes (autocomplete)",
    description="Search guests by name, document, email, or phone. Used by reservation autocomplete.",
)
def search_guests(
    q: str = Query(..., min_length=2, description="Texto a buscar (mín 2 caracteres)"),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    results = GuestService.search_guests(
        db=db, property_id=PROPERTY_ID, query=q, limit=limit
    )
    return [_to_search_result(g) for g in results]


@router.get(
    "/dropdown",
    response_model=List[dict],
    summary="Listado para dropdown de reserva/ficha",
    description=(
        "Optimised list for the PC reservation form + mobile new-reservation autocomplete. "
        "Returns clean labels (no embedded `(DocNumber)` strings — Phase 2a Bug #1 fix), "
        "sorted by total_stays DESC. Each item carries the guest_id to send back as "
        "`ReservationCreate.guest_id`."
    ),
)
def list_guests_for_dropdown(
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    return GuestService.list_guests_for_dropdown(
        db=db, property_id=PROPERTY_ID, limit=limit,
    )


@router.get(
    "",
    response_model=GuestListResponse,
    summary="Listar huéspedes",
)
def list_guests(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    items = GuestService.list_guests(
        db=db,
        property_id=PROPERTY_ID,
        skip=skip,
        limit=limit,
        active_only=active_only,
    )
    total = GuestService.count_guests(
        db=db, property_id=PROPERTY_ID, active_only=active_only
    )
    return GuestListResponse(
        items=[_to_dto(g) for g in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=GuestDTO,
    summary="Crear huésped",
)
def create_guest(
    payload: GuestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    try:
        data = payload.model_dump()
        property_id = data.pop("property_id", None) or PROPERTY_ID
        guest = GuestService.create_guest(db=db, property_id=property_id, data=data)
        return _to_dto(guest)
    except GuestServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{guest_id}",
    response_model=GuestDTO,
    summary="Detalle de huésped",
)
def get_guest(
    guest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    g = GuestService.get_guest(db=db, guest_id=guest_id)
    if not g:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe huésped con id {guest_id}",
        )
    return _to_dto(g)


@router.put(
    "/{guest_id}",
    response_model=GuestDTO,
    summary="Actualizar huésped",
)
def update_guest(
    guest_id: int,
    payload: GuestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    data = payload.model_dump(exclude_unset=True)
    g = GuestService.update_guest(db=db, guest_id=guest_id, data=data)
    if not g:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe huésped con id {guest_id}",
        )
    return _to_dto(g)


@router.get(
    "/{guest_id}/history",
    response_model=GuestHistoryDTO,
    summary="Historial de reservas del huésped",
)
def get_guest_history(
    guest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    h = GuestService.get_guest_history(db=db, guest_id=guest_id)
    if not h:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe huésped con id {guest_id}",
        )
    return GuestHistoryDTO(
        guest=_to_dto(h["guest"]),
        reservations=[
            GuestReservationItemDTO(**r) for r in h["reservations"]
        ],
        total_stays=h["total_stays"],
        total_spent=h["total_spent"],
        last_visit_at=h["last_visit_at"],
        avg_stay_length=h["avg_stay_length"],
    )
