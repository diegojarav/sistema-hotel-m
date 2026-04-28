"""
Migration 013: Guest domain extension (v1.10.0 — Phase 2a-ext)
================================================================

Adds three pieces that complete the guest domain:

  1. `guests.birth_date` — Date column on master Guest. Hook for the future
     birthday-greeting automation (see ROADMAP.md backlog).

  2. `billing_profiles` (NEW table) — reusable invoice profiles per Guest.
     Replaces the per-stay snapshots `checkins.billing_name` /
     `checkins.billing_ruc` as the LIVING source. The legacy columns stay as
     the frozen-at-registration record (snapshot pattern).

  3. `guest_vehicles` (NEW table) — vehicles registered to a Guest, max 5
     per guest (enforced at service layer). Powers the "whose car is this?"
     lookup AND the future OCR pipeline at the entrance gate.

  4. `checkin_vehicles` (NEW table) — N:M between checkins and vehicles
     with per-stay parking metadata (parking_spot, key_deposited).

  5. `checkins.billing_profile_id` — nullable FK pointing at the profile
     selected for this stay.

Auto-population from legacy data
---------------------------------
- BillingProfiles: for each unique (guest_id, billing_name+billing_ruc) on
  checkins, create one BillingProfile and link the checkin to it. The
  first profile per guest becomes the default.
- GuestVehicles: for each unique (guest_id, vehicle_plate) on checkins,
  create one GuestVehicle. Then for each checkin with a vehicle, create
  a CheckinVehicle row linking them.

This means hotels that already use the ficha form for billing/vehicle data
get instant continuity — their existing data shows up as proper profiles
+ registered vehicles after migration.

Idempotent — safe to re-run. Re-runs detect the table existence and skip
the auto-population phase if any row exists.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Dict, Tuple

MIGRATION_NAME = "013_guest_domain_ext"
MIGRATION_DESCRIPTION = (
    "Add birth_date to guests + billing_profiles + guest_vehicles + checkin_vehicles "
    "+ migrate legacy billing/vehicle data from checkins (Phase 2a-ext)"
)


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _index_exists(cursor, index_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


def run(conn: sqlite3.Connection):
    """Apply migration 013. Called by run_migrations.py inside a transaction."""
    cursor = conn.cursor()

    # --- 1. Add guests.birth_date (idempotent) ---
    if not _column_exists(cursor, "guests", "birth_date"):
        cursor.execute("ALTER TABLE guests ADD COLUMN birth_date DATE")

    # --- 2. Create billing_profiles ---
    if not _table_exists(cursor, "billing_profiles"):
        cursor.execute(
            """
            CREATE TABLE billing_profiles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id        INTEGER NOT NULL,
                property_id     VARCHAR NOT NULL,
                label           VARCHAR,
                is_default      BOOLEAN DEFAULT 0,
                tax_id_type     VARCHAR,
                tax_id_number   VARCHAR,
                business_name   VARCHAR,
                address         VARCHAR,
                city            VARCHAR,
                state           VARCHAR,
                country         VARCHAR,
                is_active       BOOLEAN DEFAULT 1,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guest_id) REFERENCES guests (id) ON DELETE CASCADE,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
            """
        )

    for idx_name, cols in (
        ("idx_billing_guest_active",     "guest_id, is_active"),
        ("idx_billing_property",         "property_id"),
        ("idx_billing_property_tax_id",  "property_id, tax_id_number"),
    ):
        if not _index_exists(cursor, idx_name):
            cursor.execute(f"CREATE INDEX {idx_name} ON billing_profiles ({cols})")

    # --- 3. Create guest_vehicles ---
    if not _table_exists(cursor, "guest_vehicles"):
        cursor.execute(
            """
            CREATE TABLE guest_vehicles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id        INTEGER NOT NULL,
                property_id     VARCHAR NOT NULL,
                plate_number    VARCHAR NOT NULL,
                model           VARCHAR,
                color           VARCHAR,
                is_active       BOOLEAN DEFAULT 1,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guest_id) REFERENCES guests (id) ON DELETE CASCADE,
                FOREIGN KEY (property_id) REFERENCES properties (id)
            )
            """
        )

    for idx_name, cols in (
        ("idx_vehicle_guest",            "guest_id"),
        ("idx_vehicle_property_plate",   "property_id, plate_number"),
        ("idx_vehicle_guest_active",     "guest_id, is_active"),
    ):
        if not _index_exists(cursor, idx_name):
            cursor.execute(f"CREATE INDEX {idx_name} ON guest_vehicles ({cols})")

    # --- 4. Create checkin_vehicles (N:M) ---
    if not _table_exists(cursor, "checkin_vehicles"):
        cursor.execute(
            """
            CREATE TABLE checkin_vehicles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                checkin_id      INTEGER NOT NULL,
                vehicle_id      INTEGER NOT NULL,
                parking_spot    VARCHAR,
                key_deposited   BOOLEAN DEFAULT 0,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (checkin_id) REFERENCES checkins (id) ON DELETE CASCADE,
                FOREIGN KEY (vehicle_id) REFERENCES guest_vehicles (id) ON DELETE CASCADE,
                CONSTRAINT uq_checkin_vehicle UNIQUE (checkin_id, vehicle_id)
            )
            """
        )

    for idx_name, cols in (
        ("idx_checkin_vehicles_checkin", "checkin_id"),
        ("idx_checkin_vehicles_vehicle", "vehicle_id"),
    ):
        if not _index_exists(cursor, idx_name):
            cursor.execute(f"CREATE INDEX {idx_name} ON checkin_vehicles ({cols})")

    # --- 5. Add checkins.billing_profile_id ---
    if not _column_exists(cursor, "checkins", "billing_profile_id"):
        cursor.execute("ALTER TABLE checkins ADD COLUMN billing_profile_id INTEGER")
    if not _index_exists(cursor, "ix_checkins_billing_profile_id"):
        cursor.execute(
            "CREATE INDEX ix_checkins_billing_profile_id ON checkins (billing_profile_id)"
        )

    # --- 6. Auto-populate from legacy data (only if both target tables empty) ---
    cursor.execute("SELECT COUNT(*) FROM billing_profiles")
    bp_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM guest_vehicles")
    gv_count = cursor.fetchone()[0]
    if bp_count > 0 or gv_count > 0:
        # Already populated — re-run safety
        return

    # Default property fallback (single-tenant today).
    cursor.execute("SELECT id FROM properties LIMIT 1")
    prop_row = cursor.fetchone()
    default_property = prop_row[0] if prop_row else "los-monges"

    # ---- 6a. Billing profiles from checkin.billing_name + billing_ruc ----
    # Group by (guest_id, billing_name, billing_ruc). Skip rows where both are
    # blank (no useful info). guest_id NULL → skip (orphan checkin).
    cursor.execute(
        """
        SELECT id, guest_id, room_id, billing_name, billing_ruc
        FROM checkins
        WHERE guest_id IS NOT NULL
          AND (
            (billing_name IS NOT NULL AND TRIM(billing_name) != '')
            OR (billing_ruc IS NOT NULL AND TRIM(billing_ruc) != '')
          )
        """
    )
    legacy_billing_rows = cursor.fetchall()

    # Map: (guest_id, name, ruc) -> billing_profile_id
    bp_map: Dict[Tuple[int, str, str], int] = {}
    # Map: guest_id -> set of profile ids (to know which is "first" for default)
    guest_profile_count: Dict[int, int] = defaultdict(int)

    for ci_id, gid, room_id, name, ruc in legacy_billing_rows:
        name_norm = (name or "").strip()
        ruc_norm = (ruc or "").strip()
        key = (gid, name_norm, ruc_norm)

        if key not in bp_map:
            # Resolve property_id from the checkin's room (or fallback)
            prop_id = default_property
            if room_id:
                cursor.execute("SELECT property_id FROM rooms WHERE id = ?", (room_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    prop_id = row[0]

            is_default = 1 if guest_profile_count[gid] == 0 else 0
            cursor.execute(
                """
                INSERT INTO billing_profiles (
                    guest_id, property_id, label, is_default,
                    tax_id_type, tax_id_number, business_name,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    gid, prop_id,
                    None,
                    is_default,
                    "RUC" if ruc_norm else None,
                    ruc_norm or None,
                    name_norm or None,
                ),
            )
            bp_map[key] = cursor.lastrowid
            guest_profile_count[gid] += 1

        # Backfill checkin.billing_profile_id
        cursor.execute(
            "UPDATE checkins SET billing_profile_id = ? WHERE id = ?",
            (bp_map[key], ci_id),
        )

    # ---- 6b. Vehicles from checkin.vehicle_plate (+ model) ----
    # Group by (guest_id, plate). Skip blank plates.
    cursor.execute(
        """
        SELECT id, guest_id, room_id, vehicle_model, vehicle_plate
        FROM checkins
        WHERE guest_id IS NOT NULL
          AND vehicle_plate IS NOT NULL
          AND TRIM(vehicle_plate) != ''
        """
    )
    legacy_vehicle_rows = cursor.fetchall()

    # Map: (guest_id, normalized_plate) -> vehicle_id
    veh_map: Dict[Tuple[int, str], int] = {}
    # Track per-guest count for the 5-vehicle limit (in case legacy data exceeds it)
    guest_vehicle_count: Dict[int, int] = defaultdict(int)
    MAX = 5

    for ci_id, gid, room_id, model, plate in legacy_vehicle_rows:
        plate_norm = (plate or "").strip().upper()
        if not plate_norm:
            continue
        key = (gid, plate_norm)

        if key not in veh_map:
            if guest_vehicle_count[gid] >= MAX:
                # Skip — guest already at limit. The recepcionist can
                # re-register manually if needed; legacy excess is dropped
                # rather than failing the migration.
                continue

            prop_id = default_property
            if room_id:
                cursor.execute("SELECT property_id FROM rooms WHERE id = ?", (room_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    prop_id = row[0]

            cursor.execute(
                """
                INSERT INTO guest_vehicles (
                    guest_id, property_id, plate_number, model, is_active
                ) VALUES (?, ?, ?, ?, 1)
                """,
                (
                    gid, prop_id, plate_norm,
                    (model or "").strip() or None,
                ),
            )
            veh_map[key] = cursor.lastrowid
            guest_vehicle_count[gid] += 1

        # Link via checkin_vehicles (idempotent — UNIQUE constraint)
        try:
            cursor.execute(
                """
                INSERT INTO checkin_vehicles (
                    checkin_id, vehicle_id, key_deposited
                ) VALUES (?, ?, 0)
                """,
                (ci_id, veh_map[key]),
            )
        except sqlite3.IntegrityError:
            # Already linked — fine
            pass
