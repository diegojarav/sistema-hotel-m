"""
Migration: Add reservation_id to checkins table
================================================

Adds a foreign key column to link check-ins to their corresponding reservations.
This enables the smart two-step flow where scanning a document during reservation
automatically creates a linked check-in record.

Changes:
- Adds `reservation_id` column to `checkins` table (nullable, indexed)
- Foreign key references `reservations.id`

Usage:
    python scripts/migrate_checkin_link.py
"""

import sqlite3
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

DB_PATH = backend_path / "hotel.db"


def migrate():
    """Add reservation_id column to checkins table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(checkins)")
        columns = [row[1] for row in cursor.fetchall()]

        if "reservation_id" in columns:
            print("✓ Column 'reservation_id' already exists in checkins table")
            return

        print("Adding reservation_id column to checkins table...")

        # SQLite doesn't support ADD COLUMN with FOREIGN KEY in one statement
        # We need to add the column first, then create an index
        cursor.execute("""
            ALTER TABLE checkins
            ADD COLUMN reservation_id TEXT
        """)

        # Create index for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_checkins_reservation_id
            ON checkins(reservation_id)
        """)

        conn.commit()
        print("✓ Migration completed successfully")
        print("  - Added reservation_id column (nullable)")
        print("  - Created index idx_checkins_reservation_id")

    except sqlite3.Error as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("MIGRATION: Add reservation_id to checkins")
    print("=" * 60)
    migrate()
    print("\nMigration complete. Check-ins can now be linked to reservations.")
