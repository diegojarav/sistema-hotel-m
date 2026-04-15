"""
Tests for v1.5.0 — ICalSyncLog audit trail.

Each sync attempt writes one log row. Logs are pruned to keep last 100 per feed.
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

from services.ical_service import ICalService
from services.ical_sync_log_service import ICalSyncLogService
from database import ICalFeed, ICalSyncLog


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


class TestSyncLogRecording:
    """Each sync attempt creates exactly one ICalSyncLog row."""

    def test_successful_sync_creates_log(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        future = date.today() + timedelta(days=5)
        ics = _make_ics([("uid-1", future, future + timedelta(days=1), "Guest")])

        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=ics, status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        logs = db_session.query(ICalSyncLog).filter(ICalSyncLog.feed_id == feed.id).all()
        assert len(logs) == 1
        assert logs[0].status == "OK"
        assert logs[0].created_count == 1
        assert logs[0].duration_ms >= 0

    def test_failed_sync_creates_error_log(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        import requests
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection refused")
            ICalService.sync_feed(db_session, feed_id=feed.id)

        logs = db_session.query(ICalSyncLog).filter(ICalSyncLog.feed_id == feed.id).all()
        assert len(logs) == 1
        assert logs[0].status == "ERROR"
        assert "Connection refused" in (logs[0].error_message or "")

    def test_log_records_counts(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        future = date.today() + timedelta(days=5)
        ics = _make_ics([
            ("uid-1", future, future + timedelta(days=1), "Guest 1"),
            ("uid-2", future + timedelta(days=5), future + timedelta(days=6), "Guest 2"),
        ])

        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=ics, status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        log = db_session.query(ICalSyncLog).filter(ICalSyncLog.feed_id == feed.id).first()
        assert log.created_count == 2
        assert log.updated_count == 0


class TestSyncLogPruning:
    """The keep-last-N pruning prevents unbounded growth."""

    def test_prune_keeps_last_n(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        # Manually insert 110 log rows
        for i in range(110):
            db_session.add(ICalSyncLog(
                feed_id=feed.id,
                attempted_at=datetime.now() - timedelta(minutes=i),
                status="OK",
                duration_ms=10,
            ))
        db_session.commit()

        assert db_session.query(ICalSyncLog).filter(ICalSyncLog.feed_id == feed.id).count() == 110

        deleted = ICalSyncLogService.prune(db_session, feed_id=feed.id, keep=100)
        assert deleted == 10
        assert db_session.query(ICalSyncLog).filter(ICalSyncLog.feed_id == feed.id).count() == 100

    def test_prune_noop_when_under_threshold(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        for i in range(50):
            db_session.add(ICalSyncLog(
                feed_id=feed.id,
                attempted_at=datetime.now() - timedelta(minutes=i),
                status="OK",
                duration_ms=10,
            ))
        db_session.commit()

        deleted = ICalSyncLogService.prune(db_session, feed_id=feed.id, keep=100)
        assert deleted == 0


class TestSyncLogQueries:
    """list_for_feed returns newest-first and respects limit."""

    def test_list_for_feed_newest_first(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)

        old = ICalSyncLog(
            feed_id=feed.id, attempted_at=datetime.now() - timedelta(hours=2),
            status="OK", duration_ms=10,
        )
        new = ICalSyncLog(
            feed_id=feed.id, attempted_at=datetime.now(),
            status="ERROR", duration_ms=20, error_message="boom",
        )
        db_session.add_all([old, new])
        db_session.commit()

        logs = ICalSyncLogService.list_for_feed(db_session, feed_id=feed.id, limit=10)
        assert len(logs) == 2
        assert logs[0].status == "ERROR"  # newest first
        assert logs[1].status == "OK"

    def test_list_for_feed_respects_limit(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id)
        for i in range(15):
            db_session.add(ICalSyncLog(
                feed_id=feed.id,
                attempted_at=datetime.now() - timedelta(minutes=i),
                status="OK", duration_ms=5,
            ))
        db_session.commit()

        logs = ICalSyncLogService.list_for_feed(db_session, feed_id=feed.id, limit=5)
        assert len(logs) == 5


class TestSyncLogEndpoint:
    """API endpoint /feeds/{id}/logs returns the data."""

    def test_logs_endpoint_returns_data(
        self, client, auth_headers_admin, db_session, seed_rooms
    ):
        feed = _make_feed(db_session, seed_rooms["rooms"][0].id)
        db_session.add(ICalSyncLog(
            feed_id=feed.id,
            attempted_at=datetime.now(),
            status="OK",
            created_count=2,
            updated_count=1,
            duration_ms=120,
        ))
        db_session.commit()

        resp = client.get(
            f"/api/v1/ical/feeds/{feed.id}/logs",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "OK"
        assert data[0]["created_count"] == 2

    def test_health_endpoint(
        self, client, auth_headers_admin, db_session, seed_rooms
    ):
        feed = _make_feed(db_session, seed_rooms["rooms"][0].id)
        feed.last_sync_status = "OK"
        feed.consecutive_failures = 0
        feed.last_sync_attempted_at = datetime.now()
        db_session.commit()

        resp = client.get(
            f"/api/v1/ical/feeds/{feed.id}/health",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_sync_status"] == "OK"
        assert data["health_badge"] == "healthy"
