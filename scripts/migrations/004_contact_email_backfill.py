"""
Migration 004: Backfill missing contact_email columns (schema drift fix)
==========================================================================

The `contact_email` column was added to `reservations` and `checkins` models
in an earlier feature commit (v1.2.0 — feat: add email field to reservations
and check-ins) but never shipped a matching migration. Local dev DBs were
re-seeded from the current model, but the staging VM's DB kept the older
schema → SQLAlchemy queries fail with `no such column: reservations.contact_email`
after pulling any code that SELECTs that column (which is all reservation
endpoints, via the ORM).

This migration is a pure backfill: it adds `contact_email TEXT NULL` to both
tables IF the column is missing. Dev databases where the column already
exists will no-op.

Idempotent: safe to run multiple times via run_migrations.py.
"""

import sqlite3

MIGRATION_NAME = "contact_email_backfill"
MIGRATION_DESCRIPTION = "Add contact_email to reservations and checkins (schema drift fix)"


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _add_if_missing(cursor, table, column_name, column_def):
    if _column_exists(cursor, table, column_name):
        return 0
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
    return 1


def run(conn: sqlite3.Connection):
    """Apply migration 004. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()
    _add_if_missing(cursor, "reservations", "contact_email", "TEXT")
    _add_if_missing(cursor, "checkins", "contact_email", "TEXT")
