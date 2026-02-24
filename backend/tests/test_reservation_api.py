"""
Phase 3 — API endpoint tests for Reservations (mobile/Next.js path).
"""

from datetime import date, timedelta


def _res_body(room_id, **overrides):
    body = {
        "check_in_date": (date.today() + timedelta(days=10)).isoformat(),
        "stay_days": 2,
        "guest_name": "API Test Guest",
        "room_ids": [room_id],
        "price": 150000,
        "property_id": "los-monges",
    }
    body.update(overrides)
    return body


class TestListReservations:
    def test_authenticated(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/reservations", headers=auth_headers_admin)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_unauthenticated(self, client, seed_rooms):
        r = client.get("/api/v1/reservations")
        assert r.status_code == 401

    def test_pagination(self, client, auth_headers_admin, seed_rooms, make_reservation):
        for i in range(5):
            make_reservation(guest_name=f"Guest {i}")
        r = client.get("/api/v1/reservations?skip=0&limit=2",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        assert len(r.json()) == 2


class TestCreateReservation:
    def test_success(self, client, auth_headers_admin, seed_rooms):
        body = _res_body(seed_rooms["rooms"][0].id)
        r = client.post("/api/v1/reservations", json=body,
                         headers=auth_headers_admin)
        assert r.status_code == 201
        ids = r.json()
        assert isinstance(ids, list)
        assert len(ids) == 1

    def test_unauthenticated(self, client, seed_rooms):
        body = _res_body(seed_rooms["rooms"][0].id)
        r = client.post("/api/v1/reservations", json=body)
        assert r.status_code == 401

    def test_invalid_data(self, client, auth_headers_admin, seed_rooms):
        body = {"stay_days": 2, "room_ids": ["x"]}  # missing guest_name
        r = client.post("/api/v1/reservations", json=body,
                         headers=auth_headers_admin)
        assert r.status_code == 422

    def test_multi_room(self, client, auth_headers_admin, seed_rooms):
        ids = [seed_rooms["rooms"][0].id, seed_rooms["rooms"][1].id]
        body = _res_body(ids[0], room_ids=ids)
        r = client.post("/api/v1/reservations", json=body,
                         headers=auth_headers_admin)
        assert r.status_code == 201
        assert len(r.json()) == 2


class TestGetReservation:
    def test_success(self, client, auth_headers_admin, seed_rooms, make_reservation):
        res = make_reservation()
        r = client.get(f"/api/v1/reservations/{res.id}",
                        headers=auth_headers_admin)
        assert r.status_code == 200

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/reservations/9999999",
                        headers=auth_headers_admin)
        assert r.status_code == 404


class TestCancelReservation:
    def test_success(self, client, auth_headers_admin, seed_rooms, make_reservation):
        res = make_reservation()
        r = client.post(
            f"/api/v1/reservations/{res.id}/cancel",
            json={"reason": "test cancel", "cancelled_by": "admin"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        r = client.post(
            "/api/v1/reservations/9999999/cancel",
            json={"reason": "test", "cancelled_by": "admin"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 404


class TestUpdateReservation:
    def test_success(self, client, auth_headers_admin, seed_rooms, make_reservation):
        res = make_reservation(guest_name="Original Name")
        body = _res_body(seed_rooms["rooms"][0].id, guest_name="Updated Name")
        r = client.put(
            f"/api/v1/reservations/{res.id}",
            json=body,
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        assert "updated" in r.json().get("message", "").lower() or r.json().get("id") == res.id

    def test_not_found(self, client, auth_headers_admin, seed_rooms):
        body = _res_body(seed_rooms["rooms"][0].id)
        r = client.put(
            "/api/v1/reservations/9999999",
            json=body,
            headers=auth_headers_admin,
        )
        assert r.status_code == 404


class TestWeeklyView:
    def test_empty(self, client, auth_headers_admin, seed_rooms):
        future = (date.today() + timedelta(days=60)).isoformat()
        r = client.get(
            f"/api/v1/reservations/weekly?start_date={future}",
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_with_data(self, client, auth_headers_admin, seed_rooms, make_reservation):
        target = date.today() + timedelta(days=1)
        make_reservation(
            check_in_date=target,
            stay_days=3,
            guest_name="Weekly Guest",
            room_id=seed_rooms["rooms"][0].id,
        )
        r = client.get(
            f"/api/v1/reservations/weekly?start_date={target.isoformat()}",
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        # The room's internal_code should be a key with guest data
        room_code = seed_rooms["rooms"][0].internal_code
        if room_code in data:
            values = list(data[room_code].values())
            assert any("Weekly Guest" in v for v in values if isinstance(v, str))
