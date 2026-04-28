"""
Migration 012: Buildings table (v1.10.0 — Phase 2a, Part 2)
=============================================================

Creates the `buildings` table that has been a planned-but-missing target of
`rooms.building_id` since the `Room` model was first defined. Seeds a default
"Edificio Principal" per existing property and backfills every existing room
to point to it, so the FK promoted in the model becomes meaningful from day
one. Hotels with annexes can then add additional buildings via the admin UI.

Decisions
---------
- One default building per property, id = `<property_id>-principal`,
  name = "Edificio Principal", sort_order = 0.
- Backfill any room with NULL building_id (most of them today) to that
  default. Rooms with a non-NULL building_id (none today, but defensive
  for re-runs) are left alone.
- The FK promotion on `rooms.building_id` is model-only (Phase 1 Option A —
  no SQLite ALTER FK). PostgreSQL migration will pick it up.

Idempotent — safe to re-run. Both the table creation and the seed are
guarded by existence checks.
"""

import sqlite3

MIGRATION_NAME = "012_buildings_table"
MIGRATION_DESCRIPTION = "Create buildings table + seed default per property + backfill rooms (Phase 2a)"


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, index_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


def run(conn: sqlite3.Connection):
    """Apply migration 012. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. Create buildings table (idempotent) ---
    if not _table_exists(cursor, "buildings"):
        cursor.execute(
            """
            CREATE TABLE buildings (
                id            VARCHAR PRIMARY KEY,
                property_id   VARCHAR NOT NULL,
                name          VARCHAR NOT NULL,
                description   VARCHAR,
                floors        INTEGER,
                sort_order    INTEGER DEFAULT 0,
                is_active     BOOLEAN DEFAULT 1,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id),
                CONSTRAINT uq_buildings_property_name UNIQUE (property_id, name)
            )
            """
        )

    if not _index_exists(cursor, "ix_buildings_property_id"):
        cursor.execute("CREATE INDEX ix_buildings_property_id ON buildings (property_id)")
    if not _index_exists(cursor, "idx_buildings_property_active"):
        cursor.execute(
            "CREATE INDEX idx_buildings_property_active ON buildings (property_id, is_active)"
        )

    # --- 2. Seed default building per property (idempotent INSERT) ---
    cursor.execute("SELECT id FROM properties")
    properties = [row[0] for row in cursor.fetchall()]
    for prop_id in properties:
        default_id = f"{prop_id}-principal"
        cursor.execute("SELECT id FROM buildings WHERE id = ?", (default_id,))
        if cursor.fetchone():
            continue
        cursor.execute(
            """
            INSERT INTO buildings (id, property_id, name, description, sort_order, is_active)
            VALUES (?, ?, 'Edificio Principal', 'Edificio principal del hotel.', 0, 1)
            """,
            (default_id, prop_id),
        )

    # --- 3. Backfill rooms.building_id where NULL ---
    # Use property_id to target the matching default. Rooms whose property_id
    # has no building (shouldn't happen, but defensive) are left unchanged.
    cursor.execute(
        """
        UPDATE rooms
        SET building_id = property_id || '-principal'
        WHERE building_id IS NULL
          AND EXISTS (
              SELECT 1 FROM buildings b WHERE b.id = rooms.property_id || '-principal'
          )
        """
    )

    # --- 4. Index on rooms.building_id (the model declares it, but we add it
    # explicitly here so existing DBs gain the index without waiting for a
    # full init_db rebuild). ---
    if not _index_exists(cursor, "ix_rooms_building_id"):
        cursor.execute("CREATE INDEX ix_rooms_building_id ON rooms (building_id)")
