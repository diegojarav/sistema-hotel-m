"""
Migration 016: Multi-vehicle per reservation (v1.10.0 — Phase 2c)
==================================================================

Adds the `reservation_vehicles` table so a single booking can carry MORE
THAN ONE vehicle.  Two modes are supported per row:

  1. **Linked**  — `guest_vehicle_id` points at a row in `guest_vehicles`
                  (master catalogue). Used when the booker's own car was
                  picked from a dropdown of their registered vehicles.

  2. **Quick-add** — `guest_vehicle_id IS NULL`; plate/model/color are the
                    SOURCE OF TRUTH for this companion vehicle. Used when a
                    second car arrives at 2 AM and there's no time to
                    create a Guest record for the driver.

Snapshot fields (plate_number/model/color) are ALWAYS stored, including
for linked rows, so the reservation page can render the vehicle list
without joining and so the future plate-recognition pipeline can scan
this table by plate alone.

The pre-existing `reservations.vehicle_plate` / `reservations.vehicle_model`
columns are PRESERVED unchanged (back-compat).  When a multi-vehicle
reservation lands, the first vehicle (or the row with `is_primary=1`)
also writes its plate/model into those legacy columns so all the older
code paths that read them continue to work without any modification.

`guest_vehicles` is NOT modified by this migration. Quick-add companion
vehicles deliberately do NOT pollute the master catalogue — that table
keeps the invariant "every row has an owner".  If the operator later
decides a companion vehicle should be promoted to a master Guest's
catalogue, an admin tool can copy the snapshot fields over (future).

Idempotent — safe to re-run.  Re-runs detect the table existence and
skip creation; index creation is also guarded.
"""
from __future__ import annotations

import sqlite3

MIGRATION_NAME = "016_reservation_vehicles"
MIGRATION_DESCRIPTION = (
    "Create reservation_vehicles table for multi-vehicle bookings "
    "(linked or quick-add) (Phase 2c)"
)


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, index_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


def run(conn: sqlite3.Connection):
    """Apply migration 016. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. Create reservation_vehicles table (idempotent) ---
    if not _table_exists(cursor, "reservation_vehicles"):
        cursor.execute(
            """
            CREATE TABLE reservation_vehicles (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id     VARCHAR NOT NULL,
                guest_vehicle_id   INTEGER,
                plate_number       VARCHAR NOT NULL,
                model              VARCHAR,
                color              VARCHAR,
                is_primary         BOOLEAN NOT NULL DEFAULT 0,
                notes              VARCHAR,
                created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reservation_id) REFERENCES reservations (id) ON DELETE CASCADE,
                FOREIGN KEY (guest_vehicle_id) REFERENCES guest_vehicles (id) ON DELETE SET NULL
            )
            """
        )

    # --- 2. Indexes (mirror the model's __table_args__) ---
    for idx_name, cols in (
        # Lookup by reservation (rendering vehicle list in detail view)
        ("idx_resv_veh_reservation", "reservation_id"),
        # Lookup by plate (future OCR + "whose car is this?" — also used by
        # GuestVehicleService.search_by_plate which now extends to this table)
        ("idx_resv_veh_plate", "plate_number"),
        # Optional FK lookup
        ("idx_resv_veh_guest_vehicle", "guest_vehicle_id"),
    ):
        if not _index_exists(cursor, idx_name):
            cursor.execute(
                f"CREATE INDEX {idx_name} ON reservation_vehicles ({cols})"
            )

    # No auto-population step — pre-existing reservations keep using the
    # legacy reservations.vehicle_plate / vehicle_model columns. New
    # multi-vehicle bookings will populate reservation_vehicles. Existing
    # single-vehicle code paths are unaffected.
