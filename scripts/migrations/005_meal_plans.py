"""
Migration 005: Meal plans & kitchen reports (v1.7.0 — Phase 4)
==============================================================

Adds support for **optional** meal service configuration. Hotels that don't
serve meals keep the default (disabled) behaviour; nothing in the UI or pricing
changes for them.

Changes
-------
1. `properties` table — add `meals_enabled` (Integer, default=0) and
   `meal_inclusion_mode` (String, nullable). Legacy `breakfast_included`
   column is kept for one release (v1.7.x) for backward compat; the migration
   backfills `meals_enabled=1, meal_inclusion_mode='INCLUIDO'` for any property
   where `breakfast_included=1`. Plan to drop `breakfast_included` in v1.8.

2. `meal_plans` table (NEW) — catalog of breakfast/half-board/full-board
   offerings. Unique `(property_id, code)`. `is_system=1` plans (seeded by
   this migration) cannot be deleted by the admin UI.

3. `reservations` table — add `meal_plan_id` (nullable FK) and
   `breakfast_guests` (nullable Integer: 0..guests_count).

4. Seed every existing property with a `SOLO_HABITACION` plan
   (applies_to_mode=ANY, zero surcharge) so the reservation form always has a
   fallback option once meals are enabled.

Idempotent — safe to re-run. Uses `PRAGMA table_info` / `sqlite_master` to skip
operations that have already been applied.
"""

import sqlite3
import uuid
from datetime import datetime

MIGRATION_NAME = "005_meal_plans"
MIGRATION_DESCRIPTION = "Add meal plan config + kitchen reports (Phase 4)"


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _add_if_missing(cursor, table, column_name, column_def):
    if _column_exists(cursor, table, column_name):
        return 0
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
    return 1


def _seed_plan(cursor, property_id, code, name, surcharge_pp, surcharge_room, applies_to_mode, is_system, sort_order):
    """Insert a meal plan if not already present for this property+code."""
    cursor.execute(
        "SELECT id FROM meal_plans WHERE property_id=? AND code=?",
        (property_id, code),
    )
    if cursor.fetchone():
        return 0
    now = datetime.now().isoformat()
    cursor.execute(
        """
        INSERT INTO meal_plans (
            id, property_id, code, name, description,
            surcharge_per_person, surcharge_per_room,
            applies_to_mode, is_system, is_active, sort_order,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            property_id,
            code,
            name,
            None,
            float(surcharge_pp),
            float(surcharge_room),
            applies_to_mode,
            int(is_system),
            sort_order,
            now,
            now,
        ),
    )
    return 1


def run(conn: sqlite3.Connection):
    """Apply migration 005. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. Property columns ---------------------------------------------
    _add_if_missing(cursor, "properties", "meals_enabled", "INTEGER DEFAULT 0")
    _add_if_missing(cursor, "properties", "meal_inclusion_mode", "VARCHAR")

    # --- 2. meal_plans table --------------------------------------------
    if not _table_exists(cursor, "meal_plans"):
        cursor.execute(
            """
            CREATE TABLE meal_plans (
                id VARCHAR PRIMARY KEY,
                property_id VARCHAR NOT NULL,
                code VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                description VARCHAR,
                surcharge_per_person FLOAT NOT NULL DEFAULT 0.0,
                surcharge_per_room FLOAT NOT NULL DEFAULT 0.0,
                applies_to_mode VARCHAR NOT NULL DEFAULT 'ANY',
                is_system INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                UNIQUE (property_id, code),
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX idx_meal_plans_property ON meal_plans (property_id)"
        )
        cursor.execute(
            "CREATE INDEX idx_meal_plans_active ON meal_plans (is_active)"
        )

    # --- 3. Reservation columns -----------------------------------------
    _add_if_missing(cursor, "reservations", "meal_plan_id", "VARCHAR")
    _add_if_missing(cursor, "reservations", "breakfast_guests", "INTEGER")
    # Index on meal_plan_id for join performance on kitchen report
    cursor.execute("PRAGMA index_list(reservations)")
    existing_indexes = {row[1] for row in cursor.fetchall()}
    if "idx_reservations_meal_plan" not in existing_indexes:
        try:
            cursor.execute(
                "CREATE INDEX idx_reservations_meal_plan ON reservations (meal_plan_id)"
            )
        except sqlite3.OperationalError:
            # Some SQLite builds reject indexing nullable FKs that were just added;
            # not fatal — the table is small and full scan is fine.
            pass

    # --- 4. Backfill legacy breakfast_included --------------------------
    # Only applies when the old flag was set and the new flag is still default.
    cursor.execute(
        """
        UPDATE properties
           SET meals_enabled = 1,
               meal_inclusion_mode = 'INCLUIDO'
         WHERE breakfast_included = 1
           AND (meals_enabled = 0 OR meals_enabled IS NULL)
        """
    )

    # --- 5. Seed SOLO_HABITACION plan per property ----------------------
    cursor.execute("SELECT id, meal_inclusion_mode FROM properties")
    for prop_id, mode in cursor.fetchall():
        _seed_plan(
            cursor,
            property_id=prop_id,
            code="SOLO_HABITACION",
            name="Solo habitación",
            surcharge_pp=0,
            surcharge_room=0,
            applies_to_mode="ANY",
            is_system=1,
            sort_order=0,
        )
        # If legacy INCLUIDO, seed CON_DESAYUNO with zero surcharge
        if mode == "INCLUIDO":
            _seed_plan(
                cursor,
                property_id=prop_id,
                code="CON_DESAYUNO",
                name="Con desayuno (incluido)",
                surcharge_pp=0,
                surcharge_room=0,
                applies_to_mode="INCLUIDO",
                is_system=1,
                sort_order=1,
            )
