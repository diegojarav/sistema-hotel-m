import sys
import os
from datetime import date, datetime, timedelta

# Add backend to path to import services/db
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal, Reservation, engine, Base
from services import ReservationService, SettingsService, ReservationCreate
from sqlalchemy.orm import Session

def test_parking_flow():
    db = SessionLocal()
    print("--- Starting Parking Verification ---")
    
    # Clean up any previous test runs
    db.query(Reservation).filter(Reservation.guest_name.like("Test%")).delete(synchronize_session=False)
    db.commit()

    try:
        # 1. Set Capacity to 2 for testing
        print("1. Setting Parking Capacity to 2")
        SettingsService.set_parking_capacity(db, 2)
        cap = SettingsService.get_parking_capacity(db)
        assert cap == 2, f"Capacity should be 2, got {cap}"
        
        # 2. Create Reservation 1 (Parking=True)
        print("2. Creating Res 1 (Needs Parking)")
        res_data_1 = ReservationCreate(
            check_in_date=date.today(),
            stay_days=1,
            guest_name="Test Driver 1",
            room_ids=["TEST_P1"],
            room_type="Standard",
            price=100000,
            arrival_time=datetime.now(),
            reserved_by="Tester",
            contact_phone="123", # Required by schema? checking defaults
            received_by="Admin",
            category_id=None,
            client_type_id=None,
            price_breakdown="{}",
            parking_needed=True,
            vehicle_model="Tesla Cybertruck",
            vehicle_plate="ELON-001",
            source="Direct"
        )
        try:
            ids1 = ReservationService.create_reservations(res_data_1)
            print(f"   Success: {ids1}")
        except Exception as e:
            print(f"   Failed: {e}")
            import traceback
            traceback.print_exc()
            exit(1)

        # 3. Verify DB Fields
        print("3. Verifying DB Fields")
        res1 = db.query(Reservation).filter(Reservation.id == ids1[0]).first()
        if not res1:
            print("   ❌ Failed to fetch reservation 1")
            exit(1)
            
        print(f"   DB check: Parking={res1.parking_needed}, Model={res1.vehicle_model}, Plate={res1.vehicle_plate}")
        assert res1.parking_needed == True
        assert res1.vehicle_model == "Tesla Cybertruck"
        assert res1.vehicle_plate == "ELON-001"
        assert res1.source == "Direct"
        print("   Data Verified ✅")

        # 4. Create Reservation 2 (Parking=True) -> Should Succeed (1+1 <= 2)
        print("4. Creating Res 2 (Needs Parking) - Should Succeed")
        res_data_2 = ReservationCreate(
            check_in_date=date.today(),
            stay_days=1,
            guest_name="Test Driver 2",
            room_ids=["TEST_P2"],
            room_type="Standard",
            price=100000,
            arrival_time=datetime.now(),
            reserved_by="Tester",
            parking_needed=True,
             contact_phone="123", received_by="Admin", category_id=None, client_type_id=None, price_breakdown="{}"
        )
        ids2 = ReservationService.create_reservations(res_data_2)
        print(f"   Success: {ids2}")

        # 5. Create Reservation 3 (Parking=True) -> Should Fail (2+1 > 2)
        print("5. Creating Res 3 (Needs Parking) - Should FAIL")
        res_data_3 = ReservationCreate(
            check_in_date=date.today(),
            stay_days=1,
            guest_name="Test Driver 3",
            room_ids=["TEST_P3"],
            room_type="Standard",
            price=100000,
            arrival_time=datetime.now(),
            reserved_by="Tester",
            parking_needed=True,
             contact_phone="123", received_by="Admin", category_id=None, client_type_id=None, price_breakdown="{}"
        )
        try:
            ReservationService.create_reservations(res_data_3)
            print("   ❌ Error: Should have failed due to capacity!")
        except Exception as e:
            if "Estacionamiento lleno" in str(e) or "Parking" in str(e):
                print(f"   ✅ Correctly Failed: {e}")
            else:
                 print(f"   ⚠️ Failed with unexpected error: {e}")

        # 6. Create Reservation 4 (Parking=False) -> Should Succeed
        print("6. Creating Res 4 (No Parking) - Should Succeed")
        res_data_4 = ReservationCreate(
            check_in_date=date.today(),
            stay_days=1,
            guest_name="Test Walker",
            room_ids=["TEST_P4"],
            room_type="Standard",
            price=100000,
            arrival_time=datetime.now(),
            reserved_by="Tester",
            parking_needed=False,
             contact_phone="123", received_by="Admin", category_id=None, client_type_id=None, price_breakdown="{}"
        )
        ids4 = ReservationService.create_reservations(res_data_4)
        print(f"   Success: {ids4}")
        
    finally:
        # Cleanup
        print("--- Cleanup ---")
        SettingsService.set_parking_capacity(db, 5) # Restore default
        db.query(Reservation).filter(Reservation.guest_name.like("Test%")).delete(synchronize_session=False)
        db.commit()
        db.close()
        print("Test Complete.")

if __name__ == "__main__":
    test_parking_flow()
