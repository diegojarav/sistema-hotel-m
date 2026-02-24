"""
Phase 3 — API endpoint tests for Guests/CheckIn (mobile/Next.js path).
"""

from datetime import date, timedelta


class TestCreateCheckin:
    def test_success(self, client, auth_headers_admin, seed_rooms):
        r = client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "API García",
            "first_name": "Juan",
            "document_number": "API001",
            "nationality": "Paraguaya",
        }, headers=auth_headers_admin)
        assert r.status_code in (200, 201)

    def test_unauthenticated(self, client, seed_rooms):
        r = client.post("/api/v1/guests", json={
            "last_name": "Test",
            "document_number": "X",
        })
        assert r.status_code == 401


class TestSearchCheckins:
    def test_search(self, client, auth_headers_admin, seed_rooms):
        # Create a checkin first
        client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "Searchable",
            "document_number": "SEARCH01",
        }, headers=auth_headers_admin)

        r = client.get("/api/v1/guests/search?q=Searchable",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        results = r.json()
        assert len(results) >= 1


class TestGuestNames:
    def test_returns_list(self, client, auth_headers_admin, seed_rooms):
        client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "NameTest",
            "first_name": "One",
            "document_number": "NAME01",
        }, headers=auth_headers_admin)

        r = client.get("/api/v1/guests/names",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestBillingProfiles:
    def test_returns_list(self, client, auth_headers_admin, seed_rooms):
        client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "Billing",
            "document_number": "BILL01",
            "billing_name": "Corp SA",
            "billing_ruc": "12345-6",
        }, headers=auth_headers_admin)

        r = client.get("/api/v1/guests/billing-profiles",
                        headers=auth_headers_admin)
        assert r.status_code == 200


class TestUnlinkedReservations:
    def test_returns_list(self, client, auth_headers_admin, seed_rooms, make_reservation):
        make_reservation(guest_name="Unlinked API")
        r = client.get("/api/v1/guests/unlinked-reservations",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestGetCheckinDetail:
    def test_found(self, client, auth_headers_admin, seed_rooms):
        resp = client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "Detail",
            "document_number": "DET001",
        }, headers=auth_headers_admin)
        cid = resp.json()["id"]

        r = client.get(f"/api/v1/guests/{cid}",
                        headers=auth_headers_admin)
        assert r.status_code == 200

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/guests/99999",
                        headers=auth_headers_admin)
        assert r.status_code == 404


class TestUpdateCheckin:
    def test_success(self, client, auth_headers_admin, seed_rooms):
        resp = client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "Original",
            "first_name": "Name",
            "document_number": "UPD001",
        }, headers=auth_headers_admin)
        cid = resp.json()["id"]

        r = client.put(f"/api/v1/guests/{cid}", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "Updated",
            "first_name": "Name",
            "document_number": "UPD001",
        }, headers=auth_headers_admin)
        assert r.status_code == 200

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.put("/api/v1/guests/99999", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "Ghost",
            "document_number": "GHOST",
        }, headers=auth_headers_admin)
        assert r.status_code == 404


class TestBillingHistory:
    def test_found(self, client, auth_headers_admin, seed_rooms):
        client.post("/api/v1/guests", json={
            "room_id": seed_rooms["rooms"][0].id,
            "last_name": "BillingTest",
            "document_number": "BILLHIST99",
            "billing_name": "Corp SA",
            "billing_ruc": "99999-0",
        }, headers=auth_headers_admin)

        r = client.get("/api/v1/guests/billing-history/BILLHIST99",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_empty(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/guests/billing-history/NONEXISTENT99",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        assert r.json() == []
