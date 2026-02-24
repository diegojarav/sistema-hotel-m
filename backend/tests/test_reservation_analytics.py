"""
Tier 1 — Service-layer tests for ReservationService analytics methods.
"""

from datetime import date, timedelta

from services.reservation_service import ReservationService


class TestGetDailyStatus:
    def test_all_free(self, db_session, seed_rooms):
        future = date.today() + timedelta(days=30)
        result = ReservationService.get_daily_status(db_session, future)

        assert len(result) == 6
        for room in result:
            assert room["status"] == "Libre"
            assert room["huesped"] == "-"
            assert "room_id" in room
            assert "internal_code" in room
            assert "type" in room

    def test_occupied(self, db_session, seed_rooms, make_reservation):
        target = date.today() + timedelta(days=15)
        make_reservation(
            check_in_date=target - timedelta(days=1),
            stay_days=3,
            guest_name="Occupied Guest",
            room_id=seed_rooms["rooms"][0].id,
        )
        result = ReservationService.get_daily_status(db_session, target)

        occupied = [r for r in result if r["room_id"] == seed_rooms["rooms"][0].id]
        assert len(occupied) == 1
        assert occupied[0]["status"] == "OCUPADA"
        assert occupied[0]["huesped"] == "Occupied Guest"
        assert occupied[0]["res_id"] is not None

        free = [r for r in result if r["room_id"] != seed_rooms["rooms"][0].id]
        assert all(r["status"] == "Libre" for r in free)


class TestGetRangeStatus:
    def test_free(self, db_session, seed_rooms):
        start = date.today() + timedelta(days=40)
        end = date.today() + timedelta(days=45)
        result = ReservationService.get_range_status(db_session, start, end)

        assert len(result) == 6
        assert all(r["status"] == "Libre" for r in result)

    def test_occupied(self, db_session, seed_rooms, make_reservation):
        make_reservation(
            check_in_date=date.today() + timedelta(days=18),
            stay_days=5,
            room_id=seed_rooms["rooms"][0].id,
            guest_name="Range Guest",
        )
        # Query range overlaps the reservation
        start = date.today() + timedelta(days=20)
        end = date.today() + timedelta(days=25)
        result = ReservationService.get_range_status(db_session, start, end)

        room0 = [r for r in result if r["room_id"] == seed_rooms["rooms"][0].id]
        assert room0[0]["status"] == "OCUPADA"
        assert room0[0]["huesped"] == "Range Guest"

        others = [r for r in result if r["room_id"] != seed_rooms["rooms"][0].id]
        assert all(r["status"] == "Libre" for r in others)


class TestGetReservationsInRange:
    def test_found(self, db_session, seed_rooms, make_reservation):
        res = make_reservation(
            check_in_date=date.today() + timedelta(days=10),
            stay_days=3,
            guest_name="Range Find Guest",
        )
        start = date.today() + timedelta(days=8)
        end = date.today() + timedelta(days=15)
        result = ReservationService.get_reservations_in_range(db_session, start, end)

        assert len(result) >= 1
        match = [r for r in result if r["id"] == res.id]
        assert len(match) == 1
        assert match[0]["guest_name"] == "Range Find Guest"
        # Verify all expected keys
        for key in ("id", "guest_name", "room_id", "room_code", "check_in_date",
                     "check_out_date", "stay_days", "status", "price"):
            assert key in match[0]

    def test_room_filter(self, db_session, seed_rooms, make_reservation):
        start = date.today() + timedelta(days=10)
        make_reservation(
            check_in_date=start, stay_days=2,
            room_id=seed_rooms["rooms"][0].id, guest_name="Room A",
        )
        make_reservation(
            check_in_date=start, stay_days=2,
            room_id=seed_rooms["rooms"][1].id, guest_name="Room B",
        )
        end = start + timedelta(days=5)

        filtered = ReservationService.get_reservations_in_range(
            db_session, start, end, room_number=seed_rooms["rooms"][0].id,
        )
        assert len(filtered) == 1
        assert filtered[0]["guest_name"] == "Room A"


class TestGetMonthlyRoomView:
    def test_empty(self, db_session, seed_rooms):
        result = ReservationService.get_monthly_room_view(db_session, 2026, 8)

        assert "rooms" in result
        assert "days" in result
        assert "matrix" in result
        assert len(result["rooms"]) == 6
        assert result["days"] == list(range(1, 32))  # August has 31 days
        assert result["matrix"] == {}

    def test_with_reservation(self, db_session, seed_rooms, make_reservation):
        make_reservation(
            check_in_date=date(2026, 8, 10),
            stay_days=3,
            guest_name="Monthly Guest",
            room_id=seed_rooms["rooms"][0].id,
        )
        result = ReservationService.get_monthly_room_view(db_session, 2026, 8)

        room_code = seed_rooms["rooms"][0].internal_code
        assert room_code in result["matrix"]

        cells = result["matrix"][room_code]
        # 3-day stay from Aug 10: occupies days 10, 11, 12
        assert "10" in cells
        assert "11" in cells
        assert "12" in cells
        assert "9" not in cells
        assert "13" not in cells

        assert cells["10"]["is_checkin"] is True
        assert cells["10"]["is_checkout"] is False
        assert cells["11"]["is_checkin"] is False
        assert cells["11"]["is_checkout"] is False
        assert cells["12"]["is_checkin"] is False
        assert cells["12"]["is_checkout"] is True

        assert cells["10"]["guest"] == "Monthly Guest"
