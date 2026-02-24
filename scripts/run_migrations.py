#!/usr/bin/env python3
"""
Hotel Munich PMS - Database Migration Runner
===============================================

Scans scripts/migrations/ for numbered Python migration files,
checks migration_history table, and runs only unapplied migrations.

Each migration file must define:
    MIGRATION_NAME = "descriptive_name"
    MIGRATION_DESCRIPTION = "What this migration does"

    def run(conn: sqlite3.Connection):
        '''Execute the migration SQL.'''
        conn.execute("ALTER TABLE ...")

Usage:
    python scripts/run_migrations.py              # Run all pending migrations
    python scripts/run_migrations.py --dry-run    # Show what would run
    python scripts/run_migrations.py --status     # Show migration status

Safety:
    - Auto-backup before first migration runs
    - Each migration wrapped in a transaction
    - Rollback on any error
    - Safe to run multiple times (idempotent)
"""

import argparse
import importlib.util
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ============================================
# CONFIGURATION
# ============================================

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
MIGRATIONS_DIR = SCRIPT_DIR / "migrations"
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DB_PATH = BACKEND_DIR / "hotel.db"
BACKUP_DIR = BACKEND_DIR / "backups"


# ============================================
# LOGGING
# ============================================

def log(msg, level="INFO"):
    prefix = {"INFO": "[INFO]", "OK": "[ OK ]", "WARN": "[WARN]", "ERR": "[ERR ]", "SKIP": "[SKIP]"}
    print(f"  {prefix.get(level, '[????]')} {msg}")


# ============================================
# MIGRATION HISTORY TABLE
# ============================================

HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS migration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_by TEXT DEFAULT 'run_migrations.py',
    success INTEGER DEFAULT 1,
    UNIQUE(version, name)
)
"""


def ensure_history_table(conn):
    """Create migration_history table if it doesn't exist."""
    conn.execute(HISTORY_TABLE_SQL)
    conn.commit()


def is_applied(conn, version, name):
    """Check if a migration has already been applied."""
    cursor = conn.execute(
        "SELECT id FROM migration_history WHERE version = ? AND name = ? AND success = 1",
        (version, name)
    )
    return cursor.fetchone() is not None


def record_migration(conn, version, name, description):
    """Record a successful migration."""
    conn.execute(
        "INSERT INTO migration_history (version, name, description) VALUES (?, ?, ?)",
        (version, name, description)
    )
    conn.commit()


# ============================================
# MIGRATION DISCOVERY
# ============================================

def discover_migrations():
    """Find all migration files in the migrations directory."""
    if not MIGRATIONS_DIR.exists():
        return []

    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue

        # Extract version from filename (e.g., "001_initial.py" -> "001")
        version = f.stem.split("_")[0]
        if not version.isdigit():
            continue

        # Load the module to get metadata
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            name = getattr(module, "MIGRATION_NAME", f.stem)
            description = getattr(module, "MIGRATION_DESCRIPTION", "No description")
            run_func = getattr(module, "run", None)

            if run_func is None:
                log(f"Skipping {f.name}: no run() function defined", "WARN")
                continue

            migrations.append({
                "version": version,
                "name": name,
                "description": description,
                "filename": f.name,
                "run": run_func,
            })
        except Exception as e:
            log(f"Error loading {f.name}: {e}", "ERR")

    return migrations


# ============================================
# BACKUP
# ============================================

def create_pre_migration_backup():
    """Create a database backup before running migrations."""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"pre_migration_{timestamp}.db"

    try:
        source = sqlite3.connect(str(DB_PATH), timeout=30)
        dest = sqlite3.connect(str(backup_path))
        source.backup(dest)
        dest.close()
        source.close()

        size_mb = backup_path.stat().st_size / (1024 * 1024)
        log(f"Pre-migration backup: {backup_path.name} ({size_mb:.2f} MB)", "OK")
        return True
    except Exception as e:
        log(f"Backup failed: {e}", "ERR")
        return False


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    print()
    print("  HOTEL MUNICH — MIGRATION RUNNER")
    print()

    if not DB_PATH.exists():
        log(f"Database not found at {DB_PATH}", "ERR")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    ensure_history_table(conn)

    # Discover migrations
    migrations = discover_migrations()
    if not migrations:
        log("No migration files found in scripts/migrations/", "INFO")
        conn.close()
        return

    # Check which are pending
    pending = []
    for m in migrations:
        applied = is_applied(conn, m["version"], m["name"])
        status = "APPLIED" if applied else "PENDING"

        if args.status:
            log(f"{m['version']} | {m['name']} | {status}")

        if not applied:
            pending.append(m)

    if args.status:
        print()
        log(f"Total: {len(migrations)} migrations, {len(pending)} pending")
        conn.close()
        return

    if not pending:
        log("All migrations are up to date", "OK")
        conn.close()
        return

    log(f"Found {len(pending)} pending migration(s)")

    if args.dry_run:
        for m in pending:
            log(f"Would run: {m['filename']} — {m['description']}")
        conn.close()
        return

    # Backup before running
    if not create_pre_migration_backup():
        log("Cannot proceed without backup. Aborting.", "ERR")
        conn.close()
        sys.exit(1)

    # Run pending migrations
    for m in pending:
        log(f"Running: {m['filename']} — {m['description']}")

        try:
            # Run in a savepoint for safety
            conn.execute("BEGIN")
            m["run"](conn)
            record_migration(conn, m["version"], m["name"], m["description"])
            conn.commit()
            log(f"Migration {m['version']} applied successfully", "OK")

        except Exception as e:
            conn.rollback()
            log(f"Migration {m['version']} FAILED: {e}", "ERR")
            log("Rolled back. Fix the issue and retry.", "ERR")
            conn.close()
            sys.exit(1)

    conn.close()
    print()
    log(f"All {len(pending)} migration(s) applied successfully", "OK")
    print()


if __name__ == "__main__":
    main()
