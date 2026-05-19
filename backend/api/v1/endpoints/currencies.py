"""
Hotel Munich — Currencies Endpoints (v1.10.0 — Phase 2d, Multi-currency MVP)
=============================================================================

Manages a property's accepted currencies + the read-only catalogue.

Roles
-----
- Read endpoints (catalog, accepted list, base): any authenticated operator
  (admin/supervisor/gerencia/recepcion/recepcionista).
- Write endpoints (add/update rate/remove): admin only.

The catalogue is hard-coded in `services/currency_service.py::CURRENCY_CATALOG`.
Hotels can't add new currencies — they pick from the 20 we know.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.config import DEFAULT_PROPERTY_ID
from api.deps import get_current_user, get_db, require_role
from database import User
from logging_config import get_logger
from schemas import (
    AcceptedCurrencyCreate,
    AcceptedCurrencyDTO,
    AcceptedCurrencyRateUpdate,
    CurrencyCatalogEntry,
)
from services import CurrencyError, CurrencyService

logger = get_logger(__name__)
router = APIRouter()


_READ_ROLES = ("admin", "supervisor", "gerencia", "recepcion", "recepcionista")
_ADMIN_ONLY = ("admin",)


def _row_to_dto(row) -> dict:
    return {
        "id": row.id,
        "property_id": row.property_id,
        "currency_code": row.currency_code,
        "currency_name": row.currency_name,
        "currency_symbol": row.currency_symbol,
        "decimal_places": row.decimal_places,
        "exchange_rate": float(row.exchange_rate),
        "rate_updated_at": row.rate_updated_at,
        "is_active": bool(row.is_active),
        "sort_order": row.sort_order,
    }


# ----------------------------------------------------------------------
# Read endpoints
# ----------------------------------------------------------------------
@router.get(
    "/catalog",
    response_model=List[CurrencyCatalogEntry],
    summary="Catálogo de monedas soportadas",
    description=(
        "Read-only catalogue of every currency the system knows about. "
        "Hotels pick from this list to configure which they accept."
    ),
)
def get_catalog(
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    return CurrencyService.CATALOG


@router.get(
    "/base",
    summary="Moneda base de la propiedad",
    description="Devuelve el código ISO 4217 de la moneda base.",
)
def get_base(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    return {"base_currency": CurrencyService.get_base_currency(db=db)}


@router.get(
    "",
    summary="Monedas aceptadas por la propiedad",
    description=(
        "Lista de monedas configuradas (con tipo de cambio actual). "
        "`active_only=true` por defecto."
    ),
)
def list_accepted(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_READ_ROLES)),
):
    rows = CurrencyService.get_accepted_currencies(
        db=db, property_id=DEFAULT_PROPERTY_ID, active_only=active_only,
    )
    return [_row_to_dto(r) for r in rows]


# ----------------------------------------------------------------------
# Write endpoints (admin only)
# ----------------------------------------------------------------------
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Agregar moneda aceptada",
    description=(
        "Agrega una moneda del catálogo a la lista de aceptadas. Si ya existe "
        "(misma `currency_code` para esta propiedad), actualiza su tipo de cambio "
        "y la reactiva. **Admin only.**"
    ),
)
def add_accepted(
    data: AcceptedCurrencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ADMIN_ONLY)),
):
    try:
        row = CurrencyService.add_accepted_currency(
            db=db,
            property_id=DEFAULT_PROPERTY_ID,
            currency_code=data.currency_code,
            exchange_rate=data.exchange_rate,
            sort_order=data.sort_order,
        )
        return _row_to_dto(row)
    except CurrencyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put(
    "/{currency_code}/rate",
    summary="Actualizar tipo de cambio",
    description="Cambia el tipo de cambio actual. **Admin only.**",
)
def update_rate(
    currency_code: str,
    data: AcceptedCurrencyRateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ADMIN_ONLY)),
):
    try:
        row = CurrencyService.update_exchange_rate(
            db=db,
            property_id=DEFAULT_PROPERTY_ID,
            currency_code=currency_code,
            new_rate=data.exchange_rate,
        )
        return _row_to_dto(row)
    except CurrencyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{currency_code}",
    summary="Quitar moneda aceptada (soft-deactivate)",
    description=(
        "Desactiva una moneda (no la borra — preserva historia). "
        "No permite quitar la moneda base. **Admin only.**"
    ),
)
def remove_accepted(
    currency_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*_ADMIN_ONLY)),
):
    try:
        CurrencyService.remove_accepted_currency(
            db=db,
            property_id=DEFAULT_PROPERTY_ID,
            currency_code=currency_code,
        )
        return {"removed": True, "currency_code": currency_code.upper()}
    except CurrencyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
