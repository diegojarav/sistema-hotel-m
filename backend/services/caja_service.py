"""
Caja (Cash Register) Service
============================
Manages cash register sessions: open, close, track cash flow.

Business rules:
- Only one ABIERTA session per user at a time
- Cash payments REQUIRE an open session (enforced in TransaccionService)
- Close computes expected = opening + sum(efectivo in session)
- Difference = declared - expected (negative = missing, positive = extra)
- Sessions are immutable after closing
"""

from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from database import CajaSesion, Transaccion, User
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class CajaSessionError(Exception):
    """Raised for caja session business rule violations."""
    pass


class CajaService:
    """Cash register session management."""

    @staticmethod
    @with_db
    def abrir_sesion(db: Session, user_id: int, opening_balance: float, notes: str = "") -> CajaSesion:
        """
        Open a new cash session for a user.

        Raises:
            CajaSessionError: if user already has an open session
        """
        # Check for existing open session
        existing = db.query(CajaSesion).filter(
            CajaSesion.user_id == user_id,
            CajaSesion.status == "ABIERTA"
        ).first()

        if existing:
            raise CajaSessionError(
                f"El usuario ya tiene una sesion de caja abierta (ID {existing.id}). "
                f"Cierrela antes de abrir una nueva."
            )

        if opening_balance < 0:
            raise CajaSessionError("El balance inicial no puede ser negativo")

        sesion = CajaSesion(
            user_id=user_id,
            opening_balance=opening_balance,
            status="ABIERTA",
            notes=notes or None,
        )
        db.add(sesion)
        db.commit()
        db.refresh(sesion)

        logger.info(f"Caja abierta: sesion #{sesion.id} usuario {user_id} balance {opening_balance:,.0f}")
        return sesion

    @staticmethod
    @with_db
    def cerrar_sesion(db: Session, session_id: int, closing_balance_declared: float, notes: str = "") -> CajaSesion:
        """
        Close a cash session. Computes expected balance vs declared.

        expected = opening + sum(EFECTIVO non-voided in session)
        difference = declared - expected
        """
        sesion = db.query(CajaSesion).filter(CajaSesion.id == session_id).first()
        if not sesion:
            raise CajaSessionError(f"Sesion {session_id} no encontrada")

        if sesion.status == "CERRADA":
            raise CajaSessionError(f"La sesion {session_id} ya esta cerrada")

        # Sum EFECTIVO transactions in this session (non-voided)
        efectivo_total = sum(
            t.amount for t in db.query(Transaccion).filter(
                Transaccion.caja_sesion_id == session_id,
                Transaccion.payment_method == "EFECTIVO",
                Transaccion.voided == False
            ).all()
        )

        expected = (sesion.opening_balance or 0.0) + efectivo_total
        difference = closing_balance_declared - expected

        sesion.closed_at = datetime.now()
        sesion.closing_balance_declared = closing_balance_declared
        sesion.closing_balance_expected = expected
        sesion.difference = difference
        sesion.status = "CERRADA"
        if notes:
            sesion.notes = (sesion.notes or "") + f"\n[Cierre] {notes}"

        db.commit()
        db.refresh(sesion)

        logger.info(
            f"Caja cerrada: sesion #{session_id} "
            f"esperado={expected:,.0f} declarado={closing_balance_declared:,.0f} "
            f"diferencia={difference:+,.0f}"
        )

        if abs(difference) > 1:
            logger.warning(
                f"Caja #{session_id} cerrada con diferencia de {difference:+,.0f} Gs"
            )

        return sesion

    @staticmethod
    @with_db
    def get_current_session(db: Session, user_id: int) -> Optional[CajaSesion]:
        """Return the open session for a user, or None."""
        return db.query(CajaSesion).filter(
            CajaSesion.user_id == user_id,
            CajaSesion.status == "ABIERTA"
        ).first()

    @staticmethod
    @with_db
    def get_session_by_id(db: Session, session_id: int) -> Optional[CajaSesion]:
        """Return a session by ID."""
        return db.query(CajaSesion).filter(CajaSesion.id == session_id).first()

    @staticmethod
    @with_db
    def list_sessions(db: Session, user_id: Optional[int] = None, limit: int = 50) -> List[CajaSesion]:
        """List past sessions with optional user filter."""
        query = db.query(CajaSesion).order_by(CajaSesion.opened_at.desc())
        if user_id is not None:
            query = query.filter(CajaSesion.user_id == user_id)
        return query.limit(limit).all()

    @staticmethod
    @with_db
    def list_open_sessions(db: Session) -> List[CajaSesion]:
        """Return all currently ABIERTA sessions across all users, newest first."""
        return db.query(CajaSesion).filter(
            CajaSesion.status == "ABIERTA"
        ).order_by(CajaSesion.opened_at.desc()).all()

    @staticmethod
    @with_db
    def get_session_transactions(db: Session, session_id: int) -> List[Transaccion]:
        """Return all transactions (voided or not) for a session."""
        return db.query(Transaccion).filter(
            Transaccion.caja_sesion_id == session_id
        ).order_by(Transaccion.created_at.asc()).all()

    @staticmethod
    @with_db
    def get_session_summary(db: Session, session_id: int) -> Dict:
        """Return session info + ALL period transactions + running totals.

        Includes:
        - Session-linked EFECTIVO transactions (for cash reconciliation)
        - ALL non-voided transactions since session opened (for full period view)
        """
        sesion = db.query(CajaSesion).filter(CajaSesion.id == session_id).first()
        if not sesion:
            return None

        # Session-linked transactions (EFECTIVO through this caja)
        session_trans = db.query(Transaccion).filter(
            Transaccion.caja_sesion_id == session_id
        ).order_by(Transaccion.created_at.asc()).all()

        # ALL non-voided transactions since session opened (includes TRANSFERENCIA/POS)
        all_period_trans = db.query(Transaccion).filter(
            Transaccion.created_at >= sesion.opened_at,
            Transaccion.voided == False,
        ).order_by(Transaccion.created_at.asc()).all()

        # Cash total from session-linked only (for expected balance calculation)
        efectivo_total = sum(
            t.amount for t in session_trans
            if t.payment_method == "EFECTIVO" and not t.voided
        )
        # Transfer + POS totals from all period transactions
        transferencia_total = sum(
            t.amount for t in all_period_trans
            if t.payment_method == "TRANSFERENCIA"
        )
        pos_total = sum(
            t.amount for t in all_period_trans
            if t.payment_method == "POS"
        )

        # Get user name
        user = db.query(User).filter(User.id == sesion.user_id).first()
        user_name = user.username if user else "?"

        return {
            "id": sesion.id,
            "user_id": sesion.user_id,
            "user_name": user_name,
            "opened_at": sesion.opened_at,
            "closed_at": sesion.closed_at,
            "opening_balance": sesion.opening_balance,
            "closing_balance_declared": sesion.closing_balance_declared,
            "closing_balance_expected": sesion.closing_balance_expected,
            "difference": sesion.difference,
            "status": sesion.status,
            "notes": sesion.notes,
            "total_efectivo": efectivo_total,
            "total_transferencia": transferencia_total,
            "total_pos": pos_total,
            "transactions": all_period_trans,
        }
