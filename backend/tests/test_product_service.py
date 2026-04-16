"""
Tests for ProductService (v1.6.0 — Phase 3).

Covers: CRUD, validation, stock adjustments, low-stock queries, top-selling.
"""

import pytest
from datetime import date, timedelta

from services import ProductService, ProductError
from database import Producto, AjusteInventario


class TestProductCRUD:
    """CRUD + validation rules for the product catalog."""

    def test_create_product_basic(self, db_session, seed_property):
        p = ProductService.create_product(
            db_session,
            product_id="t-1",
            name="Test Agua",
            category="BEBIDA",
            price=5000.0,
            stock_current=10,
            stock_minimum=3,
            is_stocked=True,
        )
        assert p.id == "t-1"
        assert p.is_active is True
        assert p.stock_current == 10

    def test_create_product_invalid_category(self, db_session, seed_property):
        with pytest.raises(ProductError, match="Categoria invalida"):
            ProductService.create_product(
                db_session, product_id="t-2", name="X",
                category="DESCONOCIDA", price=1000.0,
            )

    def test_create_product_negative_price(self, db_session, seed_property):
        with pytest.raises(ProductError, match=">= 0"):
            ProductService.create_product(
                db_session, product_id="t-3", name="X",
                category="BEBIDA", price=-100,
            )

    def test_create_duplicate_id(self, db_session, seed_products):
        with pytest.raises(ProductError, match="Ya existe"):
            ProductService.create_product(
                db_session, product_id="test-agua-500",
                name="Otra agua", category="BEBIDA", price=4000,
            )

    def test_service_product_has_no_stock(self, db_session, seed_property):
        """is_stocked=False products have stock_current=None."""
        p = ProductService.create_product(
            db_session, product_id="t-svc", name="Parking extra",
            category="SERVICIO", price=20000, is_stocked=False,
        )
        assert p.stock_current is None
        assert p.stock_minimum is None

    def test_update_product_partial(self, db_session, seed_products):
        p = ProductService.update_product(
            db_session, product_id="test-agua-500", price=6000.0,
        )
        assert p.price == 6000.0
        assert p.name == "Agua 500ml"  # unchanged

    def test_update_product_stock_current_not_allowed_direct(self, db_session, seed_products):
        """Stock should be changed via adjust_stock, but update_product silently ignores it."""
        before = seed_products["test-agua-500"].stock_current
        ProductService.update_product(
            db_session, product_id="test-agua-500", stock_current=9999,
        )
        db_session.refresh(seed_products["test-agua-500"])
        assert seed_products["test-agua-500"].stock_current == before

    def test_deactivate_product(self, db_session, seed_products):
        p = ProductService.deactivate_product(db_session, "test-agua-500")
        assert p.is_active is False

    def test_list_products_active_only(self, db_session, seed_products):
        products = ProductService.list_products(db_session, active_only=True)
        # The seed has one inactive product; it should not appear
        assert all(p.is_active for p in products)
        assert "test-inactivo" not in {p.id for p in products}

    def test_list_products_filter_by_category(self, db_session, seed_products):
        bebidas = ProductService.list_products(db_session, category="BEBIDA")
        assert len(bebidas) == 2
        assert all(p.category == "BEBIDA" for p in bebidas)


class TestStockAdjustments:
    """Stock adjustments create audit rows and update stock atomically."""

    def test_adjust_stock_compra(self, db_session, seed_products):
        result = ProductService.adjust_stock(
            db_session, product_id="test-agua-500",
            quantity_change=20, reason="COMPRA", user="admin",
        )
        assert result["new_stock"] == 70
        # Audit row created
        adjustments = db_session.query(AjusteInventario).filter(
            AjusteInventario.producto_id == "test-agua-500"
        ).all()
        assert len(adjustments) == 1
        assert adjustments[0].reason == "COMPRA"

    def test_adjust_stock_merma(self, db_session, seed_products):
        result = ProductService.adjust_stock(
            db_session, product_id="test-coca-500",
            quantity_change=-5, reason="MERMA", user="admin",
        )
        assert result["new_stock"] == 15

    def test_adjust_stock_would_go_negative_rejected(self, db_session, seed_products):
        with pytest.raises(ProductError, match="Stock insuficiente"):
            ProductService.adjust_stock(
                db_session, product_id="test-coca-500",
                quantity_change=-100, reason="MERMA", user="admin",
            )

    def test_adjust_stock_service_rejected(self, db_session, seed_products):
        with pytest.raises(ProductError, match="servicio"):
            ProductService.adjust_stock(
                db_session, product_id="test-lavanderia",
                quantity_change=5, reason="COMPRA", user="admin",
            )

    def test_adjust_stock_invalid_reason(self, db_session, seed_products):
        with pytest.raises(ProductError, match="Razon invalida"):
            ProductService.adjust_stock(
                db_session, product_id="test-agua-500",
                quantity_change=1, reason="OTRO", user="admin",
            )

    def test_adjust_stock_zero_rejected(self, db_session, seed_products):
        with pytest.raises(ProductError, match="no puede ser 0"):
            ProductService.adjust_stock(
                db_session, product_id="test-agua-500",
                quantity_change=0, reason="AJUSTE", user="admin",
            )

    def test_low_stock_alert_fires_at_threshold(self, db_session, seed_products, caplog):
        """Dropping stock to <= minimum should log an ERROR (routed to Discord)."""
        import logging
        caplog.set_level(logging.ERROR)
        # test-coca-500 starts at 20, min=5. Drop to 5 exactly.
        ProductService.adjust_stock(
            db_session, product_id="test-coca-500",
            quantity_change=-15, reason="MERMA", user="admin",
        )
        alerts = [r.message for r in caplog.records if "STOCK BAJO" in r.message]
        assert len(alerts) == 1
        assert "Coca-Cola" in alerts[0]


class TestLowStockQuery:
    """get_low_stock_products returns items at or below their minimum."""

    def test_returns_only_low_stock(self, db_session, seed_products):
        low = ProductService.get_low_stock_products(db_session)
        # test-papas has stock 3, min 5 — should be in results
        # test-agua-500 has stock 50, min 10 — should NOT be
        ids = {p.id for p in low}
        assert "test-papas" in ids
        assert "test-agua-500" not in ids

    def test_excludes_services(self, db_session, seed_products):
        low = ProductService.get_low_stock_products(db_session)
        assert "test-lavanderia" not in {p.id for p in low}

    def test_excludes_inactive(self, db_session, seed_products):
        low = ProductService.get_low_stock_products(db_session)
        assert "test-inactivo" not in {p.id for p in low}
