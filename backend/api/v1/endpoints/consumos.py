"""
Hotel API - Consumo (charge-to-room) Endpoints (v1.6.0 — Phase 3)
==================================================================

Register product consumos against active reservations, void them, list them.

Permissions:
- Register consumo: admin / supervisor / gerencia / recepcion
- Void consumo: admin / supervisor / gerencia (recepcion cannot void)
- List consumos: any authenticated user
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from api.deps import get_db, get_current_user, require_role
from database import User
from logging_config import get_logger
from services import ConsumoService, ConsumoError
from schemas import ConsumoCreate, AnularConsumoRequest, ConsumoDTO

logger = get_logger(__name__)
router = APIRouter()


def _to_dto(c) -> dict:
    return {
        "id": c.id,
        "reserva_id": c.reserva_id,
        "producto_id": c.producto_id,
        "producto_name": c.producto_name,
        "quantity": c.quantity,
        "unit_price": float(c.unit_price or 0.0),
        "total": float(c.total or 0.0),
        "description": c.description,
        "created_at": c.created_at,
        "created_by": c.created_by,
        "voided": bool(c.voided),
        "void_reason": c.void_reason,
        "voided_at": c.voided_at,
        "voided_by": c.voided_by,
    }


@router.post(
    "/",
    response_model=ConsumoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register a consumo against a reservation",
)
def registrar_consumo(
    data: ConsumoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role("admin", "supervisor", "gerencia", "recepcion", "recepcionista")
    ),
):
    try:
        c = ConsumoService.registrar_consumo(
            db=db,
            reserva_id=data.reserva_id,
            producto_id=data.producto_id,
            quantity=data.quantity,
            description=data.description,
            created_by=current_user.username,
        )
    except ConsumoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_dto(c)


@router.post(
    "/{consumo_id}/anular",
    response_model=ConsumoDTO,
    summary="Void a consumo (admin-only)",
    description="Admin-only. Restores stock and recalculates reservation status.",
)
def anular_consumo(
    consumo_id: int,
    data: AnularConsumoRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    try:
        c = ConsumoService.anular_consumo(
            db=db,
            consumo_id=consumo_id,
            reason=data.reason,
            user=current_user.username,
        )
    except ConsumoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_dto(c)


@router.get(
    "/reserva/{reserva_id}",
    response_model=List[ConsumoDTO],
    summary="List consumos for a reservation",
)
def list_by_reserva(
    reserva_id: str,
    include_voided: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consumos = ConsumoService.list_by_reserva(
        db=db, reserva_id=reserva_id, include_voided=include_voided
    )
    return [_to_dto(c) for c in consumos]


@router.get(
    "/recientes",
    response_model=List[ConsumoDTO],
    summary="List recent consumos (admin-only)",
)
def list_recent(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    consumos = ConsumoService.list_recent(db=db, limit=limit)
    return [_to_dto(c) for c in consumos]
