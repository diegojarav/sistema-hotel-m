"""
Migration: Room Charges & Product Inventory (v1.6.0 — Phase 3)
================================================================

Creates the 3 new tables for the POS layer and seeds a starter product catalog:

1. `producto` — product/service catalog
2. `consumo` — charges added to reservations (minibar, laundry, late checkout, etc.)
3. `ajuste_inventario` — audit trail of stock adjustments (purchases, losses, corrections)

Seeds 8 common hotel products so the hotel has something to work with on day 1.
All products are active and, for physical items, start with a reasonable stock_current
plus a sensible stock_minimum threshold that triggers Discord low-stock alerts.

Idempotent: safe to run multiple times. Checks table and row existence before
creating or seeding. Follows the pattern of `migrate_caja_transacciones.py` and
`migrate_ical_v2.py`.

Usage:
    python scripts/migrate_inventario_v3.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

DB_PATH = backend_path / "hotel.db"

PROPERTY_ID = "los-monges"  # Single-property deployment (see other migrations)


def table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cursor.fetchone() is not None


def create_producto_table(cursor):
    if table_exists(cursor, "producto"):
        print("  [=] Table 'producto' already exists, skipping")
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
    print("  [+] Created table 'producto' with indexes")
    return 1


def create_consumo_table(cursor):
    if table_exists(cursor, "consumo"):
        print("  [=] Table 'consumo' already exists, skipping")
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
    print("  [+] Created table 'consumo' with indexes")
    return 1


def create_ajuste_table(cursor):
    if table_exists(cursor, "ajuste_inventario"):
        print("  [=] Table 'ajuste_inventario' already exists, skipping")
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
    cursor.execute("CREATE INDEX idx_ajuste_producto ON ajuste_inventario(producto_id)")
    cursor.execute("CREATE INDEX idx_ajuste_created_at ON ajuste_inventario(created_at)")
    print("  [+] Created table 'ajuste_inventario' with indexes")
    return 1


# ---- Starter product catalog ----
# (id, name, category, price, stock_current, stock_minimum, is_stocked)
SEED_PRODUCTS = [
    (f"{PROPERTY_ID}-agua-500",        "Agua 500ml",       "BEBIDA",   5000.0,  48, 12, True),
    (f"{PROPERTY_ID}-coca-cola-500",   "Coca-Cola 500ml",  "BEBIDA",   12000.0, 24, 6,  True),
    (f"{PROPERTY_ID}-sprite-500",      "Sprite 500ml",     "BEBIDA",   12000.0, 24, 6,  True),
    (f"{PROPERTY_ID}-cerveza-pilsen",  "Cerveza Pilsen",   "BEBIDA",   15000.0, 36, 12, True),
    (f"{PROPERTY_ID}-papas-fritas",    "Papas fritas",     "SNACK",    8000.0,  20, 6,  True),
    (f"{PROPERTY_ID}-mani",            "Maní salado",      "SNACK",    5000.0,  20, 6,  True),
    (f"{PROPERTY_ID}-lavanderia",      "Lavandería",       "SERVICIO", 80000.0, None, None, False),
    (f"{PROPERTY_ID}-late-checkout",   "Late check-out",   "SERVICIO", 50000.0, None, None, False),
]


def seed_products(cursor):
    cursor.execute("SELECT COUNT(*) FROM producto")
    if cursor.fetchone()[0] > 0:
        print("  [=] Producto table already has rows, skipping seed")
        return 0

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    inserted = 0
    for (pid, name, cat, price, stock, stock_min, is_stocked) in SEED_PRODUCTS:
        cursor.execute("""
            INSERT INTO producto (
                id, property_id, name, category, price,
                stock_current, stock_minimum, is_stocked, is_active,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (pid, PROPERTY_ID, name, cat, price,
              stock, stock_min, 1 if is_stocked else 0, now, now))
        inserted += 1
    print(f"  [+] Seeded {inserted} starter products")
    return inserted


def migrate():
    if not DB_PATH.exists():
        print(f"[!] Database not found at: {DB_PATH}")
        print("    Run the app once to create the schema, then re-run.")
        sys.exit(1)

    print(f"Connecting to: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        print("\n[Step 1/4] Creating producto table...")
        n_producto = create_producto_table(cursor)

        print("\n[Step 2/4] Creating consumo table...")
        n_consumo = create_consumo_table(cursor)

        print("\n[Step 3/4] Creating ajuste_inventario table...")
        n_ajuste = create_ajuste_table(cursor)

        print("\n[Step 4/4] Seeding starter product catalog...")
        n_seeded = seed_products(cursor)

        conn.commit()

        # Verification
        print("\n[Verification]")
        cursor.execute("SELECT COUNT(*) FROM producto")
        p_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM consumo")
        c_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM ajuste_inventario")
        a_count = cursor.fetchone()[0]
        print(f"  producto rows: {p_count}")
        print(f"  consumo rows: {c_count}")
        print(f"  ajuste_inventario rows: {a_count}")

        if p_count > 0:
            print("\n  Products in catalog:")
            cursor.execute(
                "SELECT name, category, price, stock_current, is_stocked "
                "FROM producto ORDER BY category, name"
            )
            for row in cursor.fetchall():
                name, cat, price, stock, is_stocked = row
                stock_str = f"stock={stock}" if is_stocked else "servicio"
                print(f"    - [{cat}] {name}: {price:,.0f} Gs ({stock_str})")

        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY (v1.6.0 Phase 3 — Room Charges & Inventory)")
        print("=" * 60)
        print(f"  producto table created: {'yes' if n_producto else 'no (already existed)'}")
        print(f"  consumo table created: {'yes' if n_consumo else 'no (already existed)'}")
        print(f"  ajuste_inventario table created: {'yes' if n_ajuste else 'no (already existed)'}")
        print(f"  Products seeded: {n_seeded}")
        print("=" * 60)
        print("Migration completed successfully.")

    except sqlite3.Error as e:
        print(f"\n[!] Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRATION: Room Charges & Product Inventory (v1.6.0 Phase 3)")
    print("=" * 60)
    migrate()
