"""
Migration 007: Room status audit log (v1.9.0 — Feature 3)
==========================================================

Adds an append-only audit trail of room-status transitions. Closes the
TODO in `backend/api/v1/endpoints/rooms.py:326` (now removed).

Changes
-------
1. `room_status_log` table — one row per PATCH /rooms/{id}/status.
   Captures previous_status, new_status, changed_by (username), reason,
   changed_at.

2. Indexes on (room_id) and (changed_at) for the per-room history query
   (`GET /rooms/{id}/status-log` ordered by changed_at DESC).

Phantom-table cleanup
---------------------
The legacy `scripts/migrate_monges.py` (removed in v1.9.0, see D1)
created a `room_status_log` table with a different schema (TEXT room_id
+ extra `property_id` and `changed_by_type` columns) and no SQLAlchemy
model. If a database was bootstrapped with that script, we DROP the
phantom table and recreate it cleanly with the new schema. The phantom
table was never written to (no code path inserted rows), so no data is
lost.

Idempotent — safe to re-run.
"""

import sqlite3

MIGRATION_NAME = "007_room_status_log"
MIGRATION_DESCRIPTION = "Add room_status_log table + indexes (Feature 3)"


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, table, index_name):
    cursor.execute(f"PRAGMA index_list({table})")
    return any(row[1] == index_name for row in cursor.fetchall())


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _is_phantom_schema(cursor):
    """Detect the legacy migrate_monges.py schema (has property_id / changed_by_type)."""
    if not _table_exists(cursor, "room_status_log"):
        return False
    return _column_exists(cursor, "room_status_log", "property_id") and not _column_exists(
        cursor, "room_status_log", "previous_status"
    )


def run(conn: sqlite3.Connection):
    """Apply migration 007. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 0. Drop phantom table from migrate_monges.py if present ---------
    if _is_phantom_schema(cursor):
        cursor.execute("DROP TABLE room_status_log")

    # --- 1. room_status_log table ---------------------------------------
    if not _table_exists(cursor, "room_status_log"):
        cursor.execute(
            """
            CREATE TABLE room_status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id VARCHAR NOT NULL,
                previous_status VARCHAR,
                new_status VARCHAR NOT NULL,
                changed_by VARCHAR,
                reason VARCHAR,
                changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms (id)
            )
            """
        )

    # --- 2. Indexes -----------------------------------------------------
    if not _index_exists(cursor, "room_status_log", "idx_room_status_log_room"):
        cursor.execute(
            "CREATE INDEX idx_room_status_log_room ON room_status_log (room_id)"
        )
    if not _index_exists(cursor, "room_status_log", "idx_room_status_log_changed_at"):
        cursor.execute(
            "CREATE INDEX idx_room_status_log_changed_at ON room_status_log (changed_at)"
        )
