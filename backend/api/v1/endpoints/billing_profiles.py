"""
Hotel PMS API — BillingProfile endpoints (v1.10.0 — Phase 2a-ext).
====================================================================

Profiles are nested under a guest in the URL:
  /api/v1/huespedes/{guest_id}/billing[/...]

Reads (GET): admin / supervisor / gerencia / recepcion / recepcionista.
Writes (POST/PUT/DELETE): admin / supervisor / gerencia / recepcion /
                          recepcionista — receptionists routinely register
                          new billing profiles at check-in time.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_role
from database import User
from logging_config import get_logger
from schemas import BillingProfileCreate, BillingProfileDTO, BillingProfileUpdate
from services import BillingProfileError, BillingProfileService, GuestService

logger = get_logger(__name__)

router = APIRouter()

PROPERTY_ID = "los-monges"

_READ_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")
_WRITE_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")


def _to_dto(prof) -> BillingProfileDTO:
    return BillingProfileDTO(
        id=prof.id,
        guest_id=prof.guest_id,
        property_id=prof.property_id,
        label=prof.label,
        is_default=bool(prof.is_default),
        tax_id_type=prof.tax_id_type,
        tax_id_number=prof.tax_id_number,
        business_name=prof.business_name,
        address=prof.address,
        city=prof.city,
        state=prof.state,
        country=prof.country,
        is_active=bool(prof.is_active),
        created_at=prof.created_at,
        updated_at=prof.updated_at,
    )


def _ensure_guest(db: Session, guest_id: int):
    g = GuestService.get_guest(db=db, guest_id=guest_id)
    if g is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe huésped con id {guest_id}",
        )
    return g


@router.get(
    "/huespedes/{guest_id}/billing",
    response_model=List[BillingProfileDTO],
    summary="Listar perfiles de facturación del huésped",
)
def list_profiles(
    guest_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    _ensure_guest(db, guest_id)
    rows = BillingProfileService.get_profiles(
        db=db, guest_id=guest_id, active_only=active_only
    )
    return [_to_dto(p) for p in rows]


@router.post(
    "/huespedes/{guest_id}/billing",
    response_model=BillingProfileDTO,
    summary="Crear perfil de facturación",
)
def create_profile(
    guest_id: int,
    payload: BillingProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    g = _ensure_guest(db, guest_id)
    try:
        prof = BillingProfileService.create_profile(
            db=db, guest_id=guest_id, property_id=g.property_id,
            data=payload.model_dump(),
        )
    except BillingProfileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _to_dto(prof)


@router.put(
    "/huespedes/{guest_id}/billing/{profile_id}",
    response_model=BillingProfileDTO,
    summary="Actualizar perfil de facturación",
)
def update_profile(
    guest_id: int,
    profile_id: int,
    payload: BillingProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _ensure_guest(db, guest_id)
    try:
        prof = BillingProfileService.update_profile(
            db=db, profile_id=profile_id, data=payload.model_dump(exclude_unset=True),
        )
    except BillingProfileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if prof is None or prof.guest_id != guest_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe perfil de facturación {profile_id} para este huésped",
        )
    return _to_dto(prof)


@router.delete(
    "/huespedes/{guest_id}/billing/{profile_id}",
    summary="Dar de baja perfil de facturación (soft delete)",
)
def delete_profile(
    guest_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _ensure_guest(db, guest_id)
    prof = BillingProfileService.get_profile(db=db, profile_id=profile_id)
    if prof is None or prof.guest_id != guest_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe perfil de facturación {profile_id} para este huésped",
        )
    BillingProfileService.delete_profile(db=db, profile_id=profile_id)
    return {"message": "Perfil dado de baja", "id": profile_id}


@router.post(
    "/huespedes/{guest_id}/billing/{profile_id}/default",
    response_model=BillingProfileDTO,
    summary="Marcar perfil como predeterminado",
)
def set_default_profile(
    guest_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _ensure_guest(db, guest_id)
    try:
        prof = BillingProfileService.set_default(
            db=db, guest_id=guest_id, profile_id=profile_id,
        )
    except BillingProfileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if prof is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe perfil de facturación {profile_id} para este huésped",
        )
    return _to_dto(prof)
