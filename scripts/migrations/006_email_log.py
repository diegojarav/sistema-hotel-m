"""
Migration 006: Email log (v1.8.0 — Phase 5)
============================================

Adds support for sending reservation-confirmation emails to guests and
auditing every attempt.

Changes
-------
1. `email_log` table (NEW) — append-only audit trail of outbound emails.
   One row per send attempt, linked to a reservation. Captures recipient,
   subject, status (ENVIADO | FALLIDO | PENDIENTE), error_message when
   status=FALLIDO, sent_at (set when leaving PENDIENTE), sent_by (user FK).

2. Indexes on (reserva_id), (status), (sent_at) for historial queries and
   the per-reservation rate-limit window (3/hour, counts only ENVIADO).

No schema changes to other tables. `reservations.contact_email` already
exists (database.py:133) so no ALTER there.

SMTP config is stored in `system_settings` (key/value) — not a new table.
Keys added by the UI at runtime: `smtp_host`, `smtp_port`, `smtp_username`,
`smtp_password_encrypted`, `smtp_from_name`, `smtp_from_email`,
`smtp_enabled`, `email_body_template`.

Idempotent — safe to re-run. Uses `sqlite_master` / `index_list` to skip
operations that have already been applied.
"""

import sqlite3

MIGRATION_NAME = "006_email_log"
MIGRATION_DESCRIPTION = "Add email_log table + indexes (Phase 5)"


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, table, index_name):
    cursor.execute(f"PRAGMA index_list({table})")
    return any(row[1] == index_name for row in cursor.fetchall())


def run(conn: sqlite3.Connection):
    """Apply migration 006. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. email_log table ---------------------------------------------
    if not _table_exists(cursor, "email_log"):
        cursor.execute(
            """
            CREATE TABLE email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reserva_id VARCHAR NOT NULL,
                recipient_email VARCHAR NOT NULL,
                subject VARCHAR NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'PENDIENTE',
                error_message VARCHAR,
                sent_at DATETIME,
                sent_by VARCHAR,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reserva_id) REFERENCES reservations (id),
                FOREIGN KEY (sent_by) REFERENCES users (id)
            )
            """
        )

    # --- 2. Indexes -----------------------------------------------------
    # Rate-limit query filters by reserva_id + sent_at + status=ENVIADO.
    # Historial query orders by sent_at DESC within a reserva_id.
    if not _index_exists(cursor, "email_log", "idx_email_log_reserva"):
        cursor.execute(
            "CREATE INDEX idx_email_log_reserva ON email_log (reserva_id)"
        )
    if not _index_exists(cursor, "email_log", "idx_email_log_status"):
        cursor.execute(
            "CREATE INDEX idx_email_log_status ON email_log (status)"
        )
    if not _index_exists(cursor, "email_log", "idx_email_log_sent_at"):
        cursor.execute(
            "CREATE INDEX idx_email_log_sent_at ON email_log (sent_at)"
        )
