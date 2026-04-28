"""
Seed realistic test data for the guest flows (v1.10.0 — Phase 2a follow-up).
==============================================================================

Populates 10 guests with varied data quality (full data, no email, OTA-no-doc,
phone-only, repeat guest, special chars, corporate, dup-risk, international,
minimal). Each guest exercises a different code path:

  - 1 with all fields filled            → end-to-end happy path
  - 2 with no email                     → tests find_or_create email-tier skip
  - 3 OTA without document              → tests email-tier match
  - 4 phone only                        → ensures phone is NOT a match tier
  - 5 repeat guest with 3 reservations  → tests aggregates + history
  - 6 with special characters in name   → tests normalisation
  - 7 corporate                         → notes field used
  - 8 same lastname as another active   → tests Fix D duplicate warning
  - 9 international with passport       → document_type="Pasaporte"
  - 10 minimal (just name)              → edge case

Then materialises:
  - 3 reservations for guest #5 (Roberto Fernández) — repeat guest flow
  - 1 reservation + 1 checkin for guest #1 (María González) — full pipeline
  - 1 OTA reservation for guest #3 (Hans Müller) — no checkin yet

Usage:
  python scripts/seed_test_guests.py               # seed
  python scripts/seed_test_guests.py --reset       # delete previous test guests
                                                     and re-seed
  python scripts/seed_test_guests.py --dry-run     # report what would happen

The seeded rows are tagged with `notes='[test-seed]'` (or appended) so they
can be cleanly identified and removed by --reset.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

# Make sibling backend/ importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlalchemy import or_  # noqa: E402

from database import (  # noqa: E402
    CheckIn,
    Guest,
    Reservation,
    Room,
    SessionLocal,
)
from services.guest_service import GuestService  # noqa: E402

PROPERTY_ID = "los-monges"
TEST_TAG = "[test-seed]"


GUEST_RECIPES: List[Dict[str, Any]] = [
    # 1 — Complete guest
    {
        "first_name": "María",
        "last_name": "González",
        "document_number": "4521890",
        "email": "maria.gonzalez@gmail.com",
        "phone": "0981555123",
        "nationality": "Paraguaya",
        "country": "Paraguay",
        "city": "Asunción",
    },
    # 2 — No email (walk-in)
    {
        "first_name": "Carlos",
        "last_name": "Benítez",
        "document_number": "3298741",
        "phone": "0971444567",
    },
    # 3 — OTA, no document
    {
        "first_name": "Hans",
        "last_name": "Müller",
        "email": "hans.mueller@web.de",
        "source": "Booking.com",
        "nationality": "Alemana",
        "country": "Alemania",
        "city": "Berlin",
    },
    # 4 — Phone only
    {
        "first_name": "Ana",
        "last_name": "López",
        "phone": "0982333222",
    },
    # 5 — Repeat guest
    {
        "first_name": "Roberto",
        "last_name": "Fernández",
        "document_number": "5123456",
        "email": "rfernandez@hotmail.com",
        "phone": "0991777888",
        "nationality": "Brasilera",
        "country": "Brasil",
        "city": "Foz do Iguazú",
    },
    # 6 — Special characters
    {
        "first_name": "José María",
        "last_name": "O'Brien Martínez",
        "document_number": "7890123",
    },
    # 7 — Corporate
    {
        "first_name": "Lucía",
        "last_name": "Ramírez",
        "document_number": "6543210",
        "email": "lucia@empresaxyz.com.py",
        "phone": "021555000",
        "notes": "Empresa XYZ - Tarifa corporativa",
    },
    # 8 — Same lastname (will trigger Fix D dup-warning)
    {
        "first_name": "Marcos",
        "last_name": "Barrios",
        "document_number": "9999999",
        "email": "marcos.barrios.nuevo@gmail.com",
    },
    # 9 — International with passport
    {
        "first_name": "Sarah",
        "last_name": "Johnson",
        "document_type": "Pasaporte",
        "document_number": "US789456123",
        "email": "sarah.j@yahoo.com",
        "nationality": "Estadounidense",
        "country": "Estados Unidos",
        "city": "Miami",
    },
    # 10 — Minimal (just name)
    {
        "first_name": "Pedro",
        "last_name": "Desconocido",
    },
]


def _tag_notes(extra: str | None) -> str:
    return f"{TEST_TAG} {extra}".strip() if extra else TEST_TAG


def _next_reservation_id(db) -> str:
    last = db.query(Reservation).order_by(Reservation.id.desc()).first()
    try:
        n = int(last.id) + 1 if last else 999900
    except Exception:
        n = 999900
    return f"{n:07d}"


def _pick_room(db) -> Room | None:
    return (
        db.query(Room)
        .filter(Room.property_id == PROPERTY_ID, Room.active == 1)
        .order_by(Room.id)
        .first()
    )


# ----------------------------------------------------------------------
# Reset helpers
# ----------------------------------------------------------------------

def _reset_test_data(db) -> None:
    """Hard-delete every row tagged TEST_TAG. Cascade to dependent rows
    via the natural FKs (reservations.guest_id is SET NULL, but we delete
    the guest's reservations explicitly to avoid orphan snapshots)."""
    test_guests = (
        db.query(Guest)
        .filter(Guest.notes.like(f"%{TEST_TAG}%"))
        .all()
    )
    if not test_guests:
        print(f"[INFO] No previous test data found.")
        return
    ids = [g.id for g in test_guests]
    print(f"[INFO] Removing {len(ids)} previous test guest(s).")

    # Reservations + checkins linked to test guests
    n_res = (
        db.query(Reservation)
        .filter(Reservation.guest_id.in_(ids))
        .delete(synchronize_session=False)
    )
    n_ci = (
        db.query(CheckIn)
        .filter(CheckIn.guest_id.in_(ids))
        .delete(synchronize_session=False)
    )
    n_g = (
        db.query(Guest)
        .filter(Guest.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    print(f"[INFO] Deleted: {n_g} guests, {n_res} reservations, {n_ci} checkins.")


# ----------------------------------------------------------------------
# Main seeding
# ----------------------------------------------------------------------

def _seed_guests(db) -> List[Guest]:
    """Create the 10 recipe guests via GuestService.create_guest."""
    created: List[Guest] = []
    for recipe in GUEST_RECIPES:
        data = dict(recipe)
        data["notes"] = _tag_notes(data.get("notes"))
        g = GuestService.create_guest(db=db, property_id=PROPERTY_ID, data=data)
        created.append(g)
        print(f"  [+] Guest #{g.id}  {g.last_name}, {g.first_name}")
    return created


def _seed_reservations_and_checkins(db, guests: List[Guest]) -> tuple[int, int]:
    """Create the historical reservations + checkins per the recipes."""
    by_lastname = {g.last_name: g for g in guests}

    room = _pick_room(db)
    if not room:
        print("[WARN] No active rooms found; skipping reservations.")
        return 0, 0

    res_count = 0
    ci_count = 0

    # Roberto Fernández — 3 reservations spread across recent past
    roberto = by_lastname.get("Fernández")
    if roberto:
        base = date.today() - timedelta(days=240)
        for i, days_offset in enumerate([0, 80, 180]):
            rid = _next_reservation_id(db)
            r = Reservation(
                id=rid,
                created_at=datetime.now(),
                check_in_date=base + timedelta(days=days_offset),
                stay_days=2 + i,
                guest_name=f"{roberto.last_name}, {roberto.first_name}",
                room_id=room.id,
                room_type=room.internal_code or "",
                price=200000.0 + (i * 50000),
                final_price=200000.0 + (i * 50000),
                arrival_time=None,
                reserved_by="seed_test_guests",
                contact_phone=roberto.phone or "",
                contact_email=roberto.email or "",
                received_by="seed_test_guests",
                status="Confirmada",
                property_id=PROPERTY_ID,
                source="Direct",
                guest_id=roberto.id,
            )
            db.add(r)
            res_count += 1
        db.commit()
        # Refresh aggregates so the dashboard label shows "3 estadía/s"
        try:
            GuestService.refresh_aggregates(db=db, guest_id=roberto.id)
        except Exception as e:
            print(f"  [warn] refresh_aggregates(roberto): {e}")

    # María González — 1 reservation + 1 checkin
    maria = by_lastname.get("González")
    if maria:
        rid = _next_reservation_id(db)
        r = Reservation(
            id=rid,
            created_at=datetime.now(),
            check_in_date=date.today() + timedelta(days=7),
            stay_days=3,
            guest_name=f"{maria.last_name}, {maria.first_name}",
            room_id=room.id,
            room_type=room.internal_code or "",
            price=180000.0,
            final_price=180000.0,
            reserved_by="seed_test_guests",
            contact_phone=maria.phone or "",
            contact_email=maria.email or "",
            received_by="seed_test_guests",
            status="Confirmada",
            property_id=PROPERTY_ID,
            source="Direct",
            guest_id=maria.id,
        )
        db.add(r)
        # Commit the reservation FIRST so the FK on the CheckIn resolves
        # (SQLAlchemy flush ordering does not guarantee parent-then-child
        # under SQLite's PRAGMA foreign_keys=ON).
        db.commit()
        ci = CheckIn(
            created_at=date.today(),
            room_id=room.id,
            reservation_id=rid,
            guest_id=maria.id,
            last_name=maria.last_name,
            first_name=maria.first_name,
            document_number=maria.document_number or "",
            nationality=maria.nationality or "",
            country=maria.country or "",
            contact_phone=maria.phone or "",
            contact_email=maria.email or "",
            digital_signature="Pendiente",
        )
        db.add(ci)
        db.commit()
        res_count += 1
        ci_count += 1
        try:
            GuestService.refresh_aggregates(db=db, guest_id=maria.id)
        except Exception:
            pass

    # Hans Müller — OTA reservation, NO checkin
    hans = by_lastname.get("Müller")
    if hans:
        rid = _next_reservation_id(db)
        r = Reservation(
            id=rid,
            created_at=datetime.now(),
            check_in_date=date.today() + timedelta(days=14),
            stay_days=5,
            guest_name=f"{hans.last_name}, {hans.first_name}",
            room_id=room.id,
            room_type=room.internal_code or "",
            price=350000.0,
            final_price=350000.0,
            reserved_by="OTA",
            contact_phone="",
            contact_email=hans.email or "",
            received_by="seed_test_guests",
            status="Confirmada",
            property_id=PROPERTY_ID,
            source="Booking.com",
            guest_id=hans.id,
            ota_booking_id="HM-TEST-001",
        )
        db.add(r)
        res_count += 1
        db.commit()
        try:
            GuestService.refresh_aggregates(db=db, guest_id=hans.id)
        except Exception:
            pass

    return res_count, ci_count


def main():
    parser = argparse.ArgumentParser(description="Seed guest test data.")
    parser.add_argument("--reset", action="store_true", help="Delete previous test data before seeding.")
    parser.add_argument("--dry-run", action="store_true", help="Report only; no DB changes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.dry_run:
            print(f"[DRY-RUN] Would seed {len(GUEST_RECIPES)} guests + reservations.")
            existing = (
                db.query(Guest)
                .filter(Guest.notes.like(f"%{TEST_TAG}%"))
                .count()
            )
            print(f"[DRY-RUN] Currently {existing} test guest(s) tagged in DB.")
            return

        if args.reset:
            _reset_test_data(db)

        # Skip if any TEST_TAG guest already exists (idempotent)
        already = (
            db.query(Guest)
            .filter(Guest.notes.like(f"%{TEST_TAG}%"))
            .count()
        )
        if already > 0 and not args.reset:
            print(f"[INFO] Found {already} existing test guest(s). Use --reset to re-seed.")
            return

        print(f"[INFO] Seeding {len(GUEST_RECIPES)} test guests...")
        guests = _seed_guests(db)
        print(f"[INFO] Seeded {len(guests)} guests. Adding reservations/checkins...")
        n_res, n_ci = _seed_reservations_and_checkins(db, guests)
        print(f"[OK] Seeded {len(guests)} guests, {n_res} reservations, {n_ci} checkins.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
