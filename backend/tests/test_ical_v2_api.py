"""
Tests for v1.5.0 — Channel Manager v2 API extensions.

Covers:
- Expanded source validation (5 sources accepted, unknown rejected)
- URL validation
- New endpoints exposed correctly
"""

import pytest


class TestExpandedSourceValidation:
    """All 5 OTA sources are accepted; unknown ones rejected."""

    def test_booking_accepted(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Booking.com",
                "ical_url": "https://example.com/feed.ics",
            },
        )
        assert resp.status_code == 201

    def test_airbnb_accepted(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Airbnb",
                "ical_url": "https://example.com/airbnb.ics",
            },
        )
        assert resp.status_code == 201

    def test_vrbo_accepted(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Vrbo",
                "ical_url": "https://example.com/vrbo.ics",
            },
        )
        assert resp.status_code == 201

    def test_expedia_accepted(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Expedia",
                "ical_url": "https://example.com/expedia.ics",
            },
        )
        assert resp.status_code == 201

    def test_custom_accepted(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Custom",
                "ical_url": "https://my-own-site.com/feed.ics",
            },
        )
        assert resp.status_code == 201

    def test_unknown_source_rejected(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Trivago",
                "ical_url": "https://example.com/feed.ics",
            },
        )
        assert resp.status_code == 400
        assert "source" in resp.json()["detail"].lower()

    def test_invalid_url_rejected(self, client, auth_headers_admin, seed_rooms):
        resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Booking.com",
                "ical_url": "not-a-url",
            },
        )
        assert resp.status_code == 400


class TestHealthEndpoint:
    """Health endpoint returns proper structure."""

    def test_health_for_unknown_feed(self, client, auth_headers_admin):
        resp = client.get(
            "/api/v1/ical/feeds/99999/health",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 404

    def test_health_for_existing_feed(self, client, auth_headers_admin, seed_rooms):
        # Create a feed
        create_resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Booking.com",
                "ical_url": "https://example.com/feed.ics",
            },
        )
        feed_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/v1/ical/feeds/{feed_id}/health",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_sync_status"] == "NEVER"
        assert data["health_badge"] == "unknown"
        assert data["consecutive_failures"] == 0

    def test_logs_endpoint_empty(self, client, auth_headers_admin, seed_rooms):
        create_resp = client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Airbnb",
                "ical_url": "https://example.com/feed.ics",
            },
        )
        feed_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/v1/ical/feeds/{feed_id}/logs",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestFeedListIncludesHealth:
    """GET /feeds returns the new health fields."""

    def test_list_includes_health_fields(self, client, auth_headers_admin, seed_rooms):
        client.post(
            "/api/v1/ical/feeds",
            headers=auth_headers_admin,
            json={
                "room_id": seed_rooms["rooms"][0].id,
                "source": "Booking.com",
                "ical_url": "https://example.com/feed.ics",
            },
        )

        resp = client.get("/api/v1/ical/feeds", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "last_sync_status" in data[0]
        assert "consecutive_failures" in data[0]
        assert "health_badge" in data[0]
        assert data[0]["health_badge"] == "unknown"
