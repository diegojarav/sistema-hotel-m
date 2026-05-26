"""
Regression tests for bugs surfaced by the 2026-05-26 E2E Test Marathon.

Both bugs allowed the system into a state the operator could never recover
from via the UI: silent double-bookings and Phase 2e late-checkout state
that round-tripped through the DB but never through the API.
"""
from datetime import date, timedelta

import pytest

from database import Reservation
from schemas import ReservationCreate
from services import ReservationService


class TestRoomOverlapGuard:
    """Booking the same room on overlapping dates must be rejected."""

    def _make(self, room_id, check_in, stay_days=1, name="Test Guest", doc="X"):
        return ReservationCreate(
            check_in_date=check_in,
            stay_days=stay_days,
            guest_name=name,
            guest_first_name=name.split()[0],
            guest_last_name=name.split()[-1] if " " in name else name,
            document_number=doc,
            room_ids=[room_id],
            price=120000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
        )

    def test_exact_same_window_rejected(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ci = date.today() + timedelta(days=14)
        ReservationService.create_reservations(db_session, self._make(room_id, ci, doc="DOC-A"))
        with pytest.raises(ValueError, match="ya reservada"):
            ReservationService.create_reservations(db_session, self._make(room_id, ci, doc="DOC-B"))

    def test_partial_overlap_rejected(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ci = date.today() + timedelta(days=14)
        ReservationService.create_reservations(
            db_session, self._make(room_id, ci, stay_days=3, doc="DOC-C"))
        # Second tries to start on the last night → overlap by 1 night
        with pytest.raises(ValueError, match="ya reservada"):
            ReservationService.create_reservations(
                db_session, self._make(room_id, ci + timedelta(days=2), stay_days=2, doc="DOC-D"))

    def test_adjacent_dates_allowed(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ci = date.today() + timedelta(days=14)
        # First books nights [ci, ci+1), check_out = ci+1
        ReservationService.create_reservations(
            db_session, self._make(room_id, ci, stay_days=1, doc="DOC-E"))
        # Second checks in the same day the first checks out → no overlap
        ids = ReservationService.create_reservations(
            db_session, self._make(room_id, ci + timedelta(days=1), stay_days=1, doc="DOC-F"))
        assert len(ids) == 1

    def test_cancelled_reservation_does_not_block(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ci = date.today() + timedelta(days=14)
        ids = ReservationService.create_reservations(
            db_session, self._make(room_id, ci, doc="DOC-G"))
        # Cancel the first, then the second booking on the same window must succeed.
        ReservationService.cancel_reservation(db_session, ids[0], "regression test", "admin")
        ids2 = ReservationService.create_reservations(
            db_session, self._make(room_id, ci, doc="DOC-H"))
        assert len(ids2) == 1


class TestLateCheckoutRoundTrip:
    """Phase 2e late_checkout fields must round-trip through API + update."""

    def _make(self, room_id, *, late=False, time_str=None):
        return ReservationCreate(
            check_in_date=date.today() + timedelta(days=14),
            stay_days=1,
            guest_name="Late Checkout Test",
            guest_first_name="Late",
            guest_last_name="Checkout",
            document_number="DOC-LATE",
            room_ids=[room_id],
            price=120000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            late_checkout=late,
            late_checkout_time=time_str,
        )

    def test_create_persists_late_checkout(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, self._make(room_id, late=True, time_str="14:00"))
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.late_checkout is True
        assert r.late_checkout_time == "14:00"

    def test_detail_dto_exposes_late_checkout(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, self._make(room_id, late=True, time_str="13:30"))
        dto = ReservationService.get_reservation_detail(db_session, ids[0])
        assert dto.late_checkout is True
        assert dto.late_checkout_time == "13:30"
        # early_checkin defaults to False but must be present in the DTO
        assert dto.early_checkin is False

    def test_update_persists_late_checkout(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, self._make(room_id, late=False))
        ReservationService.update_reservation(
            db_session, ids[0], self._make(room_id, late=True, time_str="15:00"))
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.late_checkout is True
        assert r.late_checkout_time == "15:00"

    def test_update_clears_time_when_flag_off(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, self._make(room_id, late=True, time_str="14:00"))
        # Toggle off — late_checkout_time should be cleared even if a value is
        # accidentally still in the payload.
        ReservationService.update_reservation(
            db_session, ids[0], self._make(room_id, late=False, time_str="14:00"))
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.late_checkout is False
        assert r.late_checkout_time is None
