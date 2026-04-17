"""
Migration 002: Channel Manager v2 (v1.5.0 — Phase 2)
========================================================

1. Extends `ical_feeds`: last_sync_status, last_sync_error,
   consecutive_failures, last_sync_attempted_at
2. Extends `reservations`: ota_booking_id, needs_review, review_reason
3. Creates new `ical_sync_log` audit table
4. Seeds existing feeds with last_sync_status='OK' if they had a prior sync

Idempotent: safe to run multiple times via run_migrations.py.
"""

import sqlite3

MIGRATION_NAME = "ical_v2"
MIGRATION_DESCRIPTION = "v1.5.0 — Channel Manager upgrade (per-feed health + sync log + cancellation detection)"


def _table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_column_if_missing(cursor, table, column_name, column_def):
    if _column_exists(cursor, table, column_name):
        return 0
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
    return 1


def _extend_ical_feeds(cursor):
    n = 0
    n += _add_column_if_missing(
        cursor, "ical_feeds", "last_sync_status",
        "TEXT NOT NULL DEFAULT 'NEVER'",
    )
    n += _add_column_if_missing(cursor, "ical_feeds", "last_sync_error", "TEXT")
    n += _add_column_if_missing(
        cursor, "ical_feeds", "consecutive_failures",
        "INTEGER NOT NULL DEFAULT 0",
    )
    n += _add_column_if_missing(
        cursor, "ical_feeds", "last_sync_attempted_at", "DATETIME"
    )
    if n:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ical_feeds_status "
            "ON ical_feeds(last_sync_status)"
        )
    return n


def _extend_reservations(cursor):
    n = 0
    n += _add_column_if_missing(cursor, "reservations", "ota_booking_id", "TEXT")
    n += _add_column_if_missing(
        cursor, "reservations", "needs_review",
        "BOOLEAN NOT NULL DEFAULT 0",
    )
    n += _add_column_if_missing(cursor, "reservations", "review_reason", "TEXT")
    if n:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reservations_needs_review "
            "ON reservations(needs_review)"
        )
    return n


def _create_ical_sync_log(cursor):
    if _table_exists(cursor, "ical_sync_log"):
        return 0
    cursor.execute("""
        CREATE TABLE ical_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL,
            attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            created_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            flagged_for_review_count INTEGER NOT NULL DEFAULT 0,
            conflicts_detected INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (feed_id) REFERENCES ical_feeds(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX idx_ical_sync_log_feed_id ON ical_sync_log(feed_id)"
    )
    cursor.execute(
        "CREATE INDEX idx_ical_sync_log_attempted_at "
        "ON ical_sync_log(attempted_at)"
    )
    return 1


def _seed_existing_feed_status(cursor):
    cursor.execute(
        "UPDATE ical_feeds SET last_sync_status='OK' "
        "WHERE last_sync_status='NEVER' AND last_synced_at IS NOT NULL"
    )
    return cursor.rowcount


def run(conn: sqlite3.Connection):
    """Apply migration 002. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()
    _extend_ical_feeds(cursor)
    _extend_reservations(cursor)
    _create_ical_sync_log(cursor)
    _seed_existing_feed_status(cursor)
