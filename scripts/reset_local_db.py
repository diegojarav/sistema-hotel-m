#!/usr/bin/env python3
"""
Reset local hotel.db: delete, recreate schema, seed with test data.

Usage:
    python scripts/reset_local_db.py

This is a convenience wrapper that:
1. Deletes the existing hotel.db (if any)
2. Calls init_db() to create the schema
3. Calls seed_monges.run_seed() to populate test data
"""
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "backend" / "hotel.db"

# Fix Windows console encoding (seed script uses emoji characters)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root and backend dir are in sys.path for imports
# backend/ needed because database.py uses `from logging_config import ...`
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

def main():
    print("=== Resetting local database ===")

    # Step 1: Delete existing DB
    for suffix in ["", "-wal", "-shm"]:
        f = Path(str(DB_PATH) + suffix)
        if f.exists():
            f.unlink()
            print(f"  Deleted {f.name}")

    # Step 2: Create schema
    from backend.database import init_db
    init_db()
    print("  Schema created")

    # Step 3: Seed data
    from scripts.seed_monges import run_seed
    success = run_seed(DB_PATH, dry_run=False, reset=False)
    if success:
        # Flush WAL to get accurate file size
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        size_kb = DB_PATH.stat().st_size / 1024
        print(f"\n  Database ready: {size_kb:.0f} KB")
        print("  Run 'npm run dev:backend' to start the API server")
    else:
        print("\n  ERROR: Seeding failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
