"""
Test Suite for FEAT-LINK-01: Smart Reservation ↔ Check-in Linking

Tests:
1. Document scan → auto-create linked CheckIn
2. Duplicate prevention by document_number
3. Vincular (link) existing reservation to CheckIn
4. Database integrity (FK constraints)
5. Unlinked reservations endpoint

Usage:
    python scripts/test_feat_link_01.py
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from datetime import date, datetime, timedelta, time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import Base, Reservation, CheckIn, Room
from schemas import ReservationCreate, CheckInCreate
from services import ReservationService, GuestService

# Test database (use a copy or test DB)
TEST_DB_PATH = "backend/hotel.db"
engine = create_engine(f"sqlite:///{TEST_DB_PATH}")
SessionLocal = sessionmaker(bind=engine)

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_test(name):
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BLUE}TEST: {name}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}")

def print_pass(message):
    print(f"{Colors.GREEN}[PASS] {message}{Colors.RESET}")

def print_fail(message):
    print(f"{Colors.RED}[FAIL] {message}{Colors.RESET}")

def print_info(message):
    print(f"{Colors.YELLOW}[INFO] {message}{Colors.RESET}")

def cleanup_test_data(db, test_doc_number):
    """Remove test data"""
    db.execute(text("DELETE FROM checkins WHERE document_number = :doc"), {"doc": test_doc_number})
    db.execute(text("DELETE FROM reservations WHERE guest_name LIKE :name"), {"name": "%TEST_GUEST%"})
    db.commit()

def get_first_available_room(db):
    """Get first available room ID"""
    room = db.query(Room).first()
    return room.id if room else None

# ============================================================================
# TEST 1: Auto-create CheckIn from Reservation with document_number
# ============================================================================
def test_auto_create_checkin():
    print_test("Auto-create CheckIn from Reservation")

    db = SessionLocal()
    test_doc = "TEST_DOC_001"

    try:
        # Cleanup first
        cleanup_test_data(db, test_doc)

        # Get a room
        room_id = get_first_available_room(db)
        if not room_id:
            print_fail("No rooms available in database")
            return False

        print_info(f"Using room: {room_id}")

        # Create reservation WITH identity fields (simulates document scan)
        reservation_data = ReservationCreate(
            check_in_date=date.today(),
            stay_days=2,
            guest_name="TEST_GUEST_JOHN DOE",
            room_ids=[room_id],
            room_type="Standard",
            price=100000.0,
            arrival_time=datetime.now().time(),
            reserved_by="Test Script",
            contact_phone="0981234567",
            received_by="test_user",
            # FEAT-LINK-01: Identity fields from document scan
            document_number=test_doc,
            guest_last_name="Doe",
            guest_first_name="John",
            nationality="Paraguayo",
            birth_date=date(1990, 1, 1),
            country="Paraguay"
        )

        print_info("Creating reservation with identity fields...")
        created_ids = ReservationService.create_reservations(reservation_data)
        reservation_id = created_ids[0]
        print_pass(f"Reservation created: {reservation_id}")

        # Verify CheckIn was auto-created
        checkin = db.query(CheckIn).filter(CheckIn.document_number == test_doc).first()

        if not checkin:
            print_fail("CheckIn was NOT auto-created")
            return False

        print_pass(f"CheckIn auto-created: ID {checkin.id}")

        # Verify linking
        if checkin.reservation_id != reservation_id:
            print_fail(f"CheckIn not linked! Expected reservation_id={reservation_id}, got {checkin.reservation_id}")
            return False

        print_pass(f"CheckIn correctly linked to reservation {reservation_id}")

        # Verify data transfer
        checks = [
            (checkin.last_name == "Doe", "last_name"),
            (checkin.first_name == "John", "first_name"),
            (checkin.nationality == "Paraguayo", "nationality"),
            (checkin.birth_date == date(1990, 1, 1), "birth_date"),
            (checkin.country == "Paraguay", "country"),
        ]

        for check, field in checks:
            if check:
                print_pass(f"Field {field} transferred correctly")
            else:
                print_fail(f"Field {field} NOT transferred correctly")
                return False

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cleanup_test_data(db, test_doc)
        db.close()

# ============================================================================
# TEST 2: Duplicate Prevention
# ============================================================================
def test_duplicate_prevention():
    print_test("Duplicate Prevention by document_number")

    db = SessionLocal()
    test_doc = "TEST_DOC_002"

    try:
        cleanup_test_data(db, test_doc)

        # Create first CheckIn
        checkin_data_1 = CheckInCreate(
            room_id=None,
            last_name="Smith",
            first_name="Alice",
            nationality="Brasileño",
            birth_date=date(1985, 5, 15),
            document_number=test_doc,
            country="Brasil"
        )

        print_info("Creating first CheckIn...")
        checkin_id_1 = GuestService.register_checkin(checkin_data_1)
        print_pass(f"First CheckIn created: ID {checkin_id_1}")

        # Try to create duplicate with same document_number
        checkin_data_2 = CheckInCreate(
            room_id=None,
            last_name="Smith-Updated",
            first_name="Alice-Updated",
            nationality="Argentino",
            birth_date=date(1985, 5, 15),
            document_number=test_doc,
            country="Argentina"
        )

        print_info("Attempting to create duplicate CheckIn with same document_number...")
        checkin_id_2 = GuestService.register_checkin(checkin_data_2)

        # Should return same ID (update, not create)
        if checkin_id_2 != checkin_id_1:
            print_fail(f"Duplicate created! Got ID {checkin_id_2}, expected {checkin_id_1}")
            return False

        print_pass(f"Duplicate prevented - returned same ID: {checkin_id_2}")

        # Verify data was updated
        checkin = db.query(CheckIn).filter(CheckIn.id == checkin_id_1).first()
        if checkin.last_name == "Smith-Updated":
            print_pass("Existing record was updated (not duplicated)")
        else:
            print_fail("Record was not updated")
            return False

        # Verify only ONE record exists
        count = db.query(CheckIn).filter(CheckIn.document_number == test_doc).count()
        if count == 1:
            print_pass(f"Only 1 record exists in DB for document {test_doc}")
        else:
            print_fail(f"Found {count} records for document {test_doc}, expected 1")
            return False

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cleanup_test_data(db, test_doc)
        db.close()

# ============================================================================
# TEST 3: Manual Link via Vincular Dropdown
# ============================================================================
def test_manual_link():
    print_test("Manual Link via Vincular Dropdown")

    db = SessionLocal()
    test_doc = "TEST_DOC_003"

    try:
        cleanup_test_data(db, test_doc)

        room_id = get_first_available_room(db)
        if not room_id:
            print_fail("No rooms available")
            return False

        # Create reservation WITHOUT document_number (unlinked)
        reservation_data = ReservationCreate(
            check_in_date=date.today(),
            stay_days=1,
            guest_name="TEST_GUEST_UNLINKED",
            room_ids=[room_id],
            room_type="Standard",
            price=80000.0,
            arrival_time=datetime.now().time(),
            reserved_by="Test",
            contact_phone="0981111111",
            received_by="test_user"
        )

        print_info("Creating unlinked reservation...")
        reservation_id = ReservationService.create_reservations(reservation_data)[0]
        print_pass(f"Unlinked reservation created: {reservation_id}")

        # Verify no CheckIn was created
        checkin_count = db.query(CheckIn).filter(CheckIn.reservation_id == reservation_id).count()
        if checkin_count == 0:
            print_pass("No CheckIn auto-created (expected for reservation without document)")
        else:
            print_fail("CheckIn was unexpectedly created")
            return False

        # Get unlinked reservations
        print_info("Fetching unlinked reservations...")
        unlinked = GuestService.get_unlinked_reservations()

        found = any(r['id'] == reservation_id for r in unlinked)
        if found:
            print_pass(f"Reservation {reservation_id} appears in unlinked list")
        else:
            print_fail(f"Reservation {reservation_id} NOT in unlinked list")
            return False

        # Manually create CheckIn and link it
        checkin_data = CheckInCreate(
            room_id=room_id,
            reservation_id=reservation_id,  # Manual link
            last_name="Manual",
            first_name="Link",
            document_number=test_doc,
            nationality="Paraguayo",
            birth_date=date(1992, 3, 10),
            country="Paraguay"
        )

        print_info("Creating CheckIn with manual link...")
        checkin_id = GuestService.register_checkin(checkin_data)
        print_pass(f"CheckIn created with manual link: ID {checkin_id}")

        # Verify link
        checkin = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if checkin.reservation_id == reservation_id:
            print_pass(f"CheckIn correctly linked to reservation {reservation_id}")
        else:
            print_fail("CheckIn not linked correctly")
            return False

        # Verify reservation no longer appears in unlinked list
        unlinked_after = GuestService.get_unlinked_reservations()
        still_found = any(r['id'] == reservation_id for r in unlinked_after)

        if not still_found:
            print_pass(f"Reservation {reservation_id} removed from unlinked list after linking")
        else:
            print_fail(f"Reservation {reservation_id} still in unlinked list")
            return False

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cleanup_test_data(db, test_doc)
        db.close()

# ============================================================================
# TEST 4: Database Integrity - FK Constraints
# ============================================================================
def test_database_integrity():
    print_test("Database Integrity - FK Constraints")

    db = SessionLocal()

    try:
        # Verify reservation_id column exists
        result = db.execute(text("PRAGMA table_info(checkins)")).fetchall()
        columns = [row[1] for row in result]

        if "reservation_id" in columns:
            print_pass("Column 'reservation_id' exists in checkins table")
        else:
            print_fail("Column 'reservation_id' NOT found in checkins table")
            return False

        # Verify index exists
        indexes = db.execute(text("PRAGMA index_list(checkins)")).fetchall()
        index_names = [idx[1] for idx in indexes]

        has_reservation_index = any("reservation" in name.lower() for name in index_names)
        if has_reservation_index:
            print_pass("Index on reservation_id found")
        else:
            print_info("No specific index on reservation_id (nullable FK, might be intentional)")

        # Test FK constraint (if enabled)
        print_info("Testing FK constraint...")

        # Try to insert CheckIn with non-existent reservation_id
        try:
            fake_checkin = CheckIn(
                created_at=date.today(),
                reservation_id="FAKE_RESERVATION_ID_99999",
                last_name="Test",
                first_name="FK",
                document_number="FK_TEST"
            )
            db.add(fake_checkin)
            db.commit()

            # If we got here, FK constraint is NOT enforced (SQLite default)
            print_info("FK constraint not enforced (SQLite default - PRAGMA foreign_keys=OFF)")

            # Cleanup
            db.delete(fake_checkin)
            db.commit()

        except Exception as e:
            print_pass(f"FK constraint enforced: {str(e)[:50]}...")
            db.rollback()

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

# ============================================================================
# TEST 5: Update Existing CheckIn with Reservation Link
# ============================================================================
def test_update_existing_checkin():
    print_test("Update Existing CheckIn - Link to Reservation")

    db = SessionLocal()
    test_doc = "TEST_DOC_004"

    try:
        cleanup_test_data(db, test_doc)

        room_id = get_first_available_room(db)
        if not room_id:
            print_fail("No rooms available")
            return False

        # Create standalone CheckIn first
        checkin_data = CheckInCreate(
            room_id=room_id,
            last_name="Existing",
            first_name="Guest",
            document_number=test_doc,
            nationality="Paraguayo",
            birth_date=date(1988, 7, 20),
            country="Paraguay"
        )

        print_info("Creating standalone CheckIn...")
        checkin_id = GuestService.register_checkin(checkin_data)
        print_pass(f"CheckIn created: ID {checkin_id}")

        # Verify no reservation linked
        checkin = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if checkin.reservation_id is None:
            print_pass("CheckIn has no reservation_id (expected)")
        else:
            print_fail(f"CheckIn unexpectedly has reservation_id: {checkin.reservation_id}")
            return False

        # Now create reservation with same document_number
        reservation_data = ReservationCreate(
            check_in_date=date.today(),
            stay_days=2,
            guest_name="TEST_GUEST_EXISTING",
            room_ids=[room_id],
            room_type="Standard",
            price=90000.0,
            arrival_time=datetime.now().time(),
            reserved_by="Test",
            contact_phone="0982222222",
            received_by="test_user",
            document_number=test_doc,
            guest_last_name="Existing",
            guest_first_name="Guest",
            nationality="Paraguayo",
            birth_date=date(1988, 7, 20),
            country="Paraguay"
        )

        print_info("Creating reservation with same document_number...")
        reservation_id = ReservationService.create_reservations(reservation_data)[0]
        print_pass(f"Reservation created: {reservation_id}")

        # Verify existing CheckIn was linked (not duplicated)
        db.refresh(checkin)

        if checkin.reservation_id == reservation_id:
            print_pass(f"Existing CheckIn linked to new reservation {reservation_id}")
        else:
            print_fail(f"CheckIn not linked! Expected {reservation_id}, got {checkin.reservation_id}")
            return False

        # Verify no duplicate CheckIn created
        checkin_count = db.query(CheckIn).filter(CheckIn.document_number == test_doc).count()
        if checkin_count == 1:
            print_pass("No duplicate CheckIn created")
        else:
            print_fail(f"Found {checkin_count} CheckIns, expected 1")
            return False

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cleanup_test_data(db, test_doc)
        db.close()

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"FEAT-LINK-01 TEST SUITE")
    print(f"Database: {TEST_DB_PATH}")
    print(f"{'='*70}{Colors.RESET}\n")

    tests = [
        ("Auto-create CheckIn from Reservation", test_auto_create_checkin),
        ("Duplicate Prevention", test_duplicate_prevention),
        ("Manual Link via Vincular", test_manual_link),
        ("Database Integrity", test_database_integrity),
        ("Update Existing CheckIn with Link", test_update_existing_checkin),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"Test crashed: {e}")
            results.append((name, False))

    # Summary
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"TEST SUMMARY")
    print(f"{'='*70}{Colors.RESET}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if result else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  {status} - {name}")

    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print(f"{Colors.GREEN}[SUCCESS] ALL TESTS PASSED{Colors.RESET}")
    else:
        print(f"{Colors.RED}[ERROR] SOME TESTS FAILED{Colors.RESET}")

    print(f"{'='*70}{Colors.RESET}\n")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
