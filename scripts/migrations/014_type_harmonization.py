"""
Migration 014: Type harmonization (v1.10.0 -- Phase 2b)
========================================================

Cleans up the SQLite schema before the PostgreSQL cutover:

  1. Drop `properties.breakfast_included` (deprecated since v1.7).
     Uses SQLite 3.35+ native DROP COLUMN (we run 3.50.4 locally).

  2. Backfill `properties.slug WHERE slug IS NULL → properties.id`, then
     enforce NOT NULL.  Already-populated rows are left alone.

  3. Verify (defense in depth -- read-only) that:
     - every Boolean-as-Integer column holds only NULL / 0 / 1
     - every JSON-in-String column parses as valid JSON
     - zero orphan `property_id` values across the 8 tables that get
       their FK promoted in migration 015

  Steps 1-2 are data ops; the rest are sanity checks that log warnings
  but never abort the migration (we already audited before writing this).

The Boolean / JSON / Date→DateTime promotions are MODEL-ONLY changes in
database.py -- SQLite stores all of these as the same underlying value
(INTEGER for bool, TEXT for JSON/DateTime), so the ORM round-trips
transparently. The change becomes "real" on a fresh init_db() or on
the future Postgres migration. No data rewrite needed here.

FK promotions for the 8 remaining property_id columns also go in
migration 015 (model-only, Option A). They're split out so this
migration can be reviewed independently.

Idempotent -- safe to re-run.
"""
from __future__ import annotations

import json
import sqlite3

MIGRATION_NAME = "014_type_harmonization"
MIGRATION_DESCRIPTION = (
    "Drop properties.breakfast_included + backfill+enforce slug NOT NULL + "
    "verify Boolean/JSON/FK data quality (Phase 2b)"
)


# Columns that the model now declares as Boolean (must be NULL / 0 / 1)
BOOLEAN_COLUMNS = [
    ("room_categories", "active"),
    ("rooms", "active"),
    ("client_types", "active"),
    ("client_types", "requires_contract"),
    ("client_contracts", "active"),
    ("pricing_seasons", "active"),
    ("properties", "active"),
    ("properties", "parking_available"),
    ("properties", "meals_enabled"),
    ("ical_feeds", "sync_enabled"),
    ("meal_plans", "is_system"),
    ("meal_plans", "is_active"),
    ("ai_agent_permissions", "can_view_reservations"),
    ("ai_agent_permissions", "can_create_reservations"),
    ("ai_agent_permissions", "can_modify_reservations"),
    ("ai_agent_permissions", "can_cancel_reservations"),
    ("ai_agent_permissions", "can_view_guests"),
    ("ai_agent_permissions", "can_modify_guests"),
    ("ai_agent_permissions", "can_view_rooms"),
    ("ai_agent_permissions", "can_modify_rooms"),
    ("ai_agent_permissions", "can_modify_room_status"),
    ("ai_agent_permissions", "can_view_prices"),
    ("ai_agent_permissions", "can_modify_prices"),
    ("ai_agent_permissions", "can_view_reports"),
    ("ai_agent_permissions", "can_export_data"),
    ("ai_agent_permissions", "can_modify_settings"),
    ("ai_agent_permissions", "requires_confirmation"),
    ("migration_history", "success"),
]

# Columns that the model now declares as JSON (must parse via json.loads)
JSON_COLUMNS = [
    ("room_categories", "bed_configuration"),
    ("room_categories", "amenities"),
    ("reservations", "price_breakdown"),
    ("pricing_seasons", "applies_to_categories"),
    ("price_calculations", "calculation_details"),
]

# Tables whose `property_id` gets FK-promoted in migration 015
PROPERTY_ID_TABLES = [
    "room_categories",
    "rooms",
    "reservations",
    "system_settings",
    "client_types",
    "client_contracts",
    "pricing_seasons",
    "price_calculations",
]


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _verify_booleans(cursor) -> list[str]:
    """Returns list of warning strings (empty if clean)."""
    warnings: list[str] = []
    for table, col in BOOLEAN_COLUMNS:
        if not _table_exists(cursor, table) or not _column_exists(cursor, table, col):
            continue
        bad = cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} NOT IN (0, 1)"
        ).fetchone()[0]
        if bad > 0:
            warnings.append(
                f"  [WARN] {table}.{col} has {bad} row(s) with values outside {{0,1,NULL}}"
            )
    return warnings


