"""
Database Index Migration Script
================================
Adds indexes to existing tables for improved query performance (PERF-006).

Run from project root: python scripts/add_indexes.py
"""

import os
import sys
import sqlite3

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import DB_NAME

def add_indexes():
    """Add performance indexes to existing database."""

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    indexes = [
        # Reservation indexes (PERF-006)
        ("ix_reservations_status", "reservations", "status"),
        ("ix_reservations_check_in_date", "reservations", "check_in_date"),
        ("ix_reservations_room_id", "reservations", "room_id"),
        # Room indexes
        ("ix_rooms_property_id", "rooms", "property_id"),
        ("ix_rooms_status", "rooms", "status"),
    ]

    for idx_name, table, column in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
            print(f"[OK] Created index: {idx_name}")
        except sqlite3.Error as e:
            print(f"[FAIL] Failed to create {idx_name}: {e}")

    conn.commit()
    conn.close()
    print("\n[OK] Index migration complete!")

if __name__ == "__main__":
    print("Adding performance indexes to database...")
    print(f"Database: {DB_NAME}\n")
    add_indexes()
