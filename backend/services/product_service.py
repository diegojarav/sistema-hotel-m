"""
Product Service (v1.6.0 — Phase 3)
====================================
Manages the product/service catalog: drinks, snacks, minibar items, services
(laundry, late checkout, etc.). Tracks stock for physical items and triggers
Discord alerts when stock drops to or below the minimum threshold.

Business rules:
- Products can be soft-deleted via `is_active=False` (hides from selectors
  but preserves consumo history)
- `is_stocked=False` for services — no stock counter, no alerts
- Every stock change is logged in `ajuste_inventario` (COMPRA | MERMA | AJUSTE)
- Discord alert fires when post-adjustment stock <= stock_minimum
"""

from datetime import datetime, date
from typing import Optional, List, Dict

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import Producto, AjusteInventario, Consumo
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)

VALID_CATEGORIES = ("BEBIDA", "SNACK", "SERVICIO", "MINIBAR", "OTRO")
VALID_REASONS = ("COMPRA", "MERMA", "AJUSTE")


class ProductError(Exception):
    """Raised on product/stock business-rule violations."""
    pass


class ProductService:
    """Product catalog + stock adjustments."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def create_product(
        db: Session,
        product_id: str,
        name: str,
        category: str,
        price: float,
        stock_current: Optional[int] = None,
        stock_minimum: Optional[int] = None,
        is_stocked: bool = True,
        property_id: Optional[str] = "los-monges",
    ) -> Producto:
        """Create a new product. Raises ProductError on validation failure."""
        if not product_id or not product_id.strip():
            raise ProductError("product_id requerido")
        if not name or not name.strip():
            raise ProductError("name requerido")
        category = (category or "").upper()
        if category not in VALID_CATEGORIES:
            raise ProductError(f"Categoria invalida. Use: {', '.join(VALID_CATEGORIES)}")
        if price is None or price < 0:
            raise ProductError("price debe ser >= 0")

        existing = db.query(Producto).filter(Producto.id == product_id).first()
        if existing:
            raise ProductError(f"Ya existe un producto con id '{product_id}'")

        # Services don't track stock
        if not is_stocked:
            stock_current = None
            stock_minimum = None
        else:
            if stock_current is None:
                stock_current = 0
            if stock_minimum is None:
                stock_minimum = 0

        p = Producto(
            id=product_id.strip(),
            property_id=property_id,
            name=name.strip(),
            category=category,
            price=float(price),
            stock_current=stock_current,
            stock_minimum=stock_minimum,
            is_stocked=bool(is_stocked),
            is_active=True,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        logger.info(f"Producto creado: {p.id} ({p.name}) categoria={p.category}")
        return p

    @staticmethod
    @with_db
    def update_product(
        db: Session,
        product_id: str,
        **fields,
    ) -> Producto:
        """Partially update a product. Allowed fields: name, category, price,
        stock_minimum, is_stocked, is_active. Stock_current must be changed
        via adjust_stock() to keep an audit trail."""
        p = db.query(Producto).filter(Producto.id == product_id).first()
        if not p:
            raise ProductError(f"Producto {product_id} no encontrado")

        allowed = {"name", "category", "price", "stock_minimum", "is_stocked", "is_active"}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if value is None:
                continue
            if key == "category":
                value = (value or "").upper()
                if value not in VALID_CATEGORIES:
                    raise ProductError(f"Categoria invalida. Use: {', '.join(VALID_CATEGORIES)}")
            if key == "price" and float(value) < 0:
                raise ProductError("price debe ser >= 0")
            setattr(p, key, value)

        p.updated_at = datetime.now()
        db.commit()
        db.refresh(p)
        logger.info(f"Producto actualizado: {p.id}")
        return p

    @staticmethod
    @with_db
    def deactivate_product(db: Session, product_id: str) -> Producto:
        """Soft-delete a product by setting is_active=False."""
        p = db.query(Producto).filter(Producto.id == product_id).first()
        if not p:
            raise ProductError(f"Producto {product_id} no encontrado")
        p.is_active = False
        p.updated_at = datetime.now()
        db.commit()
        db.refresh(p)
        logger.info(f"Producto desactivado: {p.id}")
        return p

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def get_product(db: Session, product_id: str) -> Optional[Producto]:
        return db.query(Producto).filter(Producto.id == product_id).first()

    @staticmethod
    @with_db
    def list_products(
        db: Session,
        category: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Producto]:
        query = db.query(Producto)
        if active_only:
            query = query.filter(Producto.is_active == True)
        if category:
            query = query.filter(Producto.category == category.upper())
        return query.order_by(Producto.category, Producto.name).all()

    @staticmethod
    @with_db
    def get_low_stock_products(db: Session) -> List[Producto]:
        """Return active stocked products where stock_current <= stock_minimum."""
        return db.query(Producto).filter(
            Producto.is_active == True,
            Producto.is_stocked == True,
            Producto.stock_minimum.isnot(None),
            Producto.stock_current <= Producto.stock_minimum,
        ).order_by(Producto.name).all()

    @staticmethod
    @with_db
    def get_top_selling(
        db: Session,
        desde: Optional[date] = None,
        hasta: Optional[date] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """Return top-selling products by units sold in the period.

        Result: [{producto_id, producto_name, units_sold, revenue, consumo_count}, ...]
        Only counts non-voided consumos.
        """
        query = db.query(
            Consumo.producto_id,
            Consumo.producto_name,
            func.sum(Consumo.quantity).label("units_sold"),
            func.sum(Consumo.total).label("revenue"),
            func.count(Consumo.id).label("consumo_count"),
        ).filter(Consumo.voided == False)

        if desde:
            query = query.filter(Consumo.created_at >= datetime.combine(desde, datetime.min.time()))
        if hasta:
            query = query.filter(Consumo.created_at <= datetime.combine(hasta, datetime.max.time()))

        rows = (
            query.group_by(Consumo.producto_id, Consumo.producto_name)
            .order_by(desc("units_sold"))
            .limit(limit)
            .all()
        )

        return [
            {
                "producto_id": r.producto_id,
                "producto_name": r.producto_name,
                "units_sold": int(r.units_sold or 0),
                "revenue": float(r.revenue or 0.0),
                "consumo_count": int(r.consumo_count or 0),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Stock adjustments (audit-logged)
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def adjust_stock(
        db: Session,
        product_id: str,
        quantity_change: int,
        reason: str,
        notes: Optional[str] = None,
        user: Optional[str] = None,
    ) -> Dict:
        """Apply a stock adjustment and log it in ajuste_inventario.

        quantity_change is signed: +N for compras, -N for mermas/consumos,
        or anything for AJUSTE. Fires a Discord alert (ERROR log) if the
        new stock level drops to or below stock_minimum.
        """
        p = db.query(Producto).filter(Producto.id == product_id).first()
        if not p:
            raise ProductError(f"Producto {product_id} no encontrado")
        if not p.is_stocked:
            raise ProductError(f"Producto {product_id} es un servicio (sin stock)")
        reason = (reason or "").upper()
        if reason not in VALID_REASONS:
            raise ProductError(f"Razon invalida. Use: {', '.join(VALID_REASONS)}")
        if quantity_change == 0:
            raise ProductError("quantity_change no puede ser 0")

        new_stock = (p.stock_current or 0) + int(quantity_change)
        if new_stock < 0:
            raise ProductError(
                f"Stock insuficiente: {p.stock_current} en existencia, "
                f"ajuste de {quantity_change} daria {new_stock}"
            )

        p.stock_current = new_stock
        p.updated_at = datetime.now()

        ajuste = AjusteInventario(
            producto_id=product_id,
            quantity_change=int(quantity_change),
            reason=reason,
            notes=notes,
            created_by=user or "sistema",
        )
        db.add(ajuste)
        db.commit()
        db.refresh(p)
        db.refresh(ajuste)

        logger.info(
            f"Stock ajustado: {p.id} ({p.name}) {quantity_change:+d} -> "
            f"{new_stock} ({reason}) por {user or 'sistema'}"
        )

        # Low stock Discord alert (leverages DiscordWebhookHandler on ERROR level)
        if p.stock_minimum is not None and new_stock <= p.stock_minimum:
            logger.error(
                f"STOCK BAJO: {p.name} ({p.id}) tiene {new_stock} unidad(es), "
                f"minimo={p.stock_minimum}. Reponer pronto."
            )

        return {"product": p, "ajuste": ajuste, "new_stock": new_stock}

    @staticmethod
    @with_db
    def list_adjustments(
        db: Session,
        product_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AjusteInventario]:
        q = db.query(AjusteInventario)
        if product_id:
            q = q.filter(AjusteInventario.producto_id == product_id)
        return q.order_by(desc(AjusteInventario.created_at)).limit(limit).all()
