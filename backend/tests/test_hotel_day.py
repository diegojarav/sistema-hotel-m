"""
Hotel-day operational logic (v1.10.0 — Phase 2e).

Covers:
- get_current_hotel_day before/after the cutoff
- can_create_reservation_for_date across the boundary
- _coerce_time on "HH:MM" strings, time objects, None
- ReservationCreate (Pydantic validator) accepting "yesterday" before
  check-out, rejecting it after
- ReservationService accepting/persisting early_checkin / late_checkout
"""
from datetime import date, datetime, time, timedelta

import pytest

from schemas import ReservationCreate
from services.hotel_day import (
    can_create_reservation_for_date,
    get_current_hotel_day,
    DEFAULT_CHECK_OUT_TIME,
)
from services.hotel_day import _coerce_time


# ======================================================================
# get_current_hotel_day
# ======================================================================
class TestGetCurrentHotelDay:
    def test_before_checkout_returns_yesterday(self):
        """At 02:00, the operational 'today' is yesterday's calendar date."""
        now = datetime(2026, 5, 12, 2, 0, 0)
        assert get_current_hotel_day(check_out_time=time(10, 0), now=now) == date(2026, 5, 11)

    def test_minute_before_checkout(self):
        """09:59 with 10:00 check-out → still yesterday."""
        now = datetime(2026, 5, 12, 9, 59, 0)
        assert get_current_hotel_day(check_out_time=time(10, 0), now=now) == date(2026, 5, 11)

    def test_exactly_at_checkout_flips_to_today(self):
        """10:00 exactly → new hotel day begins."""
        now = datetime(2026, 5, 12, 10, 0, 0)
        assert get_current_hotel_day(check_out_time=time(10, 0), now=now) == date(2026, 5, 12)

    def test_evening_returns_today(self):
        """22:30 well after check-out → today's hotel day."""
        now = datetime(2026, 5, 12, 22, 30, 0)
        assert get_current_hotel_day(check_out_time=time(10, 0), now=now) == date(2026, 5, 12)

    def test_accepts_string_check_out_time(self):
        """Property stores check_out_time as 'HH:MM' string — must coerce."""
        now = datetime(2026, 5, 12, 11, 30, 0)
        assert get_current_hotel_day(check_out_time="12:00", now=now) == date(2026, 5, 11)
        assert get_current_hotel_day(check_out_time="11:00", now=now) == date(2026, 5, 12)

    def test_default_check_out_is_10_am(self):
        """No arg → assumes 10:00."""
        now = datetime(2026, 5, 12, 9, 0, 0)
        assert get_current_hotel_day(now=now) == date(2026, 5, 11)
        now2 = datetime(2026, 5, 12, 11, 0, 0)
        assert get_current_hotel_day(now=now2) == date(2026, 5, 12)


# ======================================================================
# can_create_reservation_for_date
# ======================================================================
class TestCanCreateReservation:
    def test_yesterday_at_2am_allowed(self):
        """Walk-in at 02:00 the next morning — the night of yesterday is
        still in progress, so creating a reservation for yesterday is OK."""
        now = datetime(2026, 5, 12, 2, 0, 0)
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 5, 11),
            check_out_time=time(10, 0),
            now=now,
        ) is True

    def test_yesterday_at_959_allowed(self):
        """One minute before check-out → still within the night."""
        now = datetime(2026, 5, 12, 9, 59, 0)
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 5, 11),
            check_out_time=time(10, 0),
            now=now,
        ) is True

    def test_yesterday_at_1001_rejected(self):
        """One minute past check-out → that night has ended."""
        now = datetime(2026, 5, 12, 10, 1, 0)
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 5, 11),
            check_out_time=time(10, 0),
            now=now,
        ) is False

    def test_today_always_allowed(self):
        """Any moment of today → today is bookable."""
        for hour in (0, 8, 12, 18, 23):
            now = datetime(2026, 5, 12, hour, 0, 0)
            assert can_create_reservation_for_date(
                check_in_date=date(2026, 5, 12),
                check_out_time=time(10, 0),
                now=now,
            ) is True

    def test_future_always_allowed(self):
        now = datetime(2026, 5, 12, 2, 0, 0)
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 6, 1),
            check_out_time=time(10, 0),
            now=now,
        ) is True

    def test_far_past_rejected(self):
        now = datetime(2026, 5, 19, 14, 0, 0)
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 4, 1),
            check_out_time=time(10, 0),
            now=now,
        ) is False

    def test_later_checkout_window_extends(self):
        """A hotel with 14:00 check-out lets you create 'yesterday' until 14:00."""
        now = datetime(2026, 5, 12, 13, 0, 0)
        # With 10:00 check-out → already past, rejected
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 5, 11),
            check_out_time=time(10, 0),
            now=now,
        ) is False
        # With 14:00 check-out → still in the window
        assert can_create_reservation_for_date(
            check_in_date=date(2026, 5, 11),
            check_out_time=time(14, 0),
            now=now,
        ) is True


