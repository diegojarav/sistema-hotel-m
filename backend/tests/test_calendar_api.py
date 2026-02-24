"""
Phase 4 — API endpoint tests for Calendar.
"""

from datetime import date, timedelta


class TestCalendarEvents:
    def test_empty(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/calendar/events?year=2026&month=7",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_with_data(self, client, auth_headers_admin, seed_rooms, make_reservation):
        make_reservation(
            check_in_date=date(2026, 7, 10),
            stay_days=3,
            guest_name="Calendar Guest",
        )
        r = client.get("/api/v1/calendar/events?year=2026&month=7",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        events = r.json()
        assert len(events) >= 1


class TestOccupancyMap:
    def test_empty(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/calendar/occupancy?year=2026&month=9",
                        headers=auth_headers_admin)
        assert r.status_code == 200

    def test_with_data(self, client, auth_headers_admin, seed_rooms, make_reservation):
        make_reservation(
            check_in_date=date(2026, 8, 15),
            stay_days=2,
            guest_name="Occupancy Guest",
        )
        r = client.get("/api/v1/calendar/occupancy?year=2026&month=8",
                        headers=auth_headers_admin)
        assert r.status_code == 200


class TestTodaySummary:
    def test_empty(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/calendar/summary",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert "total_habitaciones" in data
        assert "libres" in data
