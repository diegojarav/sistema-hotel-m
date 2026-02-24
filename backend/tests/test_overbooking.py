"""
Tier 1 — Parking capacity validation and double-booking behavior tests.
"""

import pytest
from datetime import date, timedelta

from database import Reservation
from schemas import ReservationCreate
from services.reservation_service import ReservationService
from services.settings_service import SettingsService


def _parking_data(room_ids, check_in_days_ahead=15, stay_days=2, **overrides):
    """Build a ReservationCreate with parking_needed=True."""
    base = {
        "check_in_date": date.today() + timedelta(days=check_in_days_ahead),
        "stay_days": stay_days,
        "guest_name": "Parking Guest",
        "room_ids": room_ids,
        "price": 150000,
        "property_id": "los-monges",
        "parking_needed": True,
    }
    base.update(overrides)
    return ReservationCreate(**base)


class TestParkingCapacity:
    def test_allows(self, db_session, seed_rooms, seed_client_types):
        SettingsService.set_parking_capacity(db_session, 2)
        data = _parking_data([seed_rooms["rooms"][0].id])
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1

    def test_blocks(self, db_session, seed_rooms, seed_client_types):
        SettingsService.set_parking_capacity(db_session, 1)

        # First reservation fills the single parking slot
        data1 = _parking_data(
            [seed_rooms["rooms"][0].id],
            check_in_days_ahead=15,
            stay_days=3,
            guest_name="First Parker",
        )
        ReservationService.create_reservations(db_session, data1)

        # Second overlapping reservation should fail
        data2 = _parking_data(
            [seed_rooms["rooms"][1].id],
            check_in_days_ahead=16,
            stay_days=3,
            guest_name="Second Parker",
        )
        with pytest.raises(Exception, match="Estacionamiento lleno"):
            ReservationService.create_reservations(db_session, data2)

    def test_no_overlap_ok(self, db_session, seed_rooms, seed_client_types):
        SettingsService.set_parking_capacity(db_session, 1)

        # First parking: days 15-16
        data1 = _parking_data(
            [seed_rooms["rooms"][0].id],
            check_in_days_ahead=15,
            stay_days=2,
            guest_name="Parker A",
        )
        ReservationService.create_reservations(db_session, data1)

        # Second parking: days 25-26 (no overlap)
        data2 = _parking_data(
            [seed_rooms["rooms"][1].id],
            check_in_days_ahead=25,
            stay_days=2,
            guest_name="Parker B",
        )
        ids = ReservationService.create_reservations(db_session, data2)
        assert len(ids) == 1

        parking_count = db_session.query(Reservation).filter(
            Reservation.parking_needed == True,
        ).count()
        assert parking_count == 2


class TestRoomOverbooking:
    def test_double_booking_allowed(self, db_session, seed_rooms, make_reservation):
        """Documents that the system currently allows double-booking."""
        target_date = date.today() + timedelta(days=10)
        room_id = seed_rooms["rooms"][0].id

        make_reservation(check_in_date=target_date, stay_days=3,
                         room_id=room_id, guest_name="Guest A")
        make_reservation(check_in_date=target_date, stay_days=3,
                         room_id=room_id, guest_name="Guest B")

        count = db_session.query(Reservation).filter(
            Reservation.room_id == room_id,
            Reservation.check_in_date == target_date,
        ).count()
        assert count == 2

    def test_daily_status_double_booked(self, db_session, seed_rooms, make_reservation):
        target_date = date.today() + timedelta(days=10)
        room_id = seed_rooms["rooms"][0].id

        make_reservation(check_in_date=target_date, stay_days=3,
                         room_id=room_id, guest_name="Guest A")
        make_reservation(check_in_date=target_date, stay_days=3,
                         room_id=room_id, guest_name="Guest B")

        result = ReservationService.get_daily_status(db_session, target_date)
        room_entry = [r for r in result if r["room_id"] == room_id]
        assert len(room_entry) == 1
        assert room_entry[0]["status"] == "OCUPADA"
