"""
Phase 4 — API endpoint tests for Settings.
"""


class TestGetHotelName:
    def test_public(self, client, seed_users):
        """Hotel name endpoint is public — no auth needed."""
        r = client.get("/api/v1/settings/hotel-name")
        assert r.status_code == 200


class TestSetHotelName:
    def test_admin(self, client, auth_headers_admin):
        r = client.post("/api/v1/settings/hotel-name",
                         json={"name": "Test Hotel"},
                         headers=auth_headers_admin)
        assert r.status_code == 200

    def test_non_admin(self, client, auth_headers_recep):
        r = client.post("/api/v1/settings/hotel-name",
                         json={"name": "Hack"},
                         headers=auth_headers_recep)
        assert r.status_code == 403


class TestParkingCapacity:
    def test_get(self, client, auth_headers_admin):
        r = client.get("/api/v1/settings/parking-capacity",
                        headers=auth_headers_admin)
        assert r.status_code == 200

    def test_set_admin(self, client, auth_headers_admin):
        r = client.post("/api/v1/settings/parking-capacity",
                         json={"capacity": 10},
                         headers=auth_headers_admin)
        assert r.status_code == 200

    def test_set_non_admin(self, client, auth_headers_recep):
        r = client.post("/api/v1/settings/parking-capacity",
                         json={"capacity": 10},
                         headers=auth_headers_recep)
        assert r.status_code == 403


class TestPropertySettings:
    def test_get(self, client, auth_headers_admin, seed_property):
        r = client.get("/api/v1/settings/property-settings",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert "check_in_start" in data
        assert "check_out_time" in data
