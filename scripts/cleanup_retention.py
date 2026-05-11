#!/usr/bin/env python3
"""
Hotel Munich PMS — Retention Cleanup
======================================

Idempotent maintenance job that prunes old rows from append-only tables.
Run manually or via cron:

    python scripts/cleanup_retention.py              # prune with defaults
    python scripts/cleanup_retention.py --dry-run    # report counts, change nothing
    python scripts/cleanup_retention.py --price-days 60 --session-days 180

Rules (Phase 2b):

  price_calculations
    DELETE WHERE reservation_id IS NULL
              AND calculated_at < now - PRICE_DAYS (default 90)

    Rationale: rows attached to a real reservation are kept for audit
    history (the price snapshot is referenced from the reservation). Rows
    without `reservation_id` are pricing previews / calculator hits — only
    useful as recent diagnostics, not historical record.

  session_logs
    DELETE WHERE login_time < now - SESSION_DAYS (default 365)

    Rationale: session logs are audit/debug only. 1 year is long enough to
    investigate any reasonable security incident; beyond that they're noise.

Both rules run inside a single transaction. The script exits 0 on success,
non-zero on any error. No-op if both prune queries match zero rows.

Logging goes to stdout + the project logger (which fires Discord alerts
on ERROR level — but the cleanup only logs INFO, so a successful prune
doesn't notify anyone).

To install as a periodic job, add to crontab or Task Scheduler:

    # Cron: every Sunday at 03:00
    0 3 * * 0  cd /path/to/hotel-pms && python scripts/cleanup_retention.py

    # Or via the deploy_staging.sh "remote" cron if you want it on the VM.

Idempotent — safe to run on every schedule tick.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ============================================
# CONFIGURATION
# ============================================

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DB_PATH = BACKEND_DIR / "hotel.db"


DEFAULT_PRICE_DAYS = 90
DEFAULT_SESSION_DAYS = 365


def _log(level: str, msg: str) -> None:
    """Project-style log line. Uses stdlib (no project deps) so the script
    can run standalone on a fresh VM with just Python installed."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} | {level:8s} | retention | {msg}")


def _count_price_calculations_to_prune(conn: sqlite3.Connection, cutoff: datetime) -> int:
    cursor = conn.cursor()
    return cursor.execute(
        "SELECT COUNT(*) FROM price_calculations "
        "WHERE reservation_id IS NULL "
        "AND calculated_at IS NOT NULL "
        "AND calculated_at < ?",
        (cutoff.isoformat(),),
    ).fetchone()[0]


def _count_session_logs_to_prune(conn: sqlite3.Connection, cutoff: datetime) -> int:
    cursor = conn.cursor()
    return cursor.execute(
        "SELECT COUNT(*) FROM session_logs "
        "WHERE login_time IS NOT NULL "
        "AND login_time < ?",
        (cutoff.isoformat(),),
    ).fetchone()[0]


def _prune_price_calculations(
    conn: sqlite3.Connection, cutoff: datetime, dry_run: bool
) -> int:
    count = _count_price_calculations_to_prune(conn, cutoff)
    if count == 0:
        _log("INFO", "price_calculations: nothing to prune")
        return 0
    if dry_run:
        _log("INFO", f"price_calculations: would prune {count} row(s) [dry-run]")
        return count
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM price_calculations "
        "WHERE reservation_id IS NULL "
        "AND calculated_at IS NOT NULL "
        "AND calculated_at < ?",
        (cutoff.isoformat(),),
    )
    deleted = cursor.rowcount
    _log("INFO", f"price_calculations: pruned {deleted} row(s) older than {cutoff.date()}")
    return deleted


def _prune_session_logs(
    conn: sqlite3.Connection, cutoff: datetime, dry_run: bool
) -> int:
    count = _count_session_logs_to_prune(conn, cutoff)
    if count == 0:
        _log("INFO", "session_logs: nothing to prune")
        return 0
    if dry_run:
        _log("INFO", f"session_logs: would prune {count} row(s) [dry-run]")
        return count
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM session_logs "
        "WHERE login_time IS NOT NULL "
        "AND login_time < ?",
        (cutoff.isoformat(),),
    )
    deleted = cursor.rowcount
    _log("INFO", f"session_logs: pruned {deleted} row(s) older than {cutoff.date()}")
    return deleted


def run(
    db_path: Path = DB_PATH,
    price_days: int = DEFAULT_PRICE_DAYS,
    session_days: int = DEFAULT_SESSION_DAYS,
    dry_run: bool = False,
) -> int:
    """Run the retention cleanup. Returns total rows pruned (or would-be-pruned)."""
    if not db_path.exists():
        _log("ERROR", f"Database not found at {db_path}")
        return -1

    now = datetime.now()
    price_cutoff = now - timedelta(days=price_days)
    session_cutoff = now - timedelta(days=session_days)

    _log(
        "INFO",
        f"Starting retention pass (price_days={price_days}, session_days={session_days}, "
        f"dry_run={dry_run})",
    )

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN")
        total = 0
        total += _prune_price_calculations(conn, price_cutoff, dry_run)
        total += _prune_session_logs(conn, session_cutoff, dry_run)
        if dry_run:
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
        _log("INFO", f"Retention pass complete — {total} row(s) {'would be ' if dry_run else ''}pruned")
        return total
    except Exception as e:
        conn.execute("ROLLBACK")
        _log("ERROR", f"Retention pass FAILED: {e}")
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prune old append-only data (price_calculations, session_logs)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be deleted but make no changes",
    )
    parser.add_argument(
        "--price-days",
        type=int,
        default=DEFAULT_PRICE_DAYS,
        help=f"Prune price_calculations.reservation_id IS NULL older than N days (default: {DEFAULT_PRICE_DAYS})",
    )
    parser.add_argument(
        "--session-days",
        type=int,
        default=DEFAULT_SESSION_DAYS,
        help=f"Prune session_logs older than N days (default: {DEFAULT_SESSION_DAYS})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to hotel.db (default: {DB_PATH})",
    )
    args = parser.parse_args()

    try:
        run(
            db_path=args.db,
            price_days=args.price_days,
            session_days=args.session_days,
            dry_run=args.dry_run,
        )
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
