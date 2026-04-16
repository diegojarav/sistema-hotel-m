"""
Hotel API - Product Catalog & Inventory Endpoints (v1.6.0 — Phase 3)
=====================================================================

Manages the product catalog, stock adjustments, and inventory reports.

Permissions:
- Product CRUD, stock adjustments, inventory reports: admin / supervisor / gerencia
- List active products (for consumo forms): any authenticated user
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from api.deps import get_db, get_current_user, require_role
from database import User
from logging_config import get_logger
from services import ProductService, ProductError
from schemas import (
    ProductoCreate,
    ProductoUpdate,
    ProductoDTO,
    AjusteStockRequest,
    AjusteInventarioDTO,
    ProductoStockBajoDTO,
    ProductoMasVendidoDTO,
)

logger = get_logger(__name__)
router = APIRouter()


def _to_dto(p) -> dict:
    return {
        "id": p.id,
        "property_id": p.property_id,
        "name": p.name,
        "category": p.category,
        "price": float(p.price or 0.0),
        "stock_current": p.stock_current,
        "stock_minimum": p.stock_minimum,
        "is_stocked": bool(p.is_stocked),
        "is_active": bool(p.is_active),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


# ==========================================
# LIST / READ (any authenticated user)
# ==========================================

@router.get(
    "/",
    response_model=List[ProductoDTO],
    summary="List products",
    description="List products filtered by category and active flag. "
                "Any authenticated user can list products (needed for consumo forms).",
)
def list_products(
    category: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    products = ProductService.list_products(
        db=db, category=category, active_only=active_only
    )
    return [_to_dto(p) for p in products]


@router.get(
    "/stock-bajo",
    response_model=List[ProductoStockBajoDTO],
    summary="List products with low stock",
    description="Products where stock_current <= stock_minimum. Admin-only.",
)
def list_low_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    products = ProductService.get_low_stock_products(db=db)
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "stock_current": p.stock_current or 0,
            "stock_minimum": p.stock_minimum or 0,
        }
        for p in products
    ]


@router.get(
    "/mas-vendidos",
    response_model=List[ProductoMasVendidoDTO],
    summary="Top-selling products",
    description="Top N products by units sold in a period. Admin-only.",
)
def list_top_selling(
    desde: Optional[date] = Query(default=None),
    hasta: Optional[date] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    return ProductService.get_top_selling(
        db=db, desde=desde, hasta=hasta, limit=limit
    )


@router.get(
    "/{product_id}",
    response_model=ProductoDTO,
    summary="Get product",
)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = ProductService.get_product(db=db, product_id=product_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Producto {product_id} no encontrado")
    return _to_dto(p)


@router.get(
    "/{product_id}/ajustes",
    response_model=List[AjusteInventarioDTO],
    summary="List stock adjustments for a product",
)
def list_product_adjustments(
    product_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    rows = ProductService.list_adjustments(db=db, product_id=product_id, limit=limit)
    return [
        {
            "id": r.id,
            "producto_id": r.producto_id,
            "quantity_change": r.quantity_change,
            "reason": r.reason,
            "notes": r.notes,
            "created_by": r.created_by,
            "created_at": r.created_at,
        }
        for r in rows
    ]


# ==========================================
# CREATE / UPDATE / DELETE (admin-only)
# ==========================================

@router.post(
    "/",
    response_model=ProductoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
)
def create_product(
    data: ProductoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    try:
        p = ProductService.create_product(
            db=db,
            product_id=data.id,
            name=data.name,
            category=data.category,
            price=data.price,
            stock_current=data.stock_current,
            stock_minimum=data.stock_minimum,
            is_stocked=data.is_stocked,
        )
    except ProductError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_dto(p)


@router.patch(
    "/{product_id}",
    response_model=ProductoDTO,
    summary="Update product (partial)",
)
def update_product(
    product_id: str,
    data: ProductoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    fields = data.model_dump(exclude_unset=True)
    try:
        p = ProductService.update_product(db=db, product_id=product_id, **fields)
    except ProductError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_dto(p)


@router.delete(
    "/{product_id}",
    summary="Deactivate product (soft delete)",
)
def deactivate_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    try:
        p = ProductService.deactivate_product(db=db, product_id=product_id)
    except ProductError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"Producto {product_id} desactivado", "id": p.id}


# ==========================================
# STOCK ADJUSTMENTS (admin-only)
# ==========================================

@router.post(
    "/{product_id}/ajuste-stock",
    summary="Apply a stock adjustment",
    description="Register a purchase (+), loss (-), or correction. Audited in ajuste_inventario.",
)
def adjust_stock(
    product_id: str,
    data: AjusteStockRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor", "gerencia")),
):
    try:
        result = ProductService.adjust_stock(
            db=db,
            product_id=product_id,
            quantity_change=data.quantity_change,
            reason=data.reason,
            notes=data.notes,
            user=current_user.username,
        )
    except ProductError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "message": "Ajuste aplicado",
        "product": _to_dto(result["product"]),
        "new_stock": result["new_stock"],
        "ajuste_id": result["ajuste"].id,
    }
