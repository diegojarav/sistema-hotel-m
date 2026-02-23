"""
Phase 5 — Service-layer tests for ICalService with mocked HTTP.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from services.ical_service import ICalService
from database import ICalFeed, Reservation


def _make_ics(events):
    """Build a valid .ics string from list of (uid, start, end, summary)."""
    import icalendar
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")
    for uid, start, end, summary in events:
        event = icalendar.Event()
        event.add("uid", uid)
        event.add("dtstart", start)
        event.add("dtend", end)
        event.add("summary", summary)
        cal.add_component(event)
    return cal.to_ical().decode()


class TestFeedCRUD:
    def test_create_feed(self, db_session, seed_rooms):
        result = ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/feed.ics",
        )
        assert result is not None
        feed = db_session.query(ICalFeed).first()
        assert feed is not None
        assert feed.source == "Booking.com"

    def test_get_all_feeds(self, db_session, seed_rooms):
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/1.ics",
        )
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][1].id,
            source="Airbnb",
            ical_url="https://example.com/2.ics",
        )
        feeds = ICalService.get_all_feeds(db_session)
        assert len(feeds) == 2

    def test_delete_feed(self, db_session, seed_rooms):
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/del.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.delete_feed(db_session, feed.id)
        assert result is True
        assert db_session.query(ICalFeed).count() == 0

    def test_delete_not_found(self, db_session):
        result = ICalService.delete_feed(db_session, 99999)
        assert result is False

    def test_toggle_feed(self, db_session, seed_rooms):
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/toggle.ics",
        )
        feed = db_session.query(ICalFeed).first()

        ICalService.toggle_feed(db_session, feed.id, enabled=False)
        db_session.refresh(feed)
        assert feed.sync_enabled == 0

        ICalService.toggle_feed(db_session, feed.id, enabled=True)
        db_session.refresh(feed)
        assert feed.sync_enabled == 1


class TestSyncFeed:
    @patch("services.ical_service.requests.get")
    def test_creates_reservation(self, mock_get, db_session, seed_rooms):
        ics = _make_ics([
            ("uid-001", date(2026, 8, 1), date(2026, 8, 3), "CLOSED - Test Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/sync.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.sync_feed(db_session, feed.id)

        assert result["created"] >= 1
        res = db_session.query(Reservation).filter(
            Reservation.external_id == "uid-001"
        ).first()
        assert res is not None

    @patch("services.ical_service.requests.get")
    def test_deduplication(self, mock_get, db_session, seed_rooms):
        ics = _make_ics([
            ("uid-dup", date(2026, 9, 1), date(2026, 9, 2), "CLOSED - Dup Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/dup.ics",
        )
        feed = db_session.query(ICalFeed).first()

        ICalService.sync_feed(db_session, feed.id)
        ICalService.sync_feed(db_session, feed.id)

        count = db_session.query(Reservation).filter(
            Reservation.external_id == "uid-dup"
        ).count()
        assert count == 1

    @patch("services.ical_service.requests.get")
    def test_bad_url_returns_errors(self, mock_get, db_session, seed_rooms):
        import requests as req_lib
        mock_get.side_effect = req_lib.exceptions.ConnectionError("Connection refused")

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://bad-url.com/fail.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.sync_feed(db_session, feed.id)

        assert "error" in result or result.get("errors")


class TestGenerateIcal:
    def test_for_room(self, db_session, seed_rooms, make_reservation):
        make_reservation(
            check_in_date=date(2026, 10, 1),
            stay_days=2,
            guest_name="iCal Guest",
            room_id=seed_rooms["rooms"][0].id,
        )
        ics = ICalService.generate_ical_for_room(
            db_session, seed_rooms["rooms"][0].id
        )
        assert "VEVENT" in ics
        assert "iCal Guest" in ics or "CLOSED" in ics

    def test_all_rooms(self, db_session, seed_rooms, make_reservation):
        make_reservation(
            check_in_date=date(2026, 10, 5),
            stay_days=1,
            guest_name="All Rooms Guest",
        )
        ics = ICalService.generate_ical_all_rooms(db_session)
        assert "VCALENDAR" in ics
