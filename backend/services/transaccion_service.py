"""
Transaccion Service
===================
Register immutable payments against reservations.
Automatically recalculates reservation status based on sum(payments).

Business rules:
- Amount must be > 0
- EFECTIVO requires an open caja_sesion for the user
- TRANSFERENCIA/POS do NOT require a session
- Transactions are IMMUTABLE — only voided, never updated or deleted
- Void keeps the row but sets voided=True with reason/user/timestamp
- After any change (create or void), reservation status is recalculated
"""

from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy.orm import Session

from database import Transaccion, CajaSesion, Reservation, User
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)

VALID_METHODS = ("EFECTIVO", "TRANSFERENCIA", "POS")


class TransaccionError(Exception):
    """Raised for transaction business rule violations."""
    pass


class TransaccionService:
    """Payment transaction management."""

    @staticmethod
    @with_db
    def registrar_pago(
        db: Session,
        reserva_id: str,
        amount: float,
        payment_method: str,
        reference_number: Optional[str] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Transaccion:
        """
        Register a payment against a reservation.

        For EFECTIVO: user_id is required to find the open caja_sesion.
        Raises TransaccionError if no open session exists.
        """
        # Validate amount
        if amount is None or amount <= 0:
            raise TransaccionError("El monto debe ser mayor a 0")

        # Validate method
        payment_method = (payment_method or "").upper()
        if payment_method not in VALID_METHODS:
            raise TransaccionError(f"Metodo invalido. Use: {', '.join(VALID_METHODS)}")

        # Validate reservation exists
        reserva = db.query(Reservation).filter(Reservation.id == reserva_id).first()
        if not reserva:
            raise TransaccionError(f"Reserva {reserva_id} no encontrada")

        if reserva.status == "CANCELADA":
            raise TransaccionError(f"No se puede registrar pago en reserva cancelada {reserva_id}")

        # Cash requires open session
        caja_sesion_id = None
        if payment_method == "EFECTIVO":
            if user_id is None:
                raise TransaccionError(
                    "Debe abrir caja antes de registrar pagos en efectivo"
                )
            sesion = db.query(CajaSesion).filter(
                CajaSesion.user_id == user_id,
                CajaSesion.status == "ABIERTA"
            ).first()
            if not sesion:
                raise TransaccionError(
                    "Debe abrir caja antes de registrar pagos en efectivo"
                )
            caja_sesion_id = sesion.id

        # Transfer/POS should have a reference
        if payment_method in ("TRANSFERENCIA", "POS") and not reference_number:
            logger.warning(
                f"Transaccion {payment_method} sin numero de referencia (reserva {reserva_id})"
            )

        # Create transaction
        trans = Transaccion(
            reserva_id=reserva_id,
            caja_sesion_id=caja_sesion_id,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            description=description,
            created_by=created_by or "sistema",
            voided=False,
        )
        db.add(trans)
        db.commit()
        db.refresh(trans)

        logger.info(
            f"Pago registrado: {payment_method} {amount:,.0f} Gs "
            f"reserva={reserva_id} por={created_by}"
        )

        # Recalculate reservation status
        TransaccionService._recalcular_status_reserva(db, reserva_id)

        return trans

    @staticmethod
    @with_db
    def anular_transaccion(
        db: Session,
        transaccion_id: int,
        reason: str,
        user: str,
    ) -> Transaccion:
        """Void a transaction (mark voided=True with reason)."""
        if not reason or len(reason.strip()) < 3:
            raise TransaccionError("La razon de anulacion debe tener al menos 3 caracteres")

        trans = db.query(Transaccion).filter(Transaccion.id == transaccion_id).first()
        if not trans:
            raise TransaccionError(f"Transaccion {transaccion_id} no encontrada")

        if trans.voided:
            raise TransaccionError(f"La transaccion {transaccion_id} ya esta anulada")

        trans.voided = True
        trans.void_reason = reason.strip()
        trans.voided_at = datetime.now()
        trans.voided_by = user or "sistema"

        db.commit()
        db.refresh(trans)

        logger.info(
            f"Transaccion {transaccion_id} anulada por {user}: {reason}"
        )

        # Recalculate reservation status
        if trans.reserva_id:
            TransaccionService._recalcular_status_reserva(db, trans.reserva_id)

        return trans

    @staticmethod
    @with_db
    def get_by_reserva(db: Session, reserva_id: str, include_voided: bool = False) -> List[Transaccion]:
        """List all transactions for a reservation."""
        query = db.query(Transaccion).filter(Transaccion.reserva_id == reserva_id)
        if not include_voided:
            query = query.filter(Transaccion.voided == False)
        return query.order_by(Transaccion.created_at.asc()).all()

    @staticmethod
    @with_db
    def get_saldo(db: Session, reserva_id: str) -> Dict:
        """Return {total, room_total, consumo_total, paid, pending, transacciones}
        for a reservation.

        Starting in v1.6.0 (Phase 3), `total` includes both the room price
        and the sum of active consumos. Kept the original fields plus
        breakdown fields so UI can show "Habitación + Consumos = Total".
        """
        reserva = db.query(Reservation).filter(Reservation.id == reserva_id).first()
        if not reserva:
            return None

        transactions = TransaccionService.get_by_reserva(db, reserva_id, include_voided=False)
        room_total = reserva.price or 0.0

        # Lazy import to avoid circular dependency (ConsumoService imports us
        # for _recalcular_status_reserva)
        try:
            from services.consumo_service import ConsumoService
            consumo_total = ConsumoService.get_consumo_total(db, reserva_id)
        except Exception:
            consumo_total = 0.0

        total = room_total + consumo_total
        paid = sum(t.amount for t in transactions)
        pending = max(total - paid, 0.0)

        return {
            "reserva_id": reserva_id,
            "total": total,
            "room_total": room_total,
            "consumo_total": consumo_total,
            "paid": paid,
            "pending": pending,
            "transacciones": transactions,
        }

    @staticmethod
    @with_db
    def list_transactions(
        db: Session,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        payment_method: Optional[str] = None,
        include_voided: bool = False,
        limit: int = 500,
    ) -> List[Transaccion]:
        """List transactions with filters."""
        query = db.query(Transaccion)

        if date_from:
            query = query.filter(Transaccion.created_at >= date_from)
        if date_to:
            query = query.filter(Transaccion.created_at <= date_to)
        if payment_method:
            query = query.filter(Transaccion.payment_method == payment_method.upper())
        if not include_voided:
            query = query.filter(Transaccion.voided == False)

        return query.order_by(Transaccion.created_at.desc()).limit(limit).all()

    @staticmethod
    def _recalcular_status_reserva(db: Session, reserva_id: str):
        """
        Recalculate a reservation's status based on active payments.

        Rules:
        - Don't change terminal states (CANCELADA, COMPLETADA)
        - paid == 0 → RESERVADA
        - 0 < paid < total → SEÑADA
        - paid >= total → CONFIRMADA
        """
        reserva = db.query(Reservation).filter(Reservation.id == reserva_id).first()
        if not reserva:
            return

        # Normalize current status (handle legacy values)
        current = (reserva.status or "").strip()
        if current in ("CANCELADA", "Cancelada", "COMPLETADA", "Completada"):
            return  # Terminal states — don't auto-change

        # Sum active payments
        paid = sum(
            t.amount for t in db.query(Transaccion).filter(
                Transaccion.reserva_id == reserva_id,
                Transaccion.voided == False
            ).all()
        )

        # Total = room price + active consumos (v1.6.0 — Phase 3)
        room_total = reserva.price or 0.0
        try:
            from services.consumo_service import ConsumoService
            consumo_total = ConsumoService.get_consumo_total(db, reserva_id)
        except Exception:
            consumo_total = 0.0
        total = room_total + consumo_total

        if paid >= total and total > 0:
            new_status = "CONFIRMADA"
        elif paid > 0:
            new_status = "SEÑADA"
        else:
            new_status = "RESERVADA"

        if current != new_status:
            logger.info(
                f"Reserva {reserva_id} status: {current} -> {new_status} "
                f"(pagado {paid:,.0f} / total {total:,.0f})"
            )
            reserva.status = new_status
            db.commit()
