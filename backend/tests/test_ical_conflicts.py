"""
Tests for v1.5.0 — Conflict detection during iCal sync.

When an OTA feed sends a VEVENT that overlaps with an existing reservation
on the same room, the conflict is logged + counted. The OTA reservation is
still created (OTA is authoritative — admin must investigate).
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from services.ical_service import ICalService, _check_room_conflict
from database import ICalFeed, Reservation


def _make_ics(events):
    import icalendar
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")
    for uid, start, end, summary in events:
        ev = icalendar.Event()
        ev.add("uid", uid)
        ev.add("dtstart", start)
        ev.add("dtend", end)
        ev.add("summary", summary)
        cal.add_component(ev)
    return cal.to_ical().decode()


def _make_feed(db, room_id, source="Booking.com"):
    feed = ICalFeed(
        room_id=room_id, source=source,
        ical_url="https://example.com/feed.ics", sync_enabled=1,
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return feed


class TestConflictHelper:
    """_check_room_conflict identifies overlapping reservations on same room."""

    def test_no_conflict_different_dates(self, db_session, seed_rooms, make_reservation):
        room = seed_rooms["rooms"][0]
        make_reservation(
            room_id=room.id,
            check_in_date=date(2026, 6, 1),
            stay_days=2,
            status="Confirmada",
        )
        # Asking about 2026-06-10 → no overlap
        result = _check_room_conflict(
            db_session, room_id=room.id,
            check_in=date(2026, 6, 10),
            check_out=date(2026, 6, 12),
        )
        assert result is None

    def test_overlap_detected(self, db_session, seed_rooms, make_reservation):
        room = seed_rooms["rooms"][0]
        make_reservation(
            room_id=room.id,
            check_in_date=date(2026, 6, 1),
            stay_days=5,
            status="Confirmada",
        )
        # 2026-06-03 to 2026-06-04 overlaps with 06-01..06-06
        result = _check_room_conflict(
            db_session, room_id=room.id,
            check_in=date(2026, 6, 3),
            check_out=date(2026, 6, 4),
        )
        assert result is not None

    def test_excludes_same_uid(self, db_session, seed_rooms, make_reservation):
        room = seed_rooms["rooms"][0]
        existing = make_reservation(
            room_id=room.id,
            check_in_date=date(2026, 6, 1),
            stay_days=3,
            status="Confirmada",
        )
        existing.external_id = "uid-self"
        db_session.commit()

        # Re-syncing same UID with same dates → not a conflict
        result = _check_room_conflict(
            db_session, room_id=room.id,
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 4),
            excluding_external_id="uid-self",
        )
        assert result is None

    def test_skips_cancelled_reservations(self, db_session, seed_rooms, make_reservation):
        room = seed_rooms["rooms"][0]
        make_reservation(
            room_id=room.id,
            check_in_date=date(2026, 6, 1),
            stay_days=5,
            status="Cancelada",
        )
        result = _check_room_conflict(
            db_session, room_id=room.id,
            check_in=date(2026, 6, 3),
            check_out=date(2026, 6, 4),
        )
        assert result is None  # Cancelled doesn't block


class TestSyncDetectsConflicts:
    """sync_feed counts conflicts and still creates the OTA reservation."""

    def test_conflict_counted_but_reservation_created(
        self, db_session, seed_rooms, make_reservation
    ):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id, source="Booking.com")

        # Pre-existing direct reservation
        make_reservation(
            room_id=room.id,
            check_in_date=date.today() + timedelta(days=10),
            stay_days=3,
            status="Confirmada",
        )

        # OTA sends overlapping event
        ota_start = date.today() + timedelta(days=11)
        ics = _make_ics([
            ("uid-conflict", ota_start, ota_start + timedelta(days=2), "OTA Guest"),
        ])

        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=ics, status_code=200, raise_for_status=lambda: None)
            result = ICalService.sync_feed(db_session, feed_id=feed.id)

        # Conflict detected and counted
        assert result["conflicts"] == 1
        # OTA reservation still created (OTA is authoritative)
        assert result["created"] == 1
        ota_res = db_session.query(Reservation).filter(
            Reservation.external_id == "uid-conflict"
        ).first()
        assert ota_res is not None

    def test_no_conflict_when_dates_dont_overlap(
        self, db_session, seed_rooms, make_reservation
    ):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id, source="Booking.com")
        make_reservation(
            room_id=room.id,
            check_in_date=date.today() + timedelta(days=5),
            stay_days=2,
            status="Confirmada",
        )

        ics = _make_ics([(
            "uid-far",
            date.today() + timedelta(days=30),
            date.today() + timedelta(days=32),
            "Far Guest",
        )])

        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=ics, status_code=200, raise_for_status=lambda: None)
            result = ICalService.sync_feed(db_session, feed_id=feed.id)

        assert result["conflicts"] == 0
        assert result["created"] == 1
