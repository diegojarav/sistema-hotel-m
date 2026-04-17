"""
Migration 003: Room Charges & Product Inventory (v1.6.0 — Phase 3)
====================================================================

1. Creates `producto` — product/service catalog
2. Creates `consumo` — reservation charge line items
3. Creates `ajuste_inventario` — stock adjustment audit trail
4. Seeds 8 common hotel products so the hotel has something on day 1

Idempotent: safe to run multiple times via run_migrations.py. The seed
step skips if the producto table already has rows.
"""

import sqlite3
from datetime import datetime

MIGRATION_NAME = "inventario_v3"
MIGRATION_DESCRIPTION = "v1.6.0 — Room charges, consumos, inventory + seeded catalog"

PROPERTY_ID = "los-monges"

SEED_PRODUCTS = [
    # (id, name, category, price, stock_current, stock_minimum, is_stocked)
    (f"{PROPERTY_ID}-agua-500",        "Agua 500ml",       "BEBIDA",   5000.0,  48, 12, True),
    (f"{PROPERTY_ID}-coca-cola-500",   "Coca-Cola 500ml",  "BEBIDA",   12000.0, 24, 6,  True),
    (f"{PROPERTY_ID}-sprite-500",      "Sprite 500ml",     "BEBIDA",   12000.0, 24, 6,  True),
    (f"{PROPERTY_ID}-cerveza-pilsen",  "Cerveza Pilsen",   "BEBIDA",   15000.0, 36, 12, True),
    (f"{PROPERTY_ID}-papas-fritas",    "Papas fritas",     "SNACK",    8000.0,  20, 6,  True),
    (f"{PROPERTY_ID}-mani",            "Maní salado",      "SNACK",    5000.0,  20, 6,  True),
    (f"{PROPERTY_ID}-lavanderia",      "Lavandería",       "SERVICIO", 80000.0, None, None, False),
    (f"{PROPERTY_ID}-late-checkout",   "Late check-out",   "SERVICIO", 50000.0, None, None, False),
]


def _table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cursor.fetchone() is not None


def _create_producto(cursor):
    if _table_exists(cursor, "producto"):
        return 0
    cursor.execute("""
        CREATE TABLE producto (
            id TEXT PRIMARY KEY,
            property_id TEXT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0.0,
            stock_current INTEGER,
            stock_minimum INTEGER,
            is_stocked BOOLEAN NOT NULL DEFAULT 1,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        )
    """)
    cursor.execute("CREATE INDEX idx_producto_category ON producto(category)")
    cursor.execute("CREATE INDEX idx_producto_active ON producto(is_active)")
    cursor.execute("CREATE INDEX idx_producto_property ON producto(property_id)")
    return 1


def _create_consumo(cursor):
    if _table_exists(cursor, "consumo"):
        return 0
    cursor.execute("""
        CREATE TABLE consumo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reserva_id TEXT NOT NULL,
            producto_id TEXT NOT NULL,
            producto_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            description TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            voided BOOLEAN NOT NULL DEFAULT 0,
            void_reason TEXT,
            voided_at DATETIME,
            voided_by TEXT,
            FOREIGN KEY (reserva_id) REFERENCES reservations(id),
            FOREIGN KEY (producto_id) REFERENCES producto(id)
        )
    """)
    cursor.execute("CREATE INDEX idx_consumo_reserva ON consumo(reserva_id)")
    cursor.execute("CREATE INDEX idx_consumo_producto ON consumo(producto_id)")
    cursor.execute("CREATE INDEX idx_consumo_created_at ON consumo(created_at)")
    cursor.execute("CREATE INDEX idx_consumo_voided ON consumo(voided)")
    return 1


def _create_ajuste_inventario(cursor):
    if _table_exists(cursor, "ajuste_inventario"):
        return 0
    cursor.execute("""
        CREATE TABLE ajuste_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id TEXT NOT NULL,
            quantity_change INTEGER NOT NULL,
            reason TEXT NOT NULL,
            notes TEXT,
            created_by TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (producto_id) REFERENCES producto(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX idx_ajuste_producto ON ajuste_inventario(producto_id)"
    )
    cursor.execute(
        "CREATE INDEX idx_ajuste_created_at ON ajuste_inventario(created_at)"
    )
    return 1


def _seed_products(cursor):
    cursor.execute("SELECT COUNT(*) FROM producto")
    if cursor.fetchone()[0] > 0:
        return 0

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    for (pid, name, cat, price, stock, stock_min, is_stocked) in SEED_PRODUCTS:
        cursor.execute("""
            INSERT INTO producto (
                id, property_id, name, category, price,
                stock_current, stock_minimum, is_stocked, is_active,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (pid, PROPERTY_ID, name, cat, price,
              stock, stock_min, 1 if is_stocked else 0, now, now))
    return len(SEED_PRODUCTS)


def run(conn: sqlite3.Connection):
    """Apply migration 003. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()
    _create_producto(cursor)
    _create_consumo(cursor)
    _create_ajuste_inventario(cursor)
    _seed_products(cursor)
