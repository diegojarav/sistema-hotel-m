"""
Migration 017: Multi-currency payments MVP (v1.10.0 — Phase 2d)
================================================================

Hotels can now accept payments in multiple currencies. Every hotel still has
ONE "base currency" (all totals, saldos, caja reports denominated in this
currency). Payments arrive in any of N "accepted currencies" and are converted
to the base at register time. The exchange rate is **snapshotted** on the
transaction, so historical reports stay correct even if rates change later.

Triple-border-zone use case (Ciudad del Este, Paraguay): the receptionist
takes payments in PYG, USD, and BRL daily. Each currency has its own
exchange rate to PYG; the caja desglose shows the original-currency split.

What this migration does
------------------------
1. Re-uses the EXISTING `properties.currency` column as the base currency
   (no new column needed — the column already defaults to 'PYG'). The
   model now treats it as the authoritative "base currency" for the
   property. No schema change here.

2. NEW table `accepted_currencies` — what currencies the hotel takes:
     - property_id (FK)
     - currency_code (ISO 4217: PYG, USD, BRL, etc.)
     - currency_name, currency_symbol, decimal_places (snapshot from catalog)
     - exchange_rate (FLOAT, rate to base — e.g. 7500 if 1 USD = 7,500 PYG)
     - rate_updated_at, is_active, sort_order, created_at
     - UNIQUE (property_id, currency_code)

3. NEW columns on `transaccion`:
     - currency_code (TEXT, NULL = legacy / base-currency transaction)
     - exchange_rate (FLOAT, NULL = legacy / 1)
     - amount_original (FLOAT, NULL = legacy / same as amount)
   The existing `amount` column is preserved and is ALWAYS in base currency
   (it always was — multi-currency now just makes the meaning explicit and
   adds the "what did the guest actually hand over?" snapshot).

4. Seed default currencies for any existing properties. For Los Monges
   (Ciudad del Este — triple-border zone), seeds PYG (base), USD, and BRL.
   For any other property, seeds only its base currency.

Idempotent — safe to re-run. Re-runs detect column/table existence and
skip the seeding step if rows already exist for that property.

Back-compat
-----------
- Existing transactions (currency_code IS NULL) are treated as base-currency
  transactions by all read paths. Saldo / caja totals already sum `amount`
  which is in base currency, so legacy data continues to work untouched.
- The `Property.currency` field continues to default to 'PYG' for any
  property created without one. New deployments outside Paraguay should
  set `currency='USD'`/`'ARS'`/etc. via SQL or the future setup wizard.
"""
from __future__ import annotations

import sqlite3
from typing import List, Tuple

MIGRATION_NAME = "017_multi_currency"
MIGRATION_DESCRIPTION = (
    "Add accepted_currencies table + currency fields on transaccion + "
    "seed default currencies per property (Phase 2d — Multi-currency MVP)"
)


# Default seed per property when its base currency is known.
# (property_id is filled in at runtime; only the per-currency rate matters.)
# Rates are EXAMPLES — admins can change them via the Settings page later.
SEED_BY_BASE = {
    "PYG": [
        # (code, name, symbol, decimals, rate, sort_order)
        ("PYG", "Guaraní paraguayo",        "₲",   0, 1.0,    0),
        ("USD", "Dólar estadounidense",     "US$", 2, 7500.0, 1),
        ("BRL", "Real brasileño",           "R$",  2, 1450.0, 2),
    ],
    "USD": [
        ("USD", "Dólar estadounidense",     "US$", 2, 1.0,    0),
    ],
    "ARS": [
        ("ARS", "Peso argentino",           "$",   2, 1.0,    0),
        ("USD", "Dólar estadounidense",     "US$", 2, 1000.0, 1),
    ],
    "MXN": [
        ("MXN", "Peso mexicano",            "$",   2, 1.0,    0),
        ("USD", "Dólar estadounidense",     "US$", 2, 18.0,   1),
    ],
    "EUR": [
        ("EUR", "Euro",                     "€",   2, 1.0,    0),
        ("USD", "Dólar estadounidense",     "US$", 2, 0.92,   1),
    ],
    "BRL": [
        ("BRL", "Real brasileño",           "R$",  2, 1.0,    0),
        ("USD", "Dólar estadounidense",     "US$", 2, 5.0,    1),
    ],
}


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _index_exists(cursor, index_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


def run(conn: sqlite3.Connection):
    """Apply migration 017. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. NEW table: accepted_currencies ---
    if not _table_exists(cursor, "accepted_currencies"):
        cursor.execute(
            """
            CREATE TABLE accepted_currencies (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id       TEXT NOT NULL,
                currency_code     TEXT NOT NULL,
                currency_name     TEXT NOT NULL,
                currency_symbol   TEXT NOT NULL,
                decimal_places    INTEGER NOT NULL DEFAULT 2,
                exchange_rate     REAL NOT NULL,
                rate_updated_at   DATETIME,
                is_active         BOOLEAN NOT NULL DEFAULT 1,
                sort_order        INTEGER NOT NULL DEFAULT 0,
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE RESTRICT,
                UNIQUE (property_id, currency_code)
            )
            """
        )

    # Indexes — fast lookups by property + filters by active flag
    if not _index_exists(cursor, "idx_accepted_curr_property"):
        cursor.execute(
            "CREATE INDEX idx_accepted_curr_property "
            "ON accepted_currencies (property_id, is_active)"
        )

    # --- 2. NEW columns on transaccion ---
    # SQLite's ALTER TABLE ADD COLUMN only supports literal defaults — all
    # three are NULL for legacy rows (back-compat), so no DEFAULT clause.
    if not _column_exists(cursor, "transaccion", "currency_code"):
        cursor.execute("ALTER TABLE transaccion ADD COLUMN currency_code TEXT")
    if not _column_exists(cursor, "transaccion", "exchange_rate"):
        cursor.execute("ALTER TABLE transaccion ADD COLUMN exchange_rate REAL")
    if not _column_exists(cursor, "transaccion", "amount_original"):
        cursor.execute("ALTER TABLE transaccion ADD COLUMN amount_original REAL")

    # Helpful index for currency-breakdown queries on caja sessions
    # (e.g. "what came in as USD this shift?").
    if not _index_exists(cursor, "idx_transaccion_currency"):
        cursor.execute(
            "CREATE INDEX idx_transaccion_currency ON transaccion (currency_code)"
        )

    # --- 3. Seed default accepted currencies for every existing property ---
    cursor.execute("SELECT id, currency FROM properties")
    properties: List[Tuple[str, str]] = cursor.fetchall()

    for prop_id, base in properties:
        base = (base or "PYG").upper()

        # Skip if this property already has any accepted currencies (re-run safety)
        cursor.execute(
            "SELECT COUNT(*) FROM accepted_currencies WHERE property_id = ?",
            (prop_id,),
        )
        if cursor.fetchone()[0] > 0:
            continue

        seed = SEED_BY_BASE.get(base)
        if seed is None:
            # Unknown base currency — seed just the base with rate=1 so the
            # property is functional. Admin can add more via Settings.
            seed = [(base, base, base, 2, 1.0, 0)]

        for code, name, symbol, decimals, rate, sort_order in seed:
            cursor.execute(
                """
                INSERT INTO accepted_currencies (
                    property_id, currency_code, currency_name, currency_symbol,
                    decimal_places, exchange_rate, sort_order, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (prop_id, code, name, symbol, decimals, rate, sort_order),
            )

    # No data modification on the `transaccion` table — legacy rows keep
    # currency_code=NULL and read paths treat them as base currency.
