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


class TestICalEdgeCases:
    @patch("services.ical_service.requests.get")
    def test_malformed_ical(self, mock_get, db_session, seed_rooms):
        mock_resp = MagicMock()
        mock_resp.text = "NOT A VALID ICAL AT ALL"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/bad.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.sync_feed(db_session, feed.id)

        assert len(result.get("errors", [])) >= 1

    @patch("services.ical_service.requests.get")
    def test_missing_dtstart(self, mock_get, db_session, seed_rooms):
        """VEVENT without DTSTART should be skipped."""
        import icalendar
        cal = icalendar.Calendar()
        cal.add("prodid", "-//Test//")
        cal.add("version", "2.0")
        event = icalendar.Event()
        event.add("uid", "uid-no-dtstart")
        event.add("summary", "No Start")
        # Deliberately no DTSTART or DTEND
        cal.add_component(event)

        mock_resp = MagicMock()
        mock_resp.text = cal.to_ical().decode()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/nostart.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.sync_feed(db_session, feed.id)
        assert result["created"] == 0

    @patch("services.ical_service.requests.get")
    def test_zero_stay_days(self, mock_get, db_session, seed_rooms):
        """DTSTART == DTEND → 0 stay days → skipped."""
        ics = _make_ics([
            ("uid-zero", date(2026, 9, 1), date(2026, 9, 1), "Zero Stay"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/zero.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.sync_feed(db_session, feed.id)
        assert result["created"] == 0

    @patch("services.ical_service.requests.get")
    def test_datetime_normalization(self, mock_get, db_session, seed_rooms):
        """datetime objects should be normalized to date."""
        from datetime import datetime as dt
        ics = _make_ics([
            ("uid-datetime", dt(2026, 9, 1, 14, 0), dt(2026, 9, 3, 11, 0), "DT Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/datetime.ics",
        )
        feed = db_session.query(ICalFeed).first()
        result = ICalService.sync_feed(db_session, feed.id)
        assert result["created"] == 1

        res = db_session.query(Reservation).filter(
            Reservation.external_id == "uid-datetime"
        ).first()
        assert res is not None
        assert res.check_in_date == date(2026, 9, 1)
        assert res.stay_days == 2

    @patch("services.ical_service.requests.get")
    def test_update_existing(self, mock_get, db_session, seed_rooms):
        """Sync same UID twice with different dates → updated=1."""
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/update.ics",
        )
        feed = db_session.query(ICalFeed).first()

        # First sync: Aug 1-3
        ics1 = _make_ics([
            ("uid-update-test", date(2026, 8, 1), date(2026, 8, 3), "Update Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics1
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        ICalService.sync_feed(db_session, feed.id)

        # Second sync: same UID, different dates Aug 5-8
        ics2 = _make_ics([
            ("uid-update-test", date(2026, 8, 5), date(2026, 8, 8), "Update Guest"),
        ])
        mock_resp2 = MagicMock()
        mock_resp2.text = ics2
        mock_resp2.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp2
        result = ICalService.sync_feed(db_session, feed.id)

        assert result["updated"] == 1
        res = db_session.query(Reservation).filter(
            Reservation.external_id == "uid-update-test"
        ).first()
        assert res.check_in_date == date(2026, 8, 5)
        assert res.stay_days == 3


class TestBackgroundSync:
    @patch("services.ical_service.requests.get")
    def test_aggregation(self, mock_get, db_session, seed_rooms):
        """2 enabled feeds → totals aggregated."""
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/agg1.ics",
        )
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][1].id,
            source="Airbnb",
            ical_url="https://example.com/agg2.ics",
        )

        ics = _make_ics([
            ("uid-agg-1", date(2026, 10, 1), date(2026, 10, 3), "Agg Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = ICalService.sync_all_feeds(db_session)
        assert result["feeds_synced"] == 2
        assert result["created"] >= 1

    @patch("services.ical_service.requests.get")
    def test_skips_disabled(self, mock_get, db_session, seed_rooms):
        """Disabled feed should not be synced."""
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/en.ics",
        )
        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][1].id,
            source="Airbnb",
            ical_url="https://example.com/dis.ics",
        )
        # Disable the second feed
        feed2 = db_session.query(ICalFeed).filter(
            ICalFeed.room_id == seed_rooms["rooms"][1].id
        ).first()
        ICalService.toggle_feed(db_session, feed2.id, enabled=False)

        ics = _make_ics([
            ("uid-skip", date(2026, 10, 5), date(2026, 10, 7), "Skip Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = ICalService.sync_all_feeds(db_session)
        assert result["feeds_synced"] == 1

    @patch("services.ical_service.requests.get")
    def test_standalone(self, mock_get, db_session, seed_rooms):
        """standalone sync creates its own session — verify no crash."""
        import services.ical_service as ical_module

        ICalService.create_feed(
            db_session,
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/standalone.ics",
        )

        ics = _make_ics([
            ("uid-standalone", date(2026, 11, 1), date(2026, 11, 3), "Standalone Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Patch the session_factory used by standalone method
        from tests.conftest import TestingSessionLocal
        original = ical_module.session_factory
        ical_module.session_factory = TestingSessionLocal
        try:
            ICalService.sync_all_feeds_standalone()
        finally:
            ical_module.session_factory = original


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
