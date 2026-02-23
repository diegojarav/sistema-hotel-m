"""
Phase 3 — API endpoint tests for Rooms (mobile/Next.js path).
"""

from datetime import date, timedelta


class TestListRooms:
    def test_returns_rooms(self, client, seed_rooms):
        r = client.get("/api/v1/rooms")
        assert r.status_code == 200
        rooms = r.json()
        assert len(rooms) == 6

    def test_pagination(self, client, seed_rooms):
        r = client.get("/api/v1/rooms?skip=0&limit=2")
        assert r.status_code == 200
        assert len(r.json()) == 2


class TestListCategories:
    def test_returns_categories(self, client, seed_rooms):
        r = client.get("/api/v1/rooms/categories")
        assert r.status_code == 200
        cats = r.json()
        assert len(cats) == 2
        names = {c["name"] for c in cats}
        assert "Estandar" in names
        assert "Suite" in names

    def test_has_price(self, client, seed_rooms):
        r = client.get("/api/v1/rooms/categories")
        cats = r.json()
        estandar = next(c for c in cats if c["name"] == "Estandar")
        assert estandar["base_price"] == 150000.0


class TestRoomStatus:
    def test_single_date(self, client, seed_rooms):
        d = (date.today() + timedelta(days=30)).isoformat()
        r = client.get(f"/api/v1/rooms/status?target_date={d}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_date_range(self, client, seed_rooms):
        ci = (date.today() + timedelta(days=30)).isoformat()
        co = (date.today() + timedelta(days=32)).isoformat()
        r = client.get(f"/api/v1/rooms/status?check_in={ci}&check_out={co}")
        assert r.status_code == 200


class TestGetRoom:
    def test_found(self, client, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        r = client.get(f"/api/v1/rooms/{room_id}")
        assert r.status_code == 200
        assert r.json()["id"] == room_id

    def test_not_found(self, client, seed_rooms):
        r = client.get("/api/v1/rooms/nonexistent-room")
        assert r.status_code == 404


class TestCreateRooms:
    def test_admin_success(self, client, auth_headers_admin, seed_rooms):
        r = client.post("/api/v1/rooms", json={
            "category_id": "los-monges-estandar",
            "quantity": 1,
            "floor": 3,
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_non_admin_forbidden(self, client, auth_headers_recep, seed_rooms):
        r = client.post("/api/v1/rooms", json={
            "category_id": "los-monges-estandar",
            "quantity": 1,
            "floor": 3,
        }, headers=auth_headers_recep)
        assert r.status_code == 403


class TestUpdateRoomStatus:
    def test_admin_success(self, client, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        r = client.patch(f"/api/v1/rooms/{room_id}/status", json={
            "status": "maintenance",
            "reason": "plumbing fix",
        }, headers=auth_headers_admin)
        assert r.status_code == 200

    def test_non_admin_forbidden(self, client, auth_headers_recep, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        r = client.patch(f"/api/v1/rooms/{room_id}/status", json={
            "status": "maintenance",
        }, headers=auth_headers_recep)
        assert r.status_code == 403


class TestDeleteRoom:
    def test_admin_success(self, client, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][-1].id  # last room
        r = client.delete(f"/api/v1/rooms/{room_id}",
                           headers=auth_headers_admin)
        assert r.status_code == 200

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.delete("/api/v1/rooms/nonexistent",
                           headers=auth_headers_admin)
        assert r.status_code == 404


class TestRoomStatistics:
    def test_returns_data(self, client, seed_rooms):
        r = client.get("/api/v1/rooms/statistics/by-category")
        assert r.status_code == 200
        stats = r.json()
        assert len(stats) == 2
