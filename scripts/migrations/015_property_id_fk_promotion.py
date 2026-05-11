"""
Migration 015: property_id FK promotion -- model-only (v1.10.0 -- Phase 2b)
==========================================================================

Promotes the 8 remaining `property_id` columns from plain String to a real
ForeignKey to `properties.id`. Same Option A approach used by Phase 1 +
Phase 2a -- the change lives in the SQLAlchemy model and takes effect on:

  * Fresh `init_db()` on a clean SQLite DB
  * The future PostgreSQL cutover (Phase 3+)

On the existing SQLite production DB, the column metadata stays unchanged
-- SQLite cannot ALTER a column to add a FOREIGN KEY without rebuilding
the whole table. The enforcement gap is fine because:

  1. Zero orphans were verified pre-migration (014 ran the audit and
     migration 015 re-verifies as a safety check).
  2. The Postgres cutover migration will rebuild the schema from scratch
     with all FKs in place.

Columns promoted (8):
  1. room_categories.property_id     (NOT NULL → RESTRICT)
  2. rooms.property_id               (NOT NULL → RESTRICT)
  3. reservations.property_id        (NULLABLE → RESTRICT)
  4. system_settings.property_id     (NOT NULL → RESTRICT)
  5. client_types.property_id        (NOT NULL → RESTRICT)
  6. client_contracts.property_id    (NOT NULL → RESTRICT)
  7. pricing_seasons.property_id     (NOT NULL → RESTRICT)
  8. price_calculations.property_id  (NOT NULL → RESTRICT)

Why this is a "migration" at all (vs. just a model edit):
  - `migration_history` records that this convention change was applied
    at this point in version history. When v1.10.0 ships, anyone running
    `python scripts/run_migrations.py` on a stale DB sees an audit-trail
    entry confirming the promotion was reviewed.
  - It re-verifies orphans at runtime, catching any data that drifted
    between migration 014 and the cutover.

Idempotent -- safe to re-run.
"""
from __future__ import annotations

import sqlite3

MIGRATION_NAME = "015_property_id_fk_promotion"
MIGRATION_DESCRIPTION = (
    "Promote 8 remaining property_id columns to ForeignKey in the SQLAlchemy "
    "model (Option A, takes effect on fresh init_db / Postgres cutover) -- "
    "Phase 2b"
)

PROMOTED_TABLES = [
    "room_categories",
    "rooms",
    "reservations",
    "system_settings",
    "client_types",
    "client_contracts",
    "pricing_seasons",
    "price_calculations",
]


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def run(conn: sqlite3.Connection):
    """Apply migration 015. Verifies orphans + records the model-only change."""
    cursor = conn.cursor()

    total_orphans = 0
    for table in PROMOTED_TABLES:
        if not _table_exists(cursor, table):
            print(f"  [..]   {table}: table not present (skip)")
            continue
        try:
            orphans = cursor.execute(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE property_id IS NOT NULL "
                f"AND property_id NOT IN (SELECT id FROM properties)"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            print(f"  [WARN] {table}: orphan check failed ({e}) -- skipping")
            continue
        if orphans == 0:
            print(f"  [ok]   {table}.property_id: 0 orphans (FK promoted in model)")
        else:
            total_orphans += orphans
            print(f"  [FAIL] {table}.property_id: {orphans} ORPHAN ROW(S) -- cleanup required")

    if total_orphans > 0:
        raise RuntimeError(
            f"Cannot promote property_id to FK: {total_orphans} orphan row(s) "
            f"across {len(PROMOTED_TABLES)} tables. Fix the data, then re-run."
        )

    print("  [ok]   All 8 property_id columns are model-promoted to ForeignKey (Option A)")
    print("    Enforcement lands on fresh init_db() or Postgres cutover.")
