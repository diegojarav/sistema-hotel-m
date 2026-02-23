"""
Phase 2 — Service-layer tests for ReservationService (PC/Streamlit path).

Tests ReservationService CRUD, search, weekly view, occupancy map,
and FEAT-LINK-01 auto-checkin creation.
"""

import pytest
from datetime import date, timedelta

from services.reservation_service import ReservationService
from schemas import ReservationCreate
from database import Reservation, CheckIn


def _make_res_data(**overrides):
    """Helper to build a valid ReservationCreate with sensible defaults."""
    defaults = dict(
        check_in_date=date.today() + timedelta(days=7),
        stay_days=2,
        guest_name="Carlos Gonzalez",
        room_ids=["los-monges-room-001"],
        room_type="Estandar",
        price=150000.0,
        reserved_by="test",
        contact_phone="0981555000",
        received_by="recepcion",
        source="Direct",
    )
    defaults.update(overrides)
    return ReservationCreate(**defaults)


# ==========================================
# create_reservations
# ==========================================

class TestCreateReservations:
    """Tests for ReservationService.create_reservations."""

    def test_single_room_returns_one_id(self, db_session, seed_full):
        """Creating a reservation for 1 room returns a list with 1 ID."""
        data = _make_res_data(room_ids=["los-monges-room-001"])
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1
        assert len(ids[0]) == 7  # zero-padded 7 digits

    def test_multi_room_returns_n_ids(self, db_session, seed_full):
        """Creating a reservation for 3 rooms returns 3 IDs."""
        data = _make_res_data(
            room_ids=["los-monges-room-001", "los-monges-room-002", "los-monges-room-003"]
        )
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 3
        # IDs should be sequential
        assert int(ids[1]) == int(ids[0]) + 1
        assert int(ids[2]) == int(ids[0]) + 2

    def test_status_is_confirmada(self, db_session, seed_full):
        """Newly created reservation has status 'Confirmada'."""
        data = _make_res_data()
        ids = ReservationService.create_reservations(db_session, data)
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.status == "Confirmada"

    def test_create_with_document_auto_creates_checkin(self, db_session, seed_full):
        """FEAT-LINK-01: Providing document_number auto-creates a CheckIn record."""
        data = _make_res_data(
            document_number="4567890",
            guest_last_name="Gonzalez",
            guest_first_name="Carlos",
            nationality="Paraguaya",
        )
        ids = ReservationService.create_reservations(db_session, data)

        # Verify CheckIn was auto-created
        checkin = db_session.query(CheckIn).filter(
            CheckIn.document_number == "4567890"
        ).first()
        assert checkin is not None
        assert checkin.reservation_id == ids[0]
        assert checkin.last_name == "Gonzalez"
        assert checkin.first_name == "Carlos"


# ==========================================
# cancel_reservation
# ==========================================

class TestCancelReservation:
    """Tests for ReservationService.cancel_reservation."""

    def test_cancel_changes_status(self, db_session, seed_full):
        """Cancelling an existing reservation sets status to 'Cancelada'."""
        data = _make_res_data()
        ids = ReservationService.create_reservations(db_session, data)

        result = ReservationService.cancel_reservation(
            db_session, ids[0], reason="guest request", user="admin"
        )
        assert result is True

        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.status == "Cancelada"
        assert res.cancellation_reason == "guest request"
        assert res.cancelled_by == "admin"

    def test_cancel_nonexistent_returns_false(self, db_session, seed_full):
        """Cancelling a reservation that does not exist returns False."""
        result = ReservationService.cancel_reservation(
            db_session, "9999999", reason="test", user="admin"
        )
        assert result is False


# ==========================================
# update_reservation
# ==========================================

class TestUpdateReservation:
    """Tests for ReservationService.update_reservation."""

    def test_update_modifies_fields(self, db_session, seed_full):
        """Updating a reservation changes the stored fields."""
        data = _make_res_data()
        ids = ReservationService.create_reservations(db_session, data)

        new_data = _make_res_data(
            guest_name="Maria Lopez",
            stay_days=5,
            check_in_date=date.today() + timedelta(days=14),
        )
        result = ReservationService.update_reservation(db_session, ids[0], new_data)
        assert result is True

        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.guest_name == "Maria Lopez"
        assert res.stay_days == 5

    def test_update_nonexistent_returns_false(self, db_session, seed_full):
        """Updating a reservation that does not exist returns False."""
        data = _make_res_data()
        result = ReservationService.update_reservation(db_session, "9999999", data)
        assert result is False


