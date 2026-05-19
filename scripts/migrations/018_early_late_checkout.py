"""
Migration 018: Early check-in / late check-out (v1.10.0 — Phase 2e)
====================================================================

Adds boolean flags + optional time on the reservation row, plus surcharge
config on the property. Receptionists can mark a booking as "early check-in"
(guest arrives before the property's `check_in_start`) or "late check-out"
(guest stays past `check_out_time`), optionally storing the late-checkout
time the guest agreed to.

Scope (MVP — what this migration enables)
-----------------------------------------
- UI flags on the reservation form so the receptionist can note the
  request.
- Surcharge amounts configurable on the property — applied to total at
  checkout (or in a future pricing-modifier pass).

NOT scope yet (deferred to Phase 6.5)
-------------------------------------
- Availability blocking. A late-checkout-until-14:00 SHOULD block the
  next guest's same-day check-in at 14:00, but the availability engine
  isn't wired up to read these fields yet. This migration only stores
  the data — `ReservationService.create_reservations` does not consult
  it. The Phase 6.5 follow-up is to make the overlap check
  `check_in_date < r_end OR check_in_date == r.checkout_date AND
  check_in_time < r.late_checkout_time`.

Schema changes
--------------
On `reservations` (additive, all NULL-safe for legacy rows):
  early_checkin           BOOLEAN  default 0
  late_checkout           BOOLEAN  default 0
  late_checkout_time      TIME     nullable  ("HH:MM" or NULL = standard)

On `properties` (surcharge config, 0 = free which is the default):
  early_checkin_surcharge INTEGER  default 0  (base-currency units)
  late_checkout_surcharge INTEGER  default 0

Idempotent — safe to re-run.
"""
from __future__ import annotations

import sqlite3

MIGRATION_NAME = "018_early_late_checkout"
MIGRATION_DESCRIPTION = (
    "Add early_checkin / late_checkout flags + late_checkout_time on "
    "reservations, surcharge config on properties (Phase 2e MVP — availability "
    "blocking deferred to Phase 6.5)"
)


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def run(conn: sqlite3.Connection):
    cursor = conn.cursor()

    # ---- reservations: per-stay flags ----
    if not _column_exists(cursor, "reservations", "early_checkin"):
        cursor.execute(
            "ALTER TABLE reservations ADD COLUMN early_checkin BOOLEAN NOT NULL DEFAULT 0"
        )
    if not _column_exists(cursor, "reservations", "late_checkout"):
        cursor.execute(
            "ALTER TABLE reservations ADD COLUMN late_checkout BOOLEAN NOT NULL DEFAULT 0"
        )
    if not _column_exists(cursor, "reservations", "late_checkout_time"):
        # Stored as VARCHAR "HH:MM" for consistency with Property.check_*_time
        cursor.execute(
            "ALTER TABLE reservations ADD COLUMN late_checkout_time VARCHAR"
        )

    # ---- properties: surcharge config (in BASE currency units) ----
    if not _column_exists(cursor, "properties", "early_checkin_surcharge"):
        cursor.execute(
            "ALTER TABLE properties ADD COLUMN early_checkin_surcharge INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(cursor, "properties", "late_checkout_surcharge"):
        cursor.execute(
            "ALTER TABLE properties ADD COLUMN late_checkout_surcharge INTEGER NOT NULL DEFAULT 0"
        )

    # No data backfill — legacy rows default to early_checkin=0, late_checkout=0
    # (standard window). Surcharges default to 0 (free) until admin configures
    # them via the future Settings UI extension.
