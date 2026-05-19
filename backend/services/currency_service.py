"""
Currency Service (v1.10.0 — Phase 2d, Multi-currency MVP)
==========================================================

Manages multi-currency payments for any hotel in any Spanish-speaking
country (the demo target is Ciudad del Este, Paraguay — triple-border
zone with PYG/USD/BRL daily). Every hotel has ONE base currency
(stored as `Property.currency`), and N "accepted currencies" that
guests can hand over at the counter.

Conversion model
----------------
- Every accepted currency has an `exchange_rate` to the BASE currency.
  Rate=1 means 1 unit of this currency = 1 unit of base. Rate=7500 means
  1 unit of this currency = 7,500 units of base.
- The base currency is ALWAYS seeded with rate=1.0 for uniformity.
- Rates are SET MANUALLY by admins (no FX feeds yet — hotels in border
  zones typically post their own daily rate at the desk).

Snapshot-at-pay-time
--------------------
When `TransaccionService.registrar_pago` records a non-base-currency
payment, it copies `exchange_rate` onto the transaction row. Later
rate changes do NOT retroactively alter historical income reports.
Mirrors the pattern used for `consumo.unit_price` and
`checkins.billing_*` snapshots elsewhere in the codebase.

Formatting
----------
`format_amount` respects each currency's decimal_places + a sensible
separator convention (PYG: dots, no decimals; USD: 2 decimals dot-then-
comma; BRL: 2 decimals comma-then-dot). Goes through one helper so the
PC + mobile + PDF formatting all stay consistent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from api.core.config import DEFAULT_PROPERTY_ID
from database import AcceptedCurrency, Property
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# Read-only catalogue — every currency a hotel MIGHT want to accept.
# Hotels don't create currencies; they SELECT from this list.
# Extend here when adding a new country (or refactor to a DB table when
# the project actually serves a hotel that needs something not listed).
# ----------------------------------------------------------------------
CURRENCY_CATALOG: List[Dict] = [
    # ----- Latin America -----
    {"code": "PYG", "name": "Guaraní paraguayo",        "symbol": "₲",     "decimals": 0, "country": "Paraguay"},
    {"code": "ARS", "name": "Peso argentino",           "symbol": "$",     "decimals": 2, "country": "Argentina"},
    {"code": "UYU", "name": "Peso uruguayo",            "symbol": "$U",    "decimals": 2, "country": "Uruguay"},
    {"code": "BRL", "name": "Real brasileño",           "symbol": "R$",    "decimals": 2, "country": "Brasil"},
    {"code": "CLP", "name": "Peso chileno",             "symbol": "$",     "decimals": 0, "country": "Chile"},
    {"code": "COP", "name": "Peso colombiano",          "symbol": "$",     "decimals": 0, "country": "Colombia"},
    {"code": "MXN", "name": "Peso mexicano",            "symbol": "$",     "decimals": 2, "country": "México"},
    {"code": "PEN", "name": "Sol peruano",              "symbol": "S/",    "decimals": 2, "country": "Perú"},
    {"code": "BOB", "name": "Boliviano",                "symbol": "Bs",    "decimals": 2, "country": "Bolivia"},
    {"code": "VES", "name": "Bolívar venezolano",       "symbol": "Bs.S",  "decimals": 2, "country": "Venezuela"},
    {"code": "CRC", "name": "Colón costarricense",      "symbol": "₡",     "decimals": 2, "country": "Costa Rica"},
    {"code": "GTQ", "name": "Quetzal guatemalteco",     "symbol": "Q",     "decimals": 2, "country": "Guatemala"},
    {"code": "HNL", "name": "Lempira hondureño",        "symbol": "L",     "decimals": 2, "country": "Honduras"},
    {"code": "NIO", "name": "Córdoba nicaragüense",     "symbol": "C$",    "decimals": 2, "country": "Nicaragua"},
    {"code": "DOP", "name": "Peso dominicano",          "symbol": "RD$",   "decimals": 2, "country": "Rep. Dominicana"},
    {"code": "CUP", "name": "Peso cubano",              "symbol": "$",     "decimals": 2, "country": "Cuba"},
    {"code": "PAB", "name": "Balboa panameño",          "symbol": "B/.",   "decimals": 2, "country": "Panamá"},
    # ----- International common at any LATAM desk -----
    {"code": "USD", "name": "Dólar estadounidense",     "symbol": "US$",   "decimals": 2, "country": "Estados Unidos"},
    {"code": "EUR", "name": "Euro",                     "symbol": "€",     "decimals": 2, "country": "Zona Euro"},
    {"code": "GBP", "name": "Libra esterlina",          "symbol": "£",     "decimals": 2, "country": "Reino Unido"},
]

_CATALOG_BY_CODE: Dict[str, Dict] = {c["code"]: c for c in CURRENCY_CATALOG}


class CurrencyError(Exception):
    """Raised on currency configuration / conversion business-rule violations."""
    pass


def _fmt_amount_raw(amount: float, decimals: int) -> str:
    """Format `amount` with `decimals` decimal places, using dots as the
    thousands separator and a comma decimal mark (Spanish convention).

    PYG (0 decimals): 750_000 → "750.000"
    USD (2 decimals): 1234.5  → "1.234,50"
    BRL (2 decimals): 150     → "150,00"
    """
    if amount is None:
        return ""
    quantized = round(float(amount), decimals)
    if decimals <= 0:
        # Integer formatting: thousands as dots
        whole = int(quantized)
        return f"{whole:,}".replace(",", ".")
    # Two-step swap to avoid clobbering: , → temp → . → ,
    formatted = f"{quantized:,.{decimals}f}"
    # Python: "1,234.50" → spec: "1.234,50"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


class CurrencyService:
    """Multi-currency configuration + conversion + formatting helpers."""

    # Expose the catalogue at class level for trivial discovery.
    CATALOG = CURRENCY_CATALOG
    CATALOG_BY_CODE = _CATALOG_BY_CODE

    # ------------------------------------------------------------------
    # Base currency lookup
    # ------------------------------------------------------------------
    @staticmethod
    @with_db
    def get_base_currency(db: Session, property_id: str = DEFAULT_PROPERTY_ID) -> str:
        """Return the property's base currency code (default 'PYG')."""
        prop = db.query(Property).filter(Property.id == property_id).first()
        return (prop.currency if prop and prop.currency else "PYG").upper()

    @staticmethod
    @with_db
    def set_base_currency(
        db: Session,
        property_id: str,
        new_base: str,
    ) -> str:
        """Switch a property's base currency. Refuses if there are existing
        non-voided transactions in a DIFFERENT base (would change the meaning
        of historical amounts). On a virgin property this is fine."""
        from database import Transaccion
        new_base = (new_base or "").strip().upper()
        if new_base not in _CATALOG_BY_CODE:
            raise CurrencyError(f"Moneda '{new_base}' no está en el catálogo.")
        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            raise CurrencyError(f"Propiedad {property_id} no encontrada.")
        # Block if there's history — preserves historical report integrity
        existing_txns = db.query(Transaccion).filter(
            Transaccion.voided == False,  # noqa: E712
        ).count()
        if existing_txns > 0 and (prop.currency or "PYG").upper() != new_base:
            raise CurrencyError(
                f"No se puede cambiar la moneda base con {existing_txns} "
                f"transacción(es) activas. Cambiarla rompería los reportes "
                f"históricos. Anulá o exportá las transacciones primero."
            )
        prop.currency = new_base
        # Ensure the new base is seeded in accepted_currencies with rate=1
        CurrencyService._upsert_base_row(db, property_id, new_base)
        db.commit()
        return new_base

    @staticmethod
    def _upsert_base_row(db: Session, property_id: str, base_code: str) -> AcceptedCurrency:
        """Internal: ensure the base currency exists in accepted_currencies
        with rate=1.0. Idempotent."""
        existing = (
            db.query(AcceptedCurrency)
            .filter(
                AcceptedCurrency.property_id == property_id,
                AcceptedCurrency.currency_code == base_code,
            )
            .first()
        )
        if existing is not None:
            # Force rate back to 1.0 (it IS the base, by definition)
            if existing.exchange_rate != 1.0:
                existing.exchange_rate = 1.0
            if not existing.is_active:
                existing.is_active = True
            return existing
        meta = _CATALOG_BY_CODE.get(base_code)
        if meta is None:
            raise CurrencyError(f"Moneda '{base_code}' no está en el catálogo.")
        row = AcceptedCurrency(
            property_id=property_id,
            currency_code=base_code,
            currency_name=meta["name"],
            currency_symbol=meta["symbol"],
            decimal_places=meta["decimals"],
            exchange_rate=1.0,
            sort_order=0,
            is_active=True,
        )
        db.add(row)
        db.flush()
        return row

    # ------------------------------------------------------------------
    # Accepted-currency CRUD
    # ------------------------------------------------------------------
    @staticmethod
    @with_db
    def get_accepted_currencies(
        db: Session,
        property_id: str = DEFAULT_PROPERTY_ID,
        active_only: bool = True,
    ) -> List[AcceptedCurrency]:
        """List currencies the property accepts. Ordered by sort_order then code."""
        q = db.query(AcceptedCurrency).filter(AcceptedCurrency.property_id == property_id)
        if active_only:
            q = q.filter(AcceptedCurrency.is_active == True)  # noqa: E712
        return q.order_by(AcceptedCurrency.sort_order.asc(), AcceptedCurrency.currency_code.asc()).all()

    @staticmethod
    @with_db
    def get_accepted_currency(
        db: Session,
        property_id: str,
        currency_code: str,
    ) -> Optional[AcceptedCurrency]:
        return (
            db.query(AcceptedCurrency)
            .filter(
                AcceptedCurrency.property_id == property_id,
                AcceptedCurrency.currency_code == (currency_code or "").upper(),
            )
            .first()
        )

    @staticmethod
    @with_db
    def add_accepted_currency(
        db: Session,
        property_id: str,
        currency_code: str,
        exchange_rate: float,
        sort_order: int = 100,
    ) -> AcceptedCurrency:
        """Add a currency from the catalogue to a property's accepted list.
        Snapshots name/symbol/decimals from CATALOG at insert time.
        Idempotent: existing row → updates rate + reactivates."""
        code = (currency_code or "").strip().upper()
        meta = _CATALOG_BY_CODE.get(code)
        if meta is None:
            raise CurrencyError(
                f"Moneda '{code}' no está en el catálogo. Códigos válidos: "
                f"{', '.join(sorted(_CATALOG_BY_CODE.keys()))}"
            )
        if exchange_rate is None or exchange_rate <= 0:
            raise CurrencyError("El tipo de cambio debe ser mayor a 0.")
        base = CurrencyService.get_base_currency(db, property_id)
        if code == base and exchange_rate != 1.0:
            raise CurrencyError(
                f"La moneda base ({base}) siempre tiene tipo de cambio = 1."
            )

        existing = CurrencyService.get_accepted_currency(db, property_id, code)
        if existing is not None:
            existing.exchange_rate = float(exchange_rate)
            existing.rate_updated_at = datetime.now()
            existing.is_active = True
            db.commit()
            return existing

        row = AcceptedCurrency(
            property_id=property_id,
            currency_code=code,
            currency_name=meta["name"],
            currency_symbol=meta["symbol"],
            decimal_places=meta["decimals"],
            exchange_rate=float(exchange_rate),
            rate_updated_at=datetime.now(),
            sort_order=sort_order,
            is_active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            f"AcceptedCurrency added: {code} for {property_id} "
            f"(rate {exchange_rate} → base {base})"
        )
        return row

    @staticmethod
    @with_db
    def update_exchange_rate(
        db: Session,
        property_id: str,
        currency_code: str,
        new_rate: float,
    ) -> AcceptedCurrency:
        """Update the rate for an existing accepted currency. Refuses to change
        the base currency's rate (always 1)."""
        if new_rate is None or new_rate <= 0:
            raise CurrencyError("El tipo de cambio debe ser mayor a 0.")
        code = (currency_code or "").strip().upper()
        base = CurrencyService.get_base_currency(db, property_id)
        if code == base:
            raise CurrencyError(
                f"No se puede modificar el tipo de cambio de la moneda base ({base})."
            )
        row = CurrencyService.get_accepted_currency(db, property_id, code)
        if row is None:
            raise CurrencyError(
                f"La moneda {code} no está configurada para esta propiedad."
            )
        row.exchange_rate = float(new_rate)
        row.rate_updated_at = datetime.now()
        db.commit()
        db.refresh(row)
        logger.info(f"Exchange rate updated: {code} → {new_rate} for {property_id}")
        return row

    @staticmethod
    @with_db
    def remove_accepted_currency(
        db: Session,
        property_id: str,
        currency_code: str,
    ) -> bool:
        """Soft-deactivate an accepted currency. Refuses to remove the base."""
        code = (currency_code or "").strip().upper()
        base = CurrencyService.get_base_currency(db, property_id)
        if code == base:
            raise CurrencyError(
                f"No se puede eliminar la moneda base ({base})."
            )
        row = CurrencyService.get_accepted_currency(db, property_id, code)
        if row is None:
            raise CurrencyError(
                f"La moneda {code} no está configurada para esta propiedad."
            )
        row.is_active = False
        db.commit()
        logger.info(f"AcceptedCurrency soft-removed: {code} for {property_id}")
        return True

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    @staticmethod
    @with_db
    def convert_to_base(
        db: Session,
        amount_original: float,
        currency_code: str,
        property_id: str = DEFAULT_PROPERTY_ID,
    ) -> Dict:
        """Convert `amount_original` units of `currency_code` to the property's
        base currency. Returns a dict with all the snapshot fields a transaction
        needs: amount_base, exchange_rate, currency_code, amount_original.

        Raises CurrencyError if the currency is not configured / inactive.
        """
        if amount_original is None or amount_original <= 0:
            raise CurrencyError("El monto a convertir debe ser mayor a 0.")
        code = (currency_code or "").strip().upper()
        base = CurrencyService.get_base_currency(db, property_id)
        if code == base:
            return {
                "amount_base": float(amount_original),
                "exchange_rate": 1.0,
                "currency_code": base,
                "amount_original": float(amount_original),
            }
        row = CurrencyService.get_accepted_currency(db, property_id, code)
        if row is None or not row.is_active:
            raise CurrencyError(
                f"Moneda '{code}' no está configurada/activa para esta propiedad."
            )
        rate = float(row.exchange_rate)
        # Base currency amount = original × rate. Round to base's decimal places.
        base_meta = _CATALOG_BY_CODE.get(base, {"decimals": 0})
        base_decimals = base_meta.get("decimals", 0)
        amount_base = round(amount_original * rate, base_decimals)
        return {
            "amount_base": float(amount_base),
            "exchange_rate": rate,
            "currency_code": code,
            "amount_original": float(amount_original),
        }

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------
    @staticmethod
    def format_amount(
        amount: float,
        currency_code: str,
        decimals: Optional[int] = None,
        with_symbol: bool = True,
    ) -> str:
        """Format `amount` with the currency's correct decimal places + symbol.

        PYG  → "₲ 750.000"      (0 decimals, dot thousands)
        USD  → "US$ 100,00"     (2 decimals, comma decimal)
        BRL  → "R$ 150,00"      (2 decimals)
        Unknown code → "<code> <amount>" (graceful fallback)
        """
        code = (currency_code or "").strip().upper()
        meta = _CATALOG_BY_CODE.get(code)
        if meta is None:
            # Unknown currency — emit a safe label rather than crashing
            return f"{code} {amount:.2f}".strip()
        dec = decimals if decimals is not None else meta["decimals"]
        formatted = _fmt_amount_raw(amount, dec)
        if with_symbol:
            return f"{meta['symbol']} {formatted}"
        return formatted

    @staticmethod
    def get_catalog_entry(currency_code: str) -> Optional[Dict]:
        """Return the catalogue metadata for a code, or None if unknown."""
        return _CATALOG_BY_CODE.get((currency_code or "").strip().upper())
