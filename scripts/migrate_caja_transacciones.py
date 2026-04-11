"""
Migration: Add Caja (Cash Register) + Transaccion Tables
==========================================================

Phase 1 of the Cash Register & Transaction System upgrade (v1.4.0).

Creates the tables needed for the new payment tracking system and migrates
existing reservations to the new status lifecycle.

Changes:
1. Creates `caja_sesion` table (cash register sessions)
2. Creates `transaccion` table (immutable payment transactions)
3. Creates indexes on both tables
4. Renames reservation statuses:
     - "Pendiente" -> "RESERVADA"
     - "Confirmada" -> "CONFIRMADA"
     - "Completada" -> "COMPLETADA"
     - "Cancelada"  -> "CANCELADA"
5. For reservations that were previously "Confirmada" (i.e., paid), creates
   one synthetic Transaccion with payment_method='TRANSFERENCIA',
   reference_number='MIGRACION' to preserve financial history.

Idempotent: safe to run multiple times. Checks for table/column existence
before attempting changes.

Usage:
    python scripts/migrate_caja_transacciones.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

DB_PATH = backend_path / "hotel.db"


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def create_caja_sesion_table(cursor):
    """Create caja_sesion table if it doesn't exist."""
    if table_exists(cursor, "caja_sesion"):
        print("  [=] Table 'caja_sesion' already exists, skipping")
        return 0

    cursor.execute("""
        CREATE TABLE caja_sesion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME,
            opening_balance REAL NOT NULL DEFAULT 0.0,
            closing_balance_declared REAL,
            closing_balance_expected REAL,
            difference REAL,
            status VARCHAR NOT NULL DEFAULT 'ABIERTA',
            notes VARCHAR,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("CREATE INDEX idx_caja_sesion_user_id ON caja_sesion(user_id)")
    cursor.execute("CREATE INDEX idx_caja_sesion_status ON caja_sesion(status)")
    print("  [+] Created table 'caja_sesion' with indexes")
    return 1


def create_transaccion_table(cursor):
    """Create transaccion table if it doesn't exist."""
    if table_exists(cursor, "transaccion"):
        print("  [=] Table 'transaccion' already exists, skipping")
        return 0

    cursor.execute("""
        CREATE TABLE transaccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reserva_id VARCHAR,
            caja_sesion_id INTEGER,
            amount REAL NOT NULL,
            payment_method VARCHAR NOT NULL,
            reference_number VARCHAR,
            description VARCHAR,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by VARCHAR,
            voided BOOLEAN NOT NULL DEFAULT 0,
            void_reason VARCHAR,
            voided_at DATETIME,
            voided_by VARCHAR,
            FOREIGN KEY (reserva_id) REFERENCES reservations(id),
            FOREIGN KEY (caja_sesion_id) REFERENCES caja_sesion(id)
        )
    """)
    cursor.execute("CREATE INDEX idx_transaccion_reserva_id ON transaccion(reserva_id)")
    cursor.execute("CREATE INDEX idx_transaccion_caja_sesion_id ON transaccion(caja_sesion_id)")
    cursor.execute("CREATE INDEX idx_transaccion_payment_method ON transaccion(payment_method)")
    cursor.execute("CREATE INDEX idx_transaccion_created_at ON transaccion(created_at)")
    cursor.execute("CREATE INDEX idx_transaccion_voided ON transaccion(voided)")
    print("  [+] Created table 'transaccion' with indexes")
    return 1


def rename_reservation_statuses(cursor):
    """Rename existing reservation statuses to new values."""
    mapping = [
        ("Pendiente", "RESERVADA"),
        ("Confirmada", "CONFIRMADA"),
        ("Completada", "COMPLETADA"),
        ("Cancelada", "CANCELADA"),
    ]
    total = 0
    for old, new in mapping:
        cursor.execute(
            "UPDATE reservations SET status = ? WHERE status = ?",
            (new, old),
        )
        count = cursor.rowcount
        if count > 0:
            print(f"  [+] Renamed {count} reservation(s): '{old}' -> '{new}'")
        total += count
    return total


def create_synthetic_transactions_for_confirmed(cursor):
    """Create one synthetic TRANSFERENCIA transaction per CONFIRMADA reservation
    that has no existing transaction, to preserve financial history."""
    # Find CONFIRMADA reservations without any transaction
    cursor.execute("""
        SELECT r.id, r.price, r.guest_name, r.check_in_date
        FROM reservations r
        LEFT JOIN transaccion t
            ON t.reserva_id = r.id AND t.voided = 0
        WHERE r.status = 'CONFIRMADA'
          AND r.price IS NOT NULL
          AND r.price > 0
          AND t.id IS NULL
    """)
    rows = cursor.fetchall()

    if not rows:
        print("  [=] No CONFIRMADA reservations need synthetic transactions")
        return 0

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    inserted = 0
    for res_id, price, guest_name, check_in in rows:
        cursor.execute("""
            INSERT INTO transaccion (
                reserva_id, caja_sesion_id, amount, payment_method,
                reference_number, description, created_at, created_by,
                voided
            ) VALUES (?, NULL, ?, 'TRANSFERENCIA', 'MIGRACION',
                      ?, ?, 'sistema', 0)
        """, (
            res_id,
            float(price),
            f"Pago pre-migracion v1.4.0 ({guest_name or 'N/A'})",
            now,
        ))
        inserted += 1

    print(f"  [+] Created {inserted} synthetic TRANSFERENCIA transaction(s) for migration")
    return inserted


def migrate():
    if not DB_PATH.exists():
        print(f"[!] Database not found at: {DB_PATH}")
        print("    Run the app once to create the schema, then re-run this migration.")
        sys.exit(1)

    print(f"Connecting to: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        print("\n[Step 1/4] Creating tables...")
        created_caja = create_caja_sesion_table(cursor)
        created_trans = create_transaccion_table(cursor)

        print("\n[Step 2/4] Renaming reservation statuses...")
        renamed = rename_reservation_statuses(cursor)
        if renamed == 0:
            print("  [=] No reservations needed renaming (already uppercase or empty)")

        print("\n[Step 3/4] Creating synthetic transactions for CONFIRMADA reservations...")
        synthetic = create_synthetic_transactions_for_confirmed(cursor)

        conn.commit()

        print("\n[Step 4/4] Verification...")
        cursor.execute("SELECT COUNT(*) FROM caja_sesion")
        caja_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transaccion")
        trans_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transaccion WHERE reference_number = 'MIGRACION'")
        migrated_trans = cursor.fetchone()[0]
        cursor.execute("""
            SELECT status, COUNT(*) FROM reservations GROUP BY status ORDER BY status
        """)
        status_counts = cursor.fetchall()

        print(f"  caja_sesion rows: {caja_count}")
        print(f"  transaccion rows: {trans_count} (of which {migrated_trans} from migration)")
        print(f"  reservations by status:")
        for s, c in status_counts:
            print(f"    - {s}: {c}")

        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"  caja_sesion table created: {'yes' if created_caja else 'no (already existed)'}")
        print(f"  transaccion table created: {'yes' if created_trans else 'no (already existed)'}")
        print(f"  Reservations renamed: {renamed}")
        print(f"  Synthetic transactions created: {synthetic}")
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
    print("MIGRATION: Caja + Transacciones (v1.4.0)")
    print("=" * 60)
    migrate()
