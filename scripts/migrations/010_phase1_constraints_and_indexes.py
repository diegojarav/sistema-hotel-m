"""
Migration 010: Phase 1 — UNIQUE constraints + composite indexes (v1.10.0)
==========================================================================

Closes Phase 1 of the Postgres-readiness work. Two orthogonal sets of changes:

A. UNIQUE constraints on three tables where the service layer assumed
   uniqueness but the schema didn't enforce it (audit issues #9, #10):
     - meal_plans (property_id, code)               — was in migration 005 SQL,
                                                      missing from model
     - system_settings (property_id, setting_key)   — service did upsert by hand
     - ai_agent_permissions (property_id, role)     — service assumed it

   These are added via `CREATE UNIQUE INDEX IF NOT EXISTS` rather than a
   table rebuild. Functionally identical to a `UniqueConstraint` for query
   planning + insert validation, and avoids touching the FK relationships
   (which would otherwise need the table-rebuild dance under SQLite).

B. Composite performance indexes for hot queries (audit issue #19). All
   pure-additive `CREATE INDEX IF NOT EXISTS` — zero risk:

     - email_log (reserva_id, status, sent_at)   — rate-limit query
     - transaccion (reserva_id, voided)          — saldo() folio query
     - consumo (reserva_id, voided)              — saldo() folio query
     - room_status_log (room_id, changed_at)     — per-room history endpoint
     - ajuste_inventario (producto_id, created_at) — stock history
     - producto (property_id, is_active)         — low-stock query

Cascades on FK columns (audit issue #1) and CHECK constraints (issue #15)
are declared in the SQLAlchemy model only — they take effect on fresh
init_db() and on the eventual Postgres cutover. SQLite does not support
ALTER FK / ADD CHECK in place without a full table rebuild, and rebuilding
~12 tables inside one migration carries more risk than it solves at this
stage. Existing dev/staging SQLite DBs will continue to behave as they did
before (no cascades, no CHECK enforcement on existing rows) — this is
acceptable because: (a) deletes are rare in production today, (b)
`PRAGMA foreign_keys=ON` (Fix #16) catches any orphan attempts, and (c)
all current data already conforms to the CHECK constraints (verified
during the audit). The constraints become real on Postgres.

Pre-flight: this migration verifies no duplicate rows would block the
UNIQUE indexes. The audit already confirmed zero duplicates, but we
re-check defensively in case staging/prod DBs differ.

Idempotent — safe to re-run.
"""

import sqlite3

MIGRATION_NAME = "010_phase1_constraints_and_indexes"
MIGRATION_DESCRIPTION = "Add 3 UNIQUE indexes + 6 composite perf indexes (Phase 1 #9, #10, #19)"


# (table, columns, index_name, kind)  kind=='UNIQUE' or 'INDEX'
INDEXES_TO_CREATE = [
    # --- A. UNIQUE constraints expressed as UNIQUE INDEX ---
    ("meal_plans",            ["property_id", "code"],         "uq_meal_plans_property_code",            "UNIQUE"),
    ("system_settings",       ["property_id", "setting_key"],  "uq_system_settings_property_key",        "UNIQUE"),
    ("ai_agent_permissions",  ["property_id", "role"],         "uq_ai_agent_permissions_property_role",  "UNIQUE"),
    # --- B. Composite performance indexes ---
    ("email_log",             ["reserva_id", "status", "sent_at"],  "idx_email_log_reserva_status_sent",  "INDEX"),
    ("transaccion",           ["reserva_id", "voided"],             "idx_transaccion_reserva_voided",     "INDEX"),
    ("consumo",               ["reserva_id", "voided"],             "idx_consumo_reserva_voided",         "INDEX"),
    ("room_status_log",       ["room_id", "changed_at"],            "idx_room_status_log_room_changed",   "INDEX"),
    ("ajuste_inventario",     ["producto_id", "created_at"],        "idx_ajuste_producto_created",        "INDEX"),
    ("producto",              ["property_id", "is_active"],         "idx_producto_property_active",       "INDEX"),
]


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


def _check_no_duplicates(cursor, table, columns):
    """Return list of duplicate rows that would block a UNIQUE index. Empty == clean."""
    col_list = ", ".join(columns)
    cursor.execute(
        f"SELECT {col_list}, COUNT(*) AS cnt FROM {table} "
        f"GROUP BY {col_list} HAVING cnt > 1"
    )
    return cursor.fetchall()


def run(conn: sqlite3.Connection):
    """Apply migration 010. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- Pre-flight: verify no duplicates would block the new UNIQUE indexes ---
    duplicate_blockers = []
    for table, columns, index_name, kind in INDEXES_TO_CREATE:
        if kind != "UNIQUE":
            continue
        if not _table_exists(cursor, table):
            continue
        dupes = _check_no_duplicates(cursor, table, columns)
        if dupes:
            duplicate_blockers.append((table, columns, dupes))

    if duplicate_blockers:
        msgs = []
        for table, columns, dupes in duplicate_blockers:
            sample = "; ".join(str(d) for d in dupes[:3])
            msgs.append(
                f"  {table}({', '.join(columns)}): {len(dupes)} duplicate group(s). "
                f"Sample: {sample}"
            )
        raise RuntimeError(
            "Migration 010 ABORT: duplicate rows would block UNIQUE constraints:\n"
            + "\n".join(msgs)
            + "\nDe-duplicate before re-running this migration."
        )

    # --- Create indexes (idempotent via IF NOT EXISTS + sqlite_master check) ---
    created = 0
    skipped = 0
    for table, columns, index_name, kind in INDEXES_TO_CREATE:
        if not _table_exists(cursor, table):
            # Should not happen — every referenced table exists by migration 008.
            # If it does (fresh DB without init_db run), skip silently.
            skipped += 1
            continue

        if _index_exists(cursor, index_name):
            skipped += 1
            continue

        unique_kw = "UNIQUE " if kind == "UNIQUE" else ""
        col_list = ", ".join(columns)
        cursor.execute(
            f"CREATE {unique_kw}INDEX IF NOT EXISTS {index_name} ON {table} ({col_list})"
        )
        created += 1

    # No return value needed — run_migrations.py reports success based on no exception.
    # The created/skipped counts are visible via: PRAGMA index_list per table.