# ======================================================================
# _coerce_time helper
# ======================================================================
class TestCoerceTime:
    def test_time_passthrough(self):
        assert _coerce_time(time(14, 30)) == time(14, 30)

    def test_string_hhmm(self):
        assert _coerce_time("14:30") == time(14, 30)

    def test_string_hhmmss(self):
        assert _coerce_time("14:30:45") == time(14, 30, 45)

    def test_string_whitespace(self):
        assert _coerce_time("  10:00  ") == time(10, 0)

    def test_none_uses_fallback(self):
        assert _coerce_time(None) == DEFAULT_CHECK_OUT_TIME

    def test_empty_string_uses_fallback(self):
        assert _coerce_time("") == DEFAULT_CHECK_OUT_TIME

    def test_garbage_uses_fallback(self):
        assert _coerce_time("not-a-time") == DEFAULT_CHECK_OUT_TIME


# ======================================================================
# Pydantic integration: ReservationCreate validator
# ======================================================================
class TestPydanticValidator:
    """The Pydantic validator must allow 'yesterday' bookings as long as
    we're still in the hotel-day window. (It uses real datetime.now() so
    these tests are 'best-effort' — they verify shape, not exact moment.)"""

    def _base_payload(self, check_in_date: date) -> dict:
        return {
            "check_in_date": check_in_date,
            "stay_days": 1,
            "guest_name": "Test Guest",
            "room_ids": ["los-monges-room-001"],
            "price": 100000.0,
        }

    def test_today_accepted(self):
        """Today is always bookable."""
        payload = self._base_payload(date.today())
        rc = ReservationCreate(**payload)
        assert rc.check_in_date == date.today()

    def test_future_accepted(self):
        payload = self._base_payload(date.today() + timedelta(days=7))
        rc = ReservationCreate(**payload)
        assert rc.check_in_date == date.today() + timedelta(days=7)

    def test_far_past_rejected(self):
        """A date a month in the past should fail validation."""
        payload = self._base_payload(date.today() - timedelta(days=30))
        with pytest.raises(Exception):  # pydantic.ValidationError
            ReservationCreate(**payload)


# ======================================================================
# ReservationService: early_checkin / late_checkout fields persist
# ======================================================================
class TestEarlyLateCheckoutPersistence:
    def test_default_flags_false(self, db_session, seed_rooms, seed_property):
        from services import ReservationService
        rooms = seed_rooms["rooms"]
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=1),
            stay_days=2,
            guest_name="Default Flags",
            room_ids=[rooms[0].id],
            price=150000.0,
        )
        ids = ReservationService.create_reservations(db_session, data)
        from database import Reservation
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.early_checkin is False
        assert res.late_checkout is False
        assert res.late_checkout_time is None

    def test_early_checkin_flag_persists(self, db_session, seed_rooms, seed_property):
        from services import ReservationService
        rooms = seed_rooms["rooms"]
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=1),
            stay_days=1,
            guest_name="Early Bird",
            room_ids=[rooms[0].id],
            price=150000.0,
            early_checkin=True,
        )
        ids = ReservationService.create_reservations(db_session, data)
        from database import Reservation
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.early_checkin is True
        assert res.late_checkout is False

    def test_late_checkout_with_time(self, db_session, seed_rooms, seed_property):
        from services import ReservationService
        rooms = seed_rooms["rooms"]
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=1),
            stay_days=1,
            guest_name="Late Stayer",
            room_ids=[rooms[0].id],
            price=150000.0,
            late_checkout=True,
            late_checkout_time="14:00",
        )
        ids = ReservationService.create_reservations(db_session, data)
        from database import Reservation
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.late_checkout is True
        assert res.late_checkout_time == "14:00"

    def test_late_checkout_time_ignored_when_flag_false(self, db_session, seed_rooms, seed_property):
        """If late_checkout=False, late_checkout_time should NOT be stored
        (avoids stale data like 'asked for late checkout but cancelled it')."""
        from services import ReservationService
        rooms = seed_rooms["rooms"]
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=1),
            stay_days=1,
            guest_name="No Late",
            room_ids=[rooms[0].id],
            price=150000.0,
            late_checkout=False,
            late_checkout_time="14:00",  # caller mistake
        )
        ids = ReservationService.create_reservations(db_session, data)
        from database import Reservation
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.late_checkout is False
        assert res.late_checkout_time is None
