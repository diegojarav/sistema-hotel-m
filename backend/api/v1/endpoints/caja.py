"""
Hotel Munich — Caja (Cash Register) Endpoints
==============================================
Open/close cash register sessions, view history, get current session.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from api.deps import get_db, get_current_user
from services import CajaService, CajaSessionError
from schemas import (
    CajaAbrirRequest,
    CajaCerrarRequest,
    CajaSesionDTO,
)
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _to_dto(sesion, db: Session) -> dict:
    """Convert CajaSesion ORM to dict (serializable)."""
    from database import User, Transaccion
    user = db.query(User).filter(User.id == sesion.user_id).first()
    efectivo_total = sum(
        t.amount for t in db.query(Transaccion).filter(
            Transaccion.caja_sesion_id == sesion.id,
            Transaccion.payment_method == "EFECTIVO",
            Transaccion.voided == False,
        ).all()
    )
    return {
        "id": sesion.id,
        "user_id": sesion.user_id,
        "user_name": user.username if user else "",
        "opened_at": sesion.opened_at,
        "closed_at": sesion.closed_at,
        "opening_balance": sesion.opening_balance or 0.0,
        "closing_balance_declared": sesion.closing_balance_declared,
        "closing_balance_expected": sesion.closing_balance_expected,
        "difference": sesion.difference,
        "status": sesion.status,
        "notes": sesion.notes,
        "total_efectivo": efectivo_total,
    }


@router.post("/abrir", summary="Abrir sesion de caja")
def abrir_sesion(
    data: CajaAbrirRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Open a new cash register session. Fails if user already has an open session."""
    try:
        sesion = CajaService.abrir_sesion(
            db,
            user_id=current_user.id,
            opening_balance=data.opening_balance,
            notes=data.notes,
        )
        return _to_dto(sesion, db)
    except CajaSessionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/cerrar", summary="Cerrar sesion de caja")
def cerrar_sesion(
    data: CajaCerrarRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Close an open cash register session. Computes expected vs declared balance."""
    # Check the session belongs to current user OR user is admin
    sesion = CajaService.get_session_by_id(db, data.session_id)
    if not sesion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesion no encontrada")

    user_role = (current_user.role or "").lower().strip()
    if sesion.user_id != current_user.id and user_role not in ("admin", "supervisor", "gerencia"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el usuario que abrio la caja o un admin puede cerrarla",
        )

    try:
        sesion = CajaService.cerrar_sesion(
            db,
            session_id=data.session_id,
            closing_balance_declared=data.closing_balance_declared,
            notes=data.notes,
        )
        return _to_dto(sesion, db)
    except CajaSessionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/actual", summary="Sesion actual del usuario logueado")
def get_current(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the open cash session for the logged-in user, or null if none."""
    sesion = CajaService.get_current_session(db, current_user.id)
    if not sesion:
        return None
    return _to_dto(sesion, db)


@router.get("/historial", summary="Historial de sesiones de caja")
def list_sessions(
    user_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List past cash register sessions. Admins can see all; others see only their own."""
    user_role = (current_user.role or "").lower().strip()
    if user_role not in ("admin", "supervisor", "gerencia"):
        # Non-admins only see their own sessions
        user_id = current_user.id

    sessions = CajaService.list_sessions(db, user_id=user_id, limit=limit)
    return [_to_dto(s, db) for s in sessions]


@router.get("/{session_id}", summary="Detalle de sesion con transacciones")
def get_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full session detail with all transactions."""
    summary = CajaService.get_session_summary(db, session_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesion no encontrada")

    # Permission check
    user_role = (current_user.role or "").lower().strip()
    if summary["user_id"] != current_user.id and user_role not in ("admin", "supervisor", "gerencia"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")

    # Serialize transactions
    summary["transactions"] = [
        {
            "id": t.id,
            "reserva_id": t.reserva_id,
            "amount": t.amount,
            "payment_method": t.payment_method,
            "reference_number": t.reference_number,
            "description": t.description,
            "created_at": t.created_at,
            "created_by": t.created_by,
            "voided": t.voided,
            "void_reason": t.void_reason,
        }
        for t in summary["transactions"]
    ]
    return summary
