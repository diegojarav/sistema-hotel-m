"""
Migration 009: Fix email_log.sent_by type mismatch (v1.10.0 — Phase 1 Fix #2)
==============================================================================

`email_log.sent_by` was declared `Column(String)` but references `users.id`
which is `Integer`. SQLite tolerates the type mismatch (it stores values
dynamically), so existing rows hold values like `'1'` (numeric string).
PostgreSQL refuses to create a FK across mismatched types, so this must be
fixed BEFORE the Postgres migration.

Strategy
--------
SQLite cannot `ALTER TABLE ... ALTER COLUMN type`. The portable fix is the
table-rebuild dance:
  1. Verify every existing `sent_by` value is integer-castable (numeric or NULL).
     If a non-numeric value is found, abort and report — manual review needed.
  2. Recreate `email_log` with `sent_by INTEGER` + proper `FOREIGN KEY → users(id)`.
  3. Copy all rows, CAST(sent_by AS INTEGER).
  4. Drop the old table, rename the new one, recreate the indexes.

Idempotent — safe to re-run. Detects the already-fixed schema via PRAGMA
table_info and short-circuits.

Note: foreign_keys must be temporarily disabled during the table rebuild,
because the rebuild renames `email_log_new` → `email_log` and SQLite would
otherwise try to validate FKs from `transaccion`/`consumo`/etc. against the
intermediate table state. The `set_sqlite_pragma` listener (Fix #16) will
re-enable FKs on the next connection from the engine.
"""

import sqlite3

MIGRATION_NAME = "009_fix_email_log_sent_by"
MIGRATION_DESCRIPTION = "Convert email_log.sent_by from String to Integer FK to users.id (Phase 1 Fix #2)"


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _column_type(cursor, table, column):
    """Return the declared type of a column, or None if the column doesn't exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    for row in cursor.fetchall():
        if row[1] == column:
            return (row[2] or "").upper()
    return None


def _validate_sent_by_is_castable(cursor):
    """Return list of (rowid, value) for sent_by entries that are not int-castable.

    NULL is acceptable. Numeric strings like '1', '42' are acceptable. Anything
    else (e.g. 'admin', 'system') would silently lose information on CAST.
    """
    bad = []
    rows = cursor.execute(
        "SELECT rowid, sent_by FROM email_log WHERE sent_by IS NOT NULL"
    ).fetchall()
    for rowid, value in rows:
        try:
            int(str(value).strip())
        except (TypeError, ValueError):
            bad.append((rowid, value))
    return bad


def run(conn: sqlite3.Connection):
    """Apply migration 009. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # Idempotency: if the column is already INTEGER, skip.
    current_type = _column_type(cursor, "email_log", "sent_by")
    if current_type is None:
        # Table doesn't exist yet — Migration 006 hasn't run. Nothing to do here.
        return
    if "INT" in current_type:
        # Already fixed (INTEGER / INT). Idempotent skip.
        return

    # Pre-flight: every existing value must be int-castable.
    bad_rows = _validate_sent_by_is_castable(cursor)
    if bad_rows:
        sample = ", ".join(f"rowid={r}: {v!r}" for r, v in bad_rows[:5])
        raise RuntimeError(
            f"Migration 009 ABORT: email_log.sent_by has {len(bad_rows)} value(s) "
            f"that cannot be cast to INTEGER. Sample: {sample}. "
            "Manual review required — these rows may have been written by a code "
            "path that stored a non-id string. Resolve before re-running this migration."
        )

    # Disable FK enforcement during the rebuild. Other tables reference email_log
    # transitively (none directly today, but keep this defensive). The SQLite
    # connection used by run_migrations.py is independent of the SQLAlchemy
    # engine so toggling this here does not affect the application.
    cursor.execute("PRAGMA foreign_keys = OFF")

    # Build the new table with the corrected schema. Match the SQLAlchemy model
    # (database.py:EmailLog) byte-for-byte, including the index columns.
    cursor.execute(
        """
        CREATE TABLE email_log_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reserva_id VARCHAR NOT NULL,
            recipient_email VARCHAR NOT NULL,
            subject VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'PENDIENTE',
            error_message VARCHAR,
            sent_at DATETIME,
            sent_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reserva_id) REFERENCES reservations (id),
            FOREIGN KEY (sent_by) REFERENCES users (id)
        )
        """
    )

    # Copy data, casting sent_by. NULL stays NULL.
    cursor.execute(
        """
        INSERT INTO email_log_new (
            id, reserva_id, recipient_email, subject, status,
            error_message, sent_at, sent_by, created_at
        )
        SELECT
            id, reserva_id, recipient_email, subject, status,
            error_message, sent_at,
            CASE WHEN sent_by IS NULL THEN NULL ELSE CAST(sent_by AS INTEGER) END,
            created_at
        FROM email_log
        """
    )

    # Swap.
    cursor.execute("DROP TABLE email_log")
    cursor.execute("ALTER TABLE email_log_new RENAME TO email_log")

    # Recreate indexes (must mirror migration 006 exactly).
    cursor.execute("CREATE INDEX idx_email_log_reserva ON email_log (reserva_id)")
    cursor.execute("CREATE INDEX idx_email_log_status ON email_log (status)")
    cursor.execute("CREATE INDEX idx_email_log_sent_at ON email_log (sent_at)")

    # Re-enable FK enforcement. The application's connection (via SQLAlchemy
    # engine listener) sets this on every connect, but be explicit for the
    # migration runner's session too.
    cursor.execute("PRAGMA foreign_keys = ON")
