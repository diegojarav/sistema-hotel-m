"""
Migration: Channel Manager v2 (v1.5.0 — Phase 2)
==================================================

Adds the database changes needed for the Channel Manager Upgrade:

1. Extends `ical_feeds`:
     - last_sync_status (TEXT, default 'NEVER')
     - last_sync_error (TEXT, nullable)
     - consecutive_failures (INTEGER, default 0)
     - last_sync_attempted_at (DATETIME, nullable)

2. Extends `reservations`:
     - ota_booking_id (TEXT, nullable)
     - needs_review (BOOLEAN, default 0)
     - review_reason (TEXT, nullable)

3. Creates new `ical_sync_log` table:
     - Audit trail of sync attempts (created_count, updated_count,
       flagged_for_review_count, conflicts_detected, error_message, duration_ms)
     - Pruned to last 100 entries per feed_id (in service code)

4. Seeds `last_sync_status='NEVER'` for existing feeds.

Idempotent: safe to run multiple times.

Usage:
    python scripts/migrate_ical_v2.py
"""

import sqlite3
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

DB_PATH = backend_path / "hotel.db"


def table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cursor.fetchone() is not None


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def add_column_if_missing(cursor, table, column_name, column_def):
    if column_exists(cursor, table, column_name):
        print(f"  [=] Column '{table}.{column_name}' already exists, skipping")
        return 0
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
    print(f"  [+] Added column '{table}.{column_name}'")
    return 1


def extend_ical_feeds(cursor):
    """Add health tracking columns to ical_feeds."""
    n = 0
    n += add_column_if_missing(cursor, "ical_feeds", "last_sync_status",
                                "TEXT NOT NULL DEFAULT 'NEVER'")
    n += add_column_if_missing(cursor, "ical_feeds", "last_sync_error", "TEXT")
    n += add_column_if_missing(cursor, "ical_feeds", "consecutive_failures",
                                "INTEGER NOT NULL DEFAULT 0")
    n += add_column_if_missing(cursor, "ical_feeds", "last_sync_attempted_at", "DATETIME")
    if n:
        # Index on last_sync_status for quick health filtering
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ical_feeds_status "
            "ON ical_feeds(last_sync_status)"
        )
        print("  [+] Created index 'idx_ical_feeds_status'")
    return n


def extend_reservations(cursor):
    """Add Channel Manager v2 fields to reservations."""
    n = 0
    n += add_column_if_missing(cursor, "reservations", "ota_booking_id", "TEXT")
    n += add_column_if_missing(cursor, "reservations", "needs_review",
                                "BOOLEAN NOT NULL DEFAULT 0")
    n += add_column_if_missing(cursor, "reservations", "review_reason", "TEXT")
    if n:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reservations_needs_review "
            "ON reservations(needs_review)"
        )
        print("  [+] Created index 'idx_reservations_needs_review'")
    return n


def create_ical_sync_log_table(cursor):
    """Create the ical_sync_log audit table."""
    if table_exists(cursor, "ical_sync_log"):
        print("  [=] Table 'ical_sync_log' already exists, skipping")
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
        "CREATE INDEX idx_ical_sync_log_attempted_at ON ical_sync_log(attempted_at)"
    )
    print("  [+] Created table 'ical_sync_log' with indexes")
    return 1


def seed_existing_feed_status(cursor):
    """Set last_sync_status='OK' for feeds that have last_synced_at populated."""
    cursor.execute(
        "UPDATE ical_feeds SET last_sync_status='OK' "
        "WHERE last_sync_status='NEVER' AND last_synced_at IS NOT NULL"
    )
    n = cursor.rowcount
    if n:
        print(f"  [+] Seeded {n} feed(s) with last_sync_status='OK'")
    return n


def migrate():
    if not DB_PATH.exists():
        print(f"[!] Database not found at: {DB_PATH}")
        print("    Run the app once to create the schema, then re-run.")
        sys.exit(1)

    print(f"Connecting to: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        print("\n[Step 1/4] Extending ical_feeds table...")
        n_feeds = extend_ical_feeds(cursor)

        print("\n[Step 2/4] Extending reservations table...")
        n_res = extend_reservations(cursor)

        print("\n[Step 3/4] Creating ical_sync_log table...")
        n_log = create_ical_sync_log_table(cursor)

        print("\n[Step 4/4] Seeding existing feed status...")
        n_seed = seed_existing_feed_status(cursor)

        conn.commit()

        # Verification
        print("\n[Verification]")
        cursor.execute("SELECT COUNT(*) FROM ical_feeds")
        feeds_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM ical_sync_log")
        logs_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM reservations WHERE needs_review = 1"
        )
        review_count = cursor.fetchone()[0]
        print(f"  ical_feeds rows: {feeds_count}")
        print(f"  ical_sync_log rows: {logs_count}")
        print(f"  reservations needing review: {review_count}")

        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY (v1.5.0 Phase 2)")
        print("=" * 60)
        print(f"  ical_feeds columns added: {n_feeds}")
        print(f"  reservations columns added: {n_res}")
        print(f"  ical_sync_log table created: {'yes' if n_log else 'no (already existed)'}")
        print(f"  Existing feeds seeded: {n_seed}")
        print("=" * 60)
        print("Migration completed successfully.")

    except sqlite3.Error as e:
        print(f"\n[!] Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRATION: Channel Manager v2 (v1.5.0 Phase 2)")
    print("=" * 60)
    migrate()
