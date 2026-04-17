"""
Migration 001: Cash Register & Transactions (v1.4.0 — Phase 1)
=================================================================

Creates the tables needed for the payment tracking system and migrates
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
5. For reservations that were previously "Confirmada", creates one synthetic
   TRANSFERENCIA transaction with reference_number='MIGRACION' to preserve
   financial history.

Idempotent: safe to run multiple times via run_migrations.py.
"""

import sqlite3
from datetime import datetime

MIGRATION_NAME = "caja_transacciones"
MIGRATION_DESCRIPTION = "v1.4.0 — Cash register + immutable transactions + status lifecycle"


def _table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cursor.fetchone() is not None


def _create_caja_sesion(cursor):
    if _table_exists(cursor, "caja_sesion"):
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
    return 1


def _create_transaccion(cursor):
    if _table_exists(cursor, "transaccion"):
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
    return 1


def _rename_reservation_statuses(cursor):
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
        total += cursor.rowcount
    return total


def _create_synthetic_transactions_for_confirmed(cursor):
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
        return 0

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    for res_id, price, guest_name, _ in rows:
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
    return len(rows)


def run(conn: sqlite3.Connection):
    """Apply migration 001. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()
    _create_caja_sesion(cursor)
    _create_transaccion(cursor)
    _rename_reservation_statuses(cursor)
    _create_synthetic_transactions_for_confirmed(cursor)
