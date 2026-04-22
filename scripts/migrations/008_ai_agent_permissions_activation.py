"""
Migration 008: Activate AIAgentPermission (v1.9.0 — Feature 1)
================================================================

The `ai_agent_permissions` table model has lived in `database.py:512`
since early versions of the project as scaffold for granular per-role
agent control. Phase 6 (v1.9.0) wires it up: a service, an admin UI,
and a middleware that filters the agent's tool list per role.

This migration ensures the table exists (it normally does, since
`database.py:init_db()` calls `Base.metadata.create_all`) and seeds
default rows for the standard roles. Idempotent — safe to re-run.

Default seed (one row per role)
--------------------------------
- admin / supervisor / gerencia: every permission TRUE
- recepcion / recepcionista: view_reservations + view_guests + view_rooms
  + view_prices = TRUE; everything else FALSE (financial/heavy reports
  blocked from the agent — they remain accessible via the dedicated PC
  pages)
- cocina: every permission FALSE (cocina users use the dedicated PC page,
  not the agent)
"""

import sqlite3

MIGRATION_NAME = "008_ai_agent_permissions_activation"
MIGRATION_DESCRIPTION = "Seed AIAgentPermission default rows by role (Feature 1)"


PERMISSION_COLUMNS = [
    "can_view_reservations",
    "can_create_reservations",
    "can_modify_reservations",
    "can_cancel_reservations",
    "can_view_guests",
    "can_modify_guests",
    "can_view_rooms",
    "can_modify_rooms",
    "can_modify_room_status",
    "can_view_prices",
    "can_modify_prices",
    "can_view_reports",
    "can_export_data",
    "can_modify_settings",
]


def _all_true():
    return {c: 1 for c in PERMISSION_COLUMNS}


def _all_false():
    return {c: 0 for c in PERMISSION_COLUMNS}


def _recepcion():
    perms = _all_false()
    perms["can_view_reservations"] = 1
    perms["can_view_guests"] = 1
    perms["can_view_rooms"] = 1
    perms["can_view_prices"] = 1
    return perms


DEFAULTS = {
    "admin":         _all_true(),
    "supervisor":    _all_true(),
    "gerencia":      _all_true(),
    "recepcion":     _recepcion(),
    "recepcionista": _recepcion(),
    "cocina":        _all_false(),
}


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def run(conn: sqlite3.Connection):
    """Apply migration 008. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # The table itself is created by SQLAlchemy via init_db (Base.metadata.create_all).
    # If the table somehow doesn't exist, create it here matching the model.
    if not _table_exists(cursor, "ai_agent_permissions"):
        cursor.execute(
            """
            CREATE TABLE ai_agent_permissions (
                id VARCHAR PRIMARY KEY,
                property_id VARCHAR,
                role VARCHAR NOT NULL,
                can_view_reservations INTEGER DEFAULT 1,
                can_create_reservations INTEGER DEFAULT 1,
                can_modify_reservations INTEGER DEFAULT 0,
                can_cancel_reservations INTEGER DEFAULT 0,
                can_view_guests INTEGER DEFAULT 1,
                can_modify_guests INTEGER DEFAULT 0,
                can_view_rooms INTEGER DEFAULT 1,
                can_modify_rooms INTEGER DEFAULT 0,
                can_modify_room_status INTEGER DEFAULT 0,
                can_view_prices INTEGER DEFAULT 1,
                can_modify_prices INTEGER DEFAULT 0,
                can_view_reports INTEGER DEFAULT 1,
                can_export_data INTEGER DEFAULT 0,
                can_modify_settings INTEGER DEFAULT 0,
                requires_confirmation INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
            """
        )

    # Seed defaults — INSERT only when row absent for that role
    cols = ["id", "property_id", "role"] + PERMISSION_COLUMNS
    placeholders = ", ".join("?" for _ in cols)
    insert_sql = f"INSERT INTO ai_agent_permissions ({', '.join(cols)}) VALUES ({placeholders})"

    for role, perms in DEFAULTS.items():
        existing = cursor.execute(
            "SELECT id FROM ai_agent_permissions WHERE role = ?", (role,)
        ).fetchone()
        if existing:
            continue
        values = [f"role-{role}", None, role] + [perms[c] for c in PERMISSION_COLUMNS]
        cursor.execute(insert_sql, values)
