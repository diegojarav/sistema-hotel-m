"""
Tier 2 — API endpoint tests for iCal feed management and export.
"""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from database import ICalFeed


def _make_ics_text(events):
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


def _create_feed(client, headers, room_id, source="Booking.com"):
    """Create an iCal feed via API and return the feed id."""
    r = client.post("/api/v1/ical/feeds", json={
        "room_id": room_id,
        "source": source,
        "ical_url": "https://example.com/test-feed.ics",
    }, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


class TestDeleteFeed:
    def test_success(self, client, auth_headers_admin, seed_rooms):
        feed_id = _create_feed(client, auth_headers_admin, seed_rooms["rooms"][0].id)
        r = client.delete(f"/api/v1/ical/feeds/{feed_id}",
                          headers=auth_headers_admin)
        assert r.status_code == 204

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.delete("/api/v1/ical/feeds/99999",
                          headers=auth_headers_admin)
        assert r.status_code == 404


class TestToggleFeed:
    def test_disable(self, client, auth_headers_admin, seed_rooms):
        feed_id = _create_feed(client, auth_headers_admin, seed_rooms["rooms"][0].id)
        r = client.patch(f"/api/v1/ical/feeds/{feed_id}/toggle",
                         json={"enabled": False},
                         headers=auth_headers_admin)
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.patch("/api/v1/ical/feeds/99999/toggle",
                         json={"enabled": False},
                         headers=auth_headers_admin)
        assert r.status_code == 404


class TestSyncAllFeeds:
    @patch("services.ical_service.requests.get")
    def test_sync_all(self, mock_get, client, auth_headers_admin, seed_rooms):
        # Create 2 feeds
        _create_feed(client, auth_headers_admin,
                     seed_rooms["rooms"][0].id, "Booking.com")
        _create_feed(client, auth_headers_admin,
                     seed_rooms["rooms"][1].id, "Airbnb")

        # Mock HTTP to return valid ICS with 1 event each
        ics = _make_ics_text([
            ("uid-sync-all", date(2026, 9, 1), date(2026, 9, 3), "Sync Guest"),
        ])
        mock_resp = MagicMock()
        mock_resp.text = ics
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        r = client.post("/api/v1/ical/feeds/sync",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert data["feeds_synced"] == 2
        assert data["created"] >= 1


class TestExportRoomIcal:
    def test_export_room(self, client, seed_rooms, make_reservation):
        room = seed_rooms["rooms"][0]
        make_reservation(
            check_in_date=date.today() + timedelta(days=5),
            stay_days=2,
            guest_name="Export Guest",
            room_id=room.id,
        )
        r = client.get(f"/api/v1/ical/export/{room.id}.ics")
        assert r.status_code == 200
        assert "text/calendar" in r.headers.get("content-type", "")
        assert "VCALENDAR" in r.text
        assert "VEVENT" in r.text
