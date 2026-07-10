"""
Migration 019: Cleaning buffer for late-checkout blocking (Phase 6.5)
======================================================================

Adds the per-property cleaning buffer consumed by the late-checkout
availability guard. When a reservation has late check-out until HH:MM,
the next same-day arrival on that room must come at HH:MM + buffer.

Companion code change: `ReservationService.create_reservations` now
consults `late_checkout_time` (stored since migration 018) — this
migration only adds the configurable buffer.

Schema changes
--------------
On `properties` (additive):
  cleaning_buffer_minutes INTEGER NOT NULL DEFAULT 30

Idempotent — safe to re-run.
"""
from __future__ import annotations

import sqlite3

MIGRATION_NAME = "019_cleaning_buffer"
MIGRATION_DESCRIPTION = (
    "Add properties.cleaning_buffer_minutes (default 30) for the Phase 6.5 "
    "late-checkout availability guard"
)


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def run(conn: sqlite3.Connection):
    cursor = conn.cursor()

    if not _column_exists(cursor, "properties", "cleaning_buffer_minutes"):
        cursor.execute(
            "ALTER TABLE properties ADD COLUMN cleaning_buffer_minutes "
            "INTEGER NOT NULL DEFAULT 30"
        )

    # No data backfill — every property gets the 30-minute default until an
    # admin tunes it (future Settings UI extension).
