"""
Tests for ConsumoService (v1.6.0 — Phase 3).

Covers: registration, stock decrement/restore, void, status recalc, snapshots,
balance integration.
"""

import pytest
from datetime import date, timedelta

from services import ConsumoService, ConsumoError, ProductService, TransaccionService
from database import Consumo, Producto


class TestConsumoRegistration:
    """Basic rules for registering a consumo."""

    def test_register_consumo_basic(self, db_session, seed_full, make_reservation, seed_products):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=2, created_by="recep",
        )
        assert c.quantity == 2
        assert c.unit_price == 5000.0
        assert c.total == 10000.0
        assert c.producto_name == "Agua 500ml"  # snapshot
        # Stock decremented
        p = db_session.query(Producto).filter(Producto.id == "test-agua-500").first()
        assert p.stock_current == 48  # 50 - 2

    def test_register_consumo_service_no_stock_check(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-lavanderia",
            quantity=1, created_by="recep",
        )
        assert c.total == 80000.0

    def test_register_consumo_insufficient_stock(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        with pytest.raises(ConsumoError, match="Stock insuficiente"):
            ConsumoService.registrar_consumo(
                db_session, reserva_id=res.id, producto_id="test-papas",
                quantity=100, created_by="recep",
            )

    def test_register_consumo_on_cancelled_reservation_rejected(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="CANCELADA")
        with pytest.raises(ConsumoError, match="estado"):
            ConsumoService.registrar_consumo(
                db_session, reserva_id=res.id, producto_id="test-agua-500",
                quantity=1, created_by="recep",
            )

    def test_register_consumo_on_completed_reservation_rejected(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="COMPLETADA")
        with pytest.raises(ConsumoError, match="estado"):
            ConsumoService.registrar_consumo(
                db_session, reserva_id=res.id, producto_id="test-agua-500",
                quantity=1, created_by="recep",
            )

    def test_register_consumo_inactive_product_rejected(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        with pytest.raises(ConsumoError, match="desactivado"):
            ConsumoService.registrar_consumo(
                db_session, reserva_id=res.id, producto_id="test-inactivo",
                quantity=1, created_by="recep",
            )

    def test_register_consumo_zero_quantity_rejected(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        with pytest.raises(ConsumoError, match="> 0"):
            ConsumoService.registrar_consumo(
                db_session, reserva_id=res.id, producto_id="test-agua-500",
                quantity=0, created_by="recep",
            )

    def test_price_snapshot_preserved_after_product_price_change(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        """Unit price captured at registration time must not change later."""
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=1, created_by="recep",
        )
        # Now bump the product price
        ProductService.update_product(db_session, product_id="test-agua-500", price=9999.0)
        db_session.refresh(c)
        assert c.unit_price == 5000.0  # unchanged


class TestConsumoVoid:
    """Voiding restores stock and recalculates reservation status."""

    def test_void_restores_stock(self, db_session, seed_full, make_reservation, seed_products):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=5, created_by="recep",
        )
        p = db_session.query(Producto).filter(Producto.id == "test-agua-500").first()
        assert p.stock_current == 45

        ConsumoService.anular_consumo(
            db_session, consumo_id=c.id, reason="Error en el cargo", user="admin",
        )
        db_session.refresh(p)
        assert p.stock_current == 50  # fully restored

    def test_void_requires_reason(self, db_session, seed_full, make_reservation, seed_products):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=1, created_by="recep",
        )
        with pytest.raises(ConsumoError, match="razon"):
            ConsumoService.anular_consumo(
                db_session, consumo_id=c.id, reason="", user="admin",
            )

    def test_cannot_void_twice(self, db_session, seed_full, make_reservation, seed_products):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=1, created_by="recep",
        )
        ConsumoService.anular_consumo(
            db_session, consumo_id=c.id, reason="primero", user="admin",
        )
        with pytest.raises(ConsumoError, match="ya esta anulado"):
            ConsumoService.anular_consumo(
                db_session, consumo_id=c.id, reason="segundo", user="admin",
            )


class TestBalanceIntegration:
    """Consumos add to the reservation total via TransaccionService.get_saldo()."""

    def test_consumo_adds_to_pending_balance(
        self, db_session, seed_full, make_reservation, seed_products, open_caja_session
    ):
        res = make_reservation(price=100000.0, status="CONFIRMADA")
        # Guest has paid the full room total
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
            created_by="admin",
        )
        saldo_before = TransaccionService.get_saldo(db_session, res.id)
        assert saldo_before["total"] == 100000.0
        assert saldo_before["pending"] == 0.0

        # Now add a consumo
        ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=2, created_by="recep",
        )
        saldo_after = TransaccionService.get_saldo(db_session, res.id)
        assert saldo_after["total"] == 110000.0
        assert saldo_after["consumo_total"] == 10000.0
        assert saldo_after["pending"] == 10000.0

    def test_consumo_downgrades_confirmada_to_senada(
        self, db_session, seed_full, make_reservation, seed_products, open_caja_session
    ):
        """If a consumo creates a pending balance, CONFIRMADA → SEÑADA."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
            created_by="admin",
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"

        ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=1, created_by="recep",
        )
        db_session.refresh(res)
        assert res.status == "SEÑADA"

    def test_void_consumo_recalculates_status(
        self, db_session, seed_full, make_reservation, seed_products, open_caja_session
    ):
        """Voiding a consumo that downgraded the status should re-upgrade."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
            created_by="admin",
        )
        c = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=1, created_by="recep",
        )
        db_session.refresh(res)
        assert res.status == "SEÑADA"

        ConsumoService.anular_consumo(
            db_session, consumo_id=c.id, reason="error", user="admin",
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"


class TestConsumoQueries:
    """Read queries."""

    def test_list_by_reserva_excludes_voided(
        self, db_session, seed_full, make_reservation, seed_products
    ):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        c1 = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=1, created_by="recep",
        )
        c2 = ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-coca-500",
            quantity=1, created_by="recep",
        )
        ConsumoService.anular_consumo(
            db_session, consumo_id=c1.id, reason="duplicado", user="admin",
        )

        active = ConsumoService.list_by_reserva(db_session, res.id)
        assert len(active) == 1
        assert active[0].id == c2.id

        all_incl = ConsumoService.list_by_reserva(db_session, res.id, include_voided=True)
        assert len(all_incl) == 2

    def test_get_consumo_total(self, db_session, seed_full, make_reservation, seed_products):
        res = make_reservation(price=200000.0, status="CONFIRMADA")
        ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-agua-500",
            quantity=3, created_by="recep",
        )  # 3 × 5000 = 15000
        ConsumoService.registrar_consumo(
            db_session, reserva_id=res.id, producto_id="test-coca-500",
            quantity=2, created_by="recep",
        )  # 2 × 12000 = 24000
        total = ConsumoService.get_consumo_total(db_session, res.id)
        assert total == 39000.0
