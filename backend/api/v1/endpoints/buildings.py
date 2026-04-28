"""
Hotel PMS API — Building entity endpoints (v1.10.0 — Phase 2a)
================================================================

CRUD for the new `buildings` table. Hotels with annexes or distinct wings
use this to group rooms beyond the floor + category dimensions.

Permissions
-----------
- Reads: any authenticated operator (admin / supervisor / gerencia /
  recepcion / recepcionista). The reception staff need to know which
  building a room belongs to.
- Writes: admin only. Creating/renaming/retiring a building is structural
  configuration.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_role
from database import User
from logging_config import get_logger
from schemas import BuildingCreate, BuildingDTO, BuildingUpdate
from services import BuildingService, BuildingServiceError

logger = get_logger(__name__)

router = APIRouter()

PROPERTY_ID = "los-monges"  # single-tenant for now

_READ_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")
_WRITE_ROLES = ("admin",)


def _to_dto(row: dict) -> BuildingDTO:
    return BuildingDTO(**row)


@router.get(
    "",
    response_model=List[BuildingDTO],
    summary="Listar edificios",
)
def list_buildings(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    rows = BuildingService.list_buildings(
        db=db, property_id=PROPERTY_ID, active_only=active_only
    )
    return [_to_dto(r) for r in rows]


@router.post(
    "",
    response_model=BuildingDTO,
    summary="Crear edificio",
)
def create_building(
    payload: BuildingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    data = payload.model_dump()
    property_id = data.pop("property_id", None) or PROPERTY_ID
    try:
        b = BuildingService.create_building(db=db, property_id=property_id, data=data)
    except BuildingServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    # Re-list to populate room_count consistently
    rows = BuildingService.list_buildings(db=db, property_id=property_id, active_only=False)
    match = next((r for r in rows if r["id"] == b.id), None)
    if not match:
        # Fallback (shouldn't happen)
        return BuildingDTO(
            id=b.id, property_id=b.property_id, name=b.name,
            description=b.description, floors=b.floors, sort_order=b.sort_order,
            is_active=bool(b.is_active), room_count=0,
            created_at=b.created_at, updated_at=b.updated_at,
        )
    return _to_dto(match)


@router.put(
    "/{building_id}",
    response_model=BuildingDTO,
    summary="Actualizar edificio",
)
def update_building(
    building_id: str,
    payload: BuildingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_WRITE_ROLES)),
):
    data = payload.model_dump(exclude_unset=True)
    try:
        b = BuildingService.update_building(db=db, building_id=building_id, data=data)
    except BuildingServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe edificio con id '{building_id}'",
        )
    rows = BuildingService.list_buildings(db=db, property_id=b.property_id, active_only=False)
    match = next((r for r in rows if r["id"] == b.id), None)
    return _to_dto(match) if match else BuildingDTO(
        id=b.id, property_id=b.property_id, name=b.name,
        description=b.description, floors=b.floors, sort_order=b.sort_order,
        is_active=bool(b.is_active), room_count=0,
        created_at=b.created_at, updated_at=b.updated_at,
    )
