"""
Consumo Service (v1.6.0 — Phase 3)
====================================
Records line-item charges (consumos) against reservations: drinks, snacks,
minibar items, services (laundry, late checkout). Integrates with Phase 1's
transaction system — consumos increase the reservation's pending balance.

Business rules:
- Consumo can only be registered for active reservations
  (RESERVADA | SEÑADA | CONFIRMADA; legacy Pendiente + Confirmada accepted)
- Unit price and product name are captured as snapshots at registration time
- Stocked products have their stock decremented on creation, restored on void
- After any change, reservation status is recalculated via TransaccionService
- Admins can void; the original row is preserved with voided=True + reason/user
"""

from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import Consumo, Producto, Reservation
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


# Active states a reservation can be in for a consumo to be registered
# (legacy + v1.4.0 lifecycle). Excludes terminal states.
ACTIVE_RESERVATION_STATES = (
    "RESERVADA", "SEÑADA", "CONFIRMADA",
    "Confirmada", "Pendiente",
)


class ConsumoError(Exception):
    """Raised on consumo business-rule violations."""
    pass


class ConsumoService:
    """Reservation-charge line items."""

    # ------------------------------------------------------------------
    # Register / void
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def registrar_consumo(
        db: Session,
        reserva_id: str,
        producto_id: str,
        quantity: int = 1,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Consumo:
        """Register a consumo. Decrements product stock if stocked. Raises
        ConsumoError on any validation failure."""
        if not quantity or int(quantity) <= 0:
            raise ConsumoError("quantity debe ser > 0")

        # Load reservation
        reserva = db.query(Reservation).filter(Reservation.id == reserva_id).first()
        if not reserva:
            raise ConsumoError(f"Reserva {reserva_id} no encontrada")
        if (reserva.status or "").strip() not in ACTIVE_RESERVATION_STATES:
            raise ConsumoError(
                f"No se puede registrar consumo en reserva con estado "
                f"'{reserva.status}' (debe estar activa)"
            )

        # Load product
        p = db.query(Producto).filter(Producto.id == producto_id).first()
        if not p:
            raise ConsumoError(f"Producto {producto_id} no encontrado")
        if not p.is_active:
            raise ConsumoError(f"Producto {producto_id} esta desactivado")

        # Stock check (for physical products)
        if p.is_stocked:
            current = p.stock_current or 0
            if current < int(quantity):
                raise ConsumoError(
                    f"Stock insuficiente: {p.name} tiene {current} en existencia, "
                    f"se solicitaron {quantity}"
                )
            p.stock_current = current - int(quantity)
            p.updated_at = datetime.now()

        # Create consumo with snapshot
        unit_price = float(p.price or 0.0)
        total = unit_price * int(quantity)
        consumo = Consumo(
            reserva_id=reserva_id,
            producto_id=producto_id,
            producto_name=p.name,
            quantity=int(quantity),
            unit_price=unit_price,
            total=total,
            description=description,
            created_by=created_by or "sistema",
            voided=False,
        )
        db.add(consumo)
        db.commit()
        db.refresh(consumo)

        logger.info(
            f"Consumo registrado: reserva={reserva_id} producto={p.name} "
            f"qty={quantity} total={total:,.0f} Gs por {created_by or 'sistema'}"
        )

        # Low-stock alert (leverages DiscordWebhookHandler on ERROR level)
        if (
            p.is_stocked
            and p.stock_minimum is not None
            and (p.stock_current or 0) <= p.stock_minimum
        ):
            logger.error(
                f"STOCK BAJO: {p.name} ({p.id}) tiene {p.stock_current} unidad(es) "
                f"despues del consumo en reserva {reserva_id}. "
                f"Minimo={p.stock_minimum}. Reponer pronto."
            )

        # Recalculate reservation status via existing TransaccionService helper
        # (reservation total now includes this consumo)
        from services.transaccion_service import TransaccionService
        TransaccionService._recalcular_status_reserva(db, reserva_id)

        return consumo

    @staticmethod
    @with_db
    def anular_consumo(
        db: Session,
        consumo_id: int,
        reason: str,
        user: str,
    ) -> Consumo:
        """Void a consumo. Restores product stock and recalculates reservation
        status. Requires a reason >= 3 chars (admin/supervisor-only in API)."""
        if not reason or len(reason.strip()) < 3:
            raise ConsumoError("La razon de anulacion debe tener al menos 3 caracteres")

        consumo = db.query(Consumo).filter(Consumo.id == consumo_id).first()
        if not consumo:
            raise ConsumoError(f"Consumo {consumo_id} no encontrado")
        if consumo.voided:
            raise ConsumoError(f"El consumo {consumo_id} ya esta anulado")

        # Restore stock if product is stocked
        p = db.query(Producto).filter(Producto.id == consumo.producto_id).first()
        if p and p.is_stocked:
            p.stock_current = (p.stock_current or 0) + int(consumo.quantity)
            p.updated_at = datetime.now()

        consumo.voided = True
        consumo.void_reason = reason.strip()
        consumo.voided_at = datetime.now()
        consumo.voided_by = user or "sistema"

        db.commit()
        db.refresh(consumo)

        logger.info(
            f"Consumo {consumo_id} anulado por {user}: {reason} "
            f"(stock restaurado para {consumo.producto_name})"
        )

        # Recalculate reservation status
        from services.transaccion_service import TransaccionService
        TransaccionService._recalcular_status_reserva(db, consumo.reserva_id)

        return consumo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def list_by_reserva(
        db: Session,
        reserva_id: str,
        include_voided: bool = False,
    ) -> List[Consumo]:
        q = db.query(Consumo).filter(Consumo.reserva_id == reserva_id)
        if not include_voided:
            q = q.filter(Consumo.voided == False)
        return q.order_by(Consumo.created_at.asc()).all()

    @staticmethod
    @with_db
    def get_consumo_total(db: Session, reserva_id: str) -> float:
        """Sum of all active (non-voided) consumos for a reservation.

        Used by TransaccionService.get_saldo() to compute the full reservation
        total (room price + consumos).
        """
        consumos = (
            db.query(Consumo)
            .filter(Consumo.reserva_id == reserva_id, Consumo.voided == False)
            .all()
        )
        return sum(float(c.total or 0.0) for c in consumos)

    @staticmethod
    @with_db
    def get_by_id(db: Session, consumo_id: int) -> Optional[Consumo]:
        return db.query(Consumo).filter(Consumo.id == consumo_id).first()

    @staticmethod
    @with_db
    def list_recent(
        db: Session,
        limit: int = 50,
    ) -> List[Consumo]:
        """Recent consumos across all reservations (for admin reporting)."""
        return (
            db.query(Consumo)
            .filter(Consumo.voided == False)
            .order_by(desc(Consumo.created_at))
            .limit(limit)
            .all()
        )
