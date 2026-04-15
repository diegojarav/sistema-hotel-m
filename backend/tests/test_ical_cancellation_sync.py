"""
Tests for v1.5.0 — Cancellation sync detection.

When a UID is present in our DB but disappears from the OTA feed in a sync,
the local reservation is flagged for review (needs_review=True).
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

from services.ical_service import ICalService
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
        room_id=room_id,
        source=source,
        ical_url="https://example.com/feed.ics",
        sync_enabled=1,
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return feed


class TestCancellationSync:
    """UIDs that disappear from feed → reservation flagged for review."""

    def test_disappeared_uid_flags_for_review(self, db_session, seed_rooms):
        """Sync once with UID present, then sync again without it → flagged."""
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id, source="Booking.com")

        future = date.today() + timedelta(days=10)
        ics_with_event = _make_ics([
            ("uid-keep-me", future, future + timedelta(days=2), "Guest A"),
        ])

        # First sync: creates the reservation
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                text=ics_with_event, status_code=200,
                raise_for_status=lambda: None,
            )
            ICalService.sync_feed(db_session, feed_id=feed.id)

        res = db_session.query(Reservation).filter(
            Reservation.external_id == "uid-keep-me"
        ).first()
        assert res is not None
        assert res.needs_review is False

        # Second sync: empty feed → UID disappears
        empty_ics = _make_ics([])
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                text=empty_ics, status_code=200,
                raise_for_status=lambda: None,
            )
            result = ICalService.sync_feed(db_session, feed_id=feed.id)

        assert result["flagged_for_review"] == 1
        db_session.refresh(res)
        assert res.needs_review is True
        assert "desaparecio" in (res.review_reason or "").lower()

    def test_reappeared_uid_clears_flag(self, db_session, seed_rooms):
        """If UID reappears in feed after being flagged → flag cleared."""
        room = seed_rooms["rooms"][0]
        feed = _make_feed(db_session, room.id, source="Booking.com")
        future = date.today() + timedelta(days=10)
        ics_with = _make_ics([("uid-flicker", future, future + timedelta(days=1), "Guest")])

        # Create
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=ics_with, status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        # Disappear → flagged
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=_make_ics([]), status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        res = db_session.query(Reservation).filter(Reservation.external_id == "uid-flicker").first()
        assert res.needs_review is True

        # Reappear → flag cleared
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=ics_with, status_code=200, raise_for_status=lambda: None)
            ICalService.sync_feed(db_session, feed_id=feed.id)

        db_session.refresh(res)
        assert res.needs_review is False
        assert res.review_reason is None

    def test_disappeared_only_affects_same_source(self, db_session, seed_rooms):
        """A reservation from Airbnb is NOT flagged when a Booking.com feed is missing UIDs."""
        room = seed_rooms["rooms"][0]
        booking_feed = _make_feed(db_session, room.id, source="Booking.com")

        # Manually create an Airbnb reservation on the same room
        airbnb_res = Reservation(
            id="0009999",
            check_in_date=date.today() + timedelta(days=20),
            stay_days=1,
            guest_name="Airbnb Guest",
            room_id=room.id,
            source="Airbnb",
            external_id="airbnb-uid-1",
            status="Confirmada",
            price=100000,
            reserved_by="Airbnb",
            received_by="iCal Sync",
            property_id="los-monges",
        )
        db_session.add(airbnb_res)
        db_session.commit()

        # Sync the Booking.com feed with empty payload
        with patch("services.ical_service.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=_make_ics([]), status_code=200, raise_for_status=lambda: None)
            result = ICalService.sync_feed(db_session, feed_id=booking_feed.id)

        # Airbnb reservation must NOT be flagged
        db_session.refresh(airbnb_res)
        assert airbnb_res.needs_review is False
        assert result["flagged_for_review"] == 0


class TestReviewEndpoints:
    """API endpoints for managing flagged reservations."""

    def test_list_needs_review_empty(self, client, auth_headers_admin):
        resp = client.get("/api/v1/reservations/needs-review", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_needs_review_with_flagged(
        self, client, auth_headers_admin, db_session, make_reservation
    ):
        res = make_reservation(price=100000.0, status="Confirmada")
        res.needs_review = True
        res.review_reason = "Test reason"
        db_session.commit()

        resp = client.get("/api/v1/reservations/needs-review", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == res.id
        assert data[0]["review_reason"] == "Test reason"

    def test_acknowledge_review_clears_flag(
        self, client, auth_headers_admin, db_session, make_reservation
    ):
        res = make_reservation(price=100000.0, status="Confirmada")
        res.needs_review = True
        res.review_reason = "Test"
        db_session.commit()

        resp = client.post(
            f"/api/v1/reservations/{res.id}/acknowledge-review",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200

        db_session.refresh(res)
        assert res.needs_review is False
        assert res.review_reason is None

    def test_acknowledge_review_not_found(self, client, auth_headers_admin):
        resp = client.post(
            "/api/v1/reservations/NOEXISTE/acknowledge-review",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 404

    def test_confirm_ota_cancellation_sets_cancelada(
        self, client, auth_headers_admin, db_session, make_reservation
    ):
        res = make_reservation(price=100000.0, status="Confirmada")
        res.needs_review = True
        res.review_reason = "OTA removed UID"
        db_session.commit()

        resp = client.post(
            f"/api/v1/reservations/{res.id}/confirm-ota-cancellation",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200

        db_session.refresh(res)
        assert res.status in ("Cancelada", "CANCELADA")
        assert res.needs_review is False
