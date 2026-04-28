"""
Hotel PMS API — GuestVehicle endpoints (v1.10.0 — Phase 2a-ext).
====================================================================

Three URL clusters:

  /api/v1/huespedes/{guest_id}/vehicles[/...]   — guest's registered vehicles
  /api/v1/vehicles/search?plate=...             — "whose car is this?" lookup
  /api/v1/checkins/{checkin_id}/vehicles[/...]   — per-stay parking link

Reads (GET): admin / supervisor / gerencia / recepcion / recepcionista.
Writes: same set — recepción manages vehicles at check-in.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_role
from database import User
from logging_config import get_logger
from schemas import (
    CheckinVehicleDTO,
    CheckinVehicleLink,
    GuestVehicleCreate,
    GuestVehicleDTO,
    GuestVehicleUpdate,
    VehicleSearchResultDTO,
    GuestDTO,
)
from services import (
    GuestService,
    GuestVehicleError,
    GuestVehicleService,
)

logger = get_logger(__name__)

router = APIRouter()

PROPERTY_ID = "los-monges"

_READ_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")
_WRITE_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")


def _to_dto(v) -> GuestVehicleDTO:
    return GuestVehicleDTO(
        id=v.id,
        guest_id=v.guest_id,
        property_id=v.property_id,
        plate_number=v.plate_number,
        model=v.model,
        color=v.color,
        is_active=bool(v.is_active),
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _guest_to_dto(g) -> GuestDTO:
    return GuestDTO(
        id=g.id,
        property_id=g.property_id,
        first_name=g.first_name,
        last_name=g.last_name,
        document_type=g.document_type,
        document_number=g.document_number,
        email=g.email,
        phone=g.phone,
        nationality=g.nationality,
        country=g.country,
        city=g.city,
        notes=g.notes,
        source=g.source,
        birth_date=g.birth_date,
        is_active=bool(g.is_active),
        total_stays=g.total_stays or 0,
        total_spent=float(g.total_spent or 0.0),
        last_visit_at=g.last_visit_at,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


def _ensure_guest(db: Session, guest_id: int):
    g = GuestService.get_guest(db=db, guest_id=guest_id)
    if g is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe huésped con id {guest_id}",
        )
    return g


# ----------------------------------------------------------------------
# Vehicles per guest
# ----------------------------------------------------------------------

@router.get(
    "/huespedes/{guest_id}/vehicles",
    response_model=List[GuestVehicleDTO],
    summary="Listar vehículos registrados del huésped",
)
def list_vehicles(
    guest_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    _ensure_guest(db, guest_id)
    rows = GuestVehicleService.get_vehicles(
        db=db, guest_id=guest_id, active_only=active_only,
    )
    return [_to_dto(v) for v in rows]


@router.post(
    "/huespedes/{guest_id}/vehicles",
    response_model=GuestVehicleDTO,
    summary="Registrar vehículo (máx. 5 por huésped)",
)
def create_vehicle(
    guest_id: int,
    payload: GuestVehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    g = _ensure_guest(db, guest_id)
    try:
        v = GuestVehicleService.create_vehicle(
            db=db, guest_id=guest_id, property_id=g.property_id,
            data=payload.model_dump(),
        )
    except GuestVehicleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _to_dto(v)


@router.put(
    "/huespedes/{guest_id}/vehicles/{vehicle_id}",
    response_model=GuestVehicleDTO,
    summary="Actualizar vehículo",
)
def update_vehicle(
    guest_id: int,
    vehicle_id: int,
    payload: GuestVehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _ensure_guest(db, guest_id)
    try:
        v = GuestVehicleService.update_vehicle(
            db=db, vehicle_id=vehicle_id, data=payload.model_dump(exclude_unset=True),
        )
    except GuestVehicleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if v is None or v.guest_id != guest_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe vehículo {vehicle_id} para este huésped",
        )
    return _to_dto(v)


@router.delete(
    "/huespedes/{guest_id}/vehicles/{vehicle_id}",
    summary="Dar de baja vehículo (soft delete)",
)
def delete_vehicle(
    guest_id: int,
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    _ensure_guest(db, guest_id)
    v = GuestVehicleService.get_vehicle(db=db, vehicle_id=vehicle_id)
    if v is None or v.guest_id != guest_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe vehículo {vehicle_id} para este huésped",
        )
    GuestVehicleService.delete_vehicle(db=db, vehicle_id=vehicle_id)
    return {"message": "Vehículo dado de baja", "id": vehicle_id}


# ----------------------------------------------------------------------
# Plate search — "whose car is this?" + future OCR
# ----------------------------------------------------------------------

@router.get(
    "/vehicles/search",
    response_model=VehicleSearchResultDTO,
    summary="Buscar vehículo por chapa (lookup + OCR future)",
    description=(
        "Busca un vehículo registrado por chapa (case-insensitive, exact match "
        "primero, partial luego). Retorna el vehículo, el huésped propietario "
        "y la reserva activa o próxima si existe. Pensado para el lookup en "
        "recepción (\"¿de quién es el auto blanco?\") y el futuro pipeline "
        "OCR de reconocimiento automático en la entrada."
    ),
)
def search_vehicle_by_plate(
    plate: str = Query(..., min_length=2, description="Chapa o fragmento (mín 2 chars)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    result = GuestVehicleService.search_by_plate(
        db=db, property_id=PROPERTY_ID, plate=plate,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún vehículo con chapa '{plate}'",
        )
    return VehicleSearchResultDTO(
        vehicle=_to_dto(result["vehicle"]),
        guest=_guest_to_dto(result["guest"]),
        active_reservation=result.get("active_reservation"),
    )


# ----------------------------------------------------------------------
# Per-stay link (CheckinVehicle)
# ----------------------------------------------------------------------

@router.get(
    "/checkins/{checkin_id}/vehicles",
    response_model=List[CheckinVehicleDTO],
    summary="Vehículos asociados a esta ficha (estadía)",
)
def list_checkin_vehicles(
    checkin_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    rows = GuestVehicleService.get_checkin_vehicles(db=db, checkin_id=checkin_id)
    return [CheckinVehicleDTO(**r) for r in rows]


@router.post(
    "/checkins/{checkin_id}/vehicles/{vehicle_id}",
    response_model=CheckinVehicleDTO,
    summary="Vincular vehículo a la ficha actual",
)
def link_checkin_vehicle(
    checkin_id: int,
    vehicle_id: int,
    payload: CheckinVehicleLink,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    try:
        link = GuestVehicleService.link_to_checkin(
            db=db, checkin_id=checkin_id, vehicle_id=vehicle_id,
            parking_spot=payload.parking_spot, key_deposited=payload.key_deposited,
        )
    except GuestVehicleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    rows = GuestVehicleService.get_checkin_vehicles(db=db, checkin_id=checkin_id)
    match = next((r for r in rows if r["id"] == link.id), None)
    return CheckinVehicleDTO(**(match or {
        "id": link.id, "checkin_id": link.checkin_id,
        "vehicle_id": link.vehicle_id, "parking_spot": link.parking_spot,
        "key_deposited": bool(link.key_deposited), "created_at": link.created_at,
    }))


@router.delete(
    "/checkins/{checkin_id}/vehicles/{vehicle_id}",
    summary="Desvincular vehículo de la ficha",
)
def unlink_checkin_vehicle(
    checkin_id: int,
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    ok = GuestVehicleService.unlink_from_checkin(
        db=db, checkin_id=checkin_id, vehicle_id=vehicle_id,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe el vínculo entre esta ficha y el vehículo",
        )
    return {"message": "Vehículo desvinculado de la ficha"}
