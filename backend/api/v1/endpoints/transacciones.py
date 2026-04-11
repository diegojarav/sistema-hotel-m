"""
Hotel Munich — Transacciones Endpoints
========================================
Register and void payment transactions against reservations.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from api.deps import get_db, get_current_user
from services import TransaccionService, TransaccionError
from schemas import (
    TransaccionCreate,
    AnularTransaccionRequest,
)
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _trans_to_dto(t) -> dict:
    return {
        "id": t.id,
        "reserva_id": t.reserva_id,
        "caja_sesion_id": t.caja_sesion_id,
        "amount": t.amount,
        "payment_method": t.payment_method,
        "reference_number": t.reference_number,
        "description": t.description,
        "created_at": t.created_at,
        "created_by": t.created_by,
        "voided": t.voided,
        "void_reason": t.void_reason,
        "voided_at": t.voided_at,
        "voided_by": t.voided_by,
    }


@router.post("/", summary="Registrar pago")
def registrar_pago(
    data: TransaccionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Register a payment against a reservation.
    EFECTIVO requires an open caja session for the current user.
    """
    try:
        trans = TransaccionService.registrar_pago(
            db,
            reserva_id=data.reserva_id,
            amount=data.amount,
            payment_method=data.payment_method,
            reference_number=data.reference_number,
            description=data.description,
            created_by=current_user.username,
            user_id=current_user.id,
        )
        return _trans_to_dto(trans)
    except TransaccionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{transaccion_id}/anular", summary="Anular una transaccion")
def anular(
    transaccion_id: int,
    data: AnularTransaccionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Void a transaction. Both admin and recepcion can void, but reason is mandatory.
    The transaction is not deleted — marked voided with reason/user/timestamp.
    """
    user_role = (current_user.role or "").lower().strip()
    if user_role not in ("admin", "supervisor", "gerencia", "recepcion", "recepcionista"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para anular transacciones",
        )

    try:
        trans = TransaccionService.anular_transaccion(
            db,
            transaccion_id=transaccion_id,
            reason=data.reason,
            user=current_user.username,
        )
        return _trans_to_dto(trans)
    except TransaccionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", summary="Listar transacciones")
def list_transactions(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    payment_method: Optional[str] = Query(default=None),
    include_voided: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List transactions with optional filters."""
    trans = TransaccionService.list_transactions(
        db,
        date_from=date_from,
        date_to=date_to,
        payment_method=payment_method,
        include_voided=include_voided,
        limit=limit,
    )
    return [_trans_to_dto(t) for t in trans]


@router.get("/reserva/{reserva_id}", summary="Transacciones + saldo de una reserva")
def get_by_reserva(
    reserva_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all active transactions and saldo for a reservation."""
    saldo = TransaccionService.get_saldo(db, reserva_id)
    if not saldo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")

    saldo["transacciones"] = [_trans_to_dto(t) for t in saldo["transacciones"]]
    return saldo