def _verify_json(cursor) -> list[str]:
    warnings: list[str] = []
    for table, col in JSON_COLUMNS:
        if not _table_exists(cursor, table) or not _column_exists(cursor, table, col):
            continue
        bad = 0
        for row in cursor.execute(
            f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
        ):
            try:
                json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                bad += 1
        if bad > 0:
            warnings.append(f"  [WARN] {table}.{col} has {bad} row(s) with invalid JSON")
    return warnings


def _verify_property_id_orphans(cursor) -> list[str]:
    warnings: list[str] = []
    for table in PROPERTY_ID_TABLES:
        if not _table_exists(cursor, table) or not _column_exists(cursor, table, "property_id"):
            continue
        try:
            orphans = cursor.execute(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE property_id IS NOT NULL "
                f"AND property_id NOT IN (SELECT id FROM properties)"
            ).fetchone()[0]
            if orphans > 0:
                warnings.append(f"  [WARN] {table}.property_id has {orphans} orphan row(s)")
        except sqlite3.OperationalError as e:
            warnings.append(f"  [WARN] {table}.property_id orphan check failed: {e}")
    return warnings


def run(conn: sqlite3.Connection):
    """Apply migration 014. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # ----------------------------------------------------------------
    # 1. Drop properties.breakfast_included (SQLite 3.35+ native).
    # ----------------------------------------------------------------
    if _column_exists(cursor, "properties", "breakfast_included"):
        # Final safety check -- if anything is using the column, log the value
        # distribution but DROP either way (the column is deprecated and the
        # ORM no longer reads it).
        try:
            values = cursor.execute(
                "SELECT DISTINCT breakfast_included FROM properties"
            ).fetchall()
            print(f"  [info] properties.breakfast_included distinct values: {[v[0] for v in values]}")
        except sqlite3.OperationalError:
            pass
        cursor.execute("ALTER TABLE properties DROP COLUMN breakfast_included")
        print("  [ok]   Dropped properties.breakfast_included (deprecated since v1.7)")
    else:
        print("  [..]   properties.breakfast_included already dropped (idempotent)")

    # ----------------------------------------------------------------
    # 2. Backfill properties.slug WHERE NULL → properties.id, then NOT NULL.
    # ----------------------------------------------------------------
    null_slugs = cursor.execute(
        "SELECT COUNT(*) FROM properties WHERE slug IS NULL"
    ).fetchone()[0]
    if null_slugs > 0:
        cursor.execute("UPDATE properties SET slug = id WHERE slug IS NULL")
        print(f"  [ok]   Backfilled slug for {null_slugs} property row(s) (slug <- id)")
    else:
        print("  [..]   No NULL slugs to backfill")

    # SQLite cannot ALTER COLUMN ... SET NOT NULL on an existing column without
    # a table rebuild. We've backfilled the data + the model now declares
    # nullable=False, so any fresh init_db() will create the column NOT NULL.
    # On the existing column, the model + service layer is the enforcement
    # (every INSERT into properties already supplies a slug). Documented in
    # Phase 1 Option A.
    final_nulls = cursor.execute(
        "SELECT COUNT(*) FROM properties WHERE slug IS NULL"
    ).fetchone()[0]
    if final_nulls > 0:
        raise RuntimeError(
            f"slug backfill incomplete: {final_nulls} NULL slugs remain -- "
            f"investigate before continuing"
        )

    # ----------------------------------------------------------------
    # 3. Data-quality verification (warnings only -- we already audited).
    # ----------------------------------------------------------------
    bool_warnings = _verify_booleans(cursor)
    json_warnings = _verify_json(cursor)
    orphan_warnings = _verify_property_id_orphans(cursor)

    if bool_warnings:
        print("  Boolean data anomalies:")
        for w in bool_warnings:
            print(w)
    else:
        print("  [ok]   All Boolean-as-Integer columns clean (NULL / 0 / 1 only)")

    if json_warnings:
        print("  JSON data anomalies:")
        for w in json_warnings:
            print(w)
    else:
        print("  [ok]   All JSON-in-String columns parse correctly")

    if orphan_warnings:
        print("  property_id orphan anomalies:")
        for w in orphan_warnings:
            print(w)
    else:
        print("  [ok]   Zero property_id orphans across 8 tables (safe for migration 015)")
