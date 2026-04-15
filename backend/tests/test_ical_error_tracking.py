"""
Tests for v1.5.0 — Per-feed error tracking + Discord alert threshold.

consecutive_failures increments on errors, resets on success.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from services.ical_service import ICalService
from services.ical_service import _health_badge
from database import ICalFeed


def _make_ics_ok():
    import icalendar
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Test//Test//EN")
    cal.add("version", "2.0")
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


class TestErrorTracking:
    """consecutive_failures + last_sync_status track health correctly."""

    def test_failure_increments_counter(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        assert feed.consecutive_failures == 0

        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Timeout")
            ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(feed)
        assert feed.consecutive_failures == 1
        assert feed.last_sync_status == "ERROR"
        assert "Timeout" in (feed.last_sync_error or "")

    def test_multiple_failures_keep_counting(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Down")
            for _ in range(5):
                ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(feed)
        assert feed.consecutive_failures == 5
        assert feed.last_sync_status == "ERROR"

    def test_success_resets_counter(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        # 3 failures
        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Down")
            for _ in range(3):
                ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(feed)
        assert feed.consecutive_failures == 3

        # One success
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=_make_ics_ok(), status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(feed)
        assert feed.consecutive_failures == 0
        assert feed.last_sync_status == "OK"
        assert feed.last_sync_error is None

    def test_last_sync_attempted_at_always_updated(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        assert feed.last_sync_attempted_at is None

        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("err")
            ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(feed)
        # Both success and failure must update last_sync_attempted_at
        assert feed.last_sync_attempted_at is not None


class TestHealthBadge:
    """_health_badge maps state to UI category correctly."""

    def test_unknown_when_never_synced(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        # Brand new feed: never attempted
        assert _health_badge(feed) == "unknown"

    def test_healthy_after_successful_sync(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=_make_ics_ok(), status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(feed)
        assert _health_badge(feed) == "healthy"

    def test_warning_after_one_failure(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("once")
            ICalService.sync_feed(db_session, feed_id=feed.id)
        db_session.refresh(feed)
        assert _health_badge(feed) == "warning"

    def test_error_after_three_failures(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("again")
            for _ in range(3):
                ICalService.sync_feed(db_session, feed_id=feed.id)
        db_session.refresh(feed)
        assert _health_badge(feed) == "error"


class TestDiscordAlertThreshold:
    """ERROR-level log emitted at >=3 consecutive failures (DiscordWebhookHandler routes it)."""

    def test_alert_emitted_at_threshold(self, db_session, seed_rooms, caplog):
        import logging
        caplog.set_level(logging.ERROR)
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("net")
            for _ in range(3):
                ICalService.sync_feed(db_session, feed_id=feed.id)

        # Confirm the ERROR-level alert message about consecutive failures was logged
        alert_messages = [
            r.message for r in caplog.records
            if "consecutive failures" in r.message.lower()
        ]
        assert len(alert_messages) >= 1
        assert "Booking.com" in alert_messages[0]