# ==========================================
# get_reservation
# ==========================================

class TestGetReservation:
    """Tests for ReservationService.get_reservation."""

    def test_get_existing_returns_data(self, db_session, seed_full):
        """Getting an existing reservation returns a ReservationCreate with correct data."""
        data = _make_res_data(guest_name="Pedro Benitez")
        ids = ReservationService.create_reservations(db_session, data)

        result = ReservationService.get_reservation(db_session, ids[0])
        assert result is not None
        assert result.guest_name == "Pedro Benitez"
        assert result.stay_days == 2

    def test_get_nonexistent_returns_none(self, db_session, seed_full):
        """Getting a nonexistent reservation returns None."""
        result = ReservationService.get_reservation(db_session, "9999999")
        assert result is None


# ==========================================
# search_reservations
# ==========================================

class TestSearchReservations:
    """Tests for ReservationService.search_reservations."""

    def test_search_by_guest_name(self, db_session, seed_full):
        """Searching by guest name finds the matching reservation."""
        data = _make_res_data(guest_name="Alejandro Dominguez")
        ReservationService.create_reservations(db_session, data)

        results = ReservationService.search_reservations(db_session, "Alejandro")
        assert len(results) >= 1
        assert any(r["guest_name"] == "Alejandro Dominguez" for r in results)


# ==========================================
# get_all_reservations
# ==========================================

class TestGetAllReservations:
    """Tests for ReservationService.get_all_reservations."""

    def test_returns_list_sorted_by_created_at(self, db_session, seed_full):
        """Returns a list of ReservationDTO sorted by created_at desc."""
        data1 = _make_res_data(guest_name="Guest A", room_ids=["los-monges-room-001"])
        data2 = _make_res_data(guest_name="Guest B", room_ids=["los-monges-room-002"])
        ReservationService.create_reservations(db_session, data1)
        ReservationService.create_reservations(db_session, data2)

        result = ReservationService.get_all_reservations(db_session)
        assert len(result) >= 2
        # Most recently created should appear first (desc order)
        names = [r.guest_name for r in result]
        assert "Guest A" in names
        assert "Guest B" in names

    def test_pagination_via_make_reservation(self, db_session, make_reservation):
        """Fixture-created reservations appear in get_all_reservations."""
        make_reservation(guest_name="Pag Test 1")
        make_reservation(guest_name="Pag Test 2")
        make_reservation(guest_name="Pag Test 3")

        all_res = ReservationService.get_all_reservations(db_session)
        assert len(all_res) == 3


# ==========================================
# get_weekly_view
# ==========================================

class TestGetWeeklyView:
    """Tests for ReservationService.get_weekly_view."""

    def test_weekly_view_returns_dict_with_room_data(self, db_session, make_reservation):
        """Weekly view returns a dict keyed by room display code."""
        ref = date.today() + timedelta(days=7)
        make_reservation(check_in_date=ref, stay_days=2, guest_name="Weekly Guest")

        result = ReservationService.get_weekly_view(db_session, ref)
        assert isinstance(result, dict)
        # At least one room should have data
        assert len(result) >= 1
        # Check that dates are ISO-formatted keys
        for room_code, dates_map in result.items():
            for day_str in dates_map:
                assert len(day_str) == 10  # "YYYY-MM-DD"


# ==========================================
# get_occupancy_map
# ==========================================

class TestGetOccupancyMap:
    """Tests for ReservationService.get_occupancy_map."""

    def test_occupancy_map_returns_all_days(self, db_session, seed_full):
        """Occupancy map has an entry for every day of the month."""
        year = date.today().year
        month = date.today().month

        result = ReservationService.get_occupancy_map(db_session, year, month)
        assert isinstance(result, dict)
        # Should have at least 28 entries (shortest month)
        assert len(result) >= 28
        # Each entry has count and status
        for day_key, day_data in result.items():
            assert "count" in day_data
            assert "status" in day_data
