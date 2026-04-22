"""
Feature 3 (v1.9.0) — RoomStatusLog audit trail tests.

Verifies that PATCH /rooms/{id}/status writes a row to room_status_log
and that GET /rooms/{id}/status-log surfaces those rows correctly.
"""

from database import RoomStatusLog


class TestStatusChangeWritesLog:
    def test_single_change_creates_log_entry(self, client, db_session, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        before = db_session.query(RoomStatusLog).filter_by(room_id=room_id).count()

        r = client.patch(
            f"/api/v1/rooms/{room_id}/status",
            json={"status": "maintenance", "reason": "plumbing"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200

        rows = db_session.query(RoomStatusLog).filter_by(room_id=room_id).all()
        assert len(rows) == before + 1
        latest = rows[-1]
        assert latest.new_status == "maintenance"
        assert latest.reason == "plumbing"
        assert latest.changed_by == "admin"

    def test_log_captures_previous_status(self, client, db_session, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id

        # Two consecutive changes: available -> maintenance -> cleaning
        client.patch(f"/api/v1/rooms/{room_id}/status",
                     json={"status": "maintenance"}, headers=auth_headers_admin)
        client.patch(f"/api/v1/rooms/{room_id}/status",
                     json={"status": "cleaning"}, headers=auth_headers_admin)

        rows = (db_session.query(RoomStatusLog)
                .filter_by(room_id=room_id)
                .order_by(RoomStatusLog.id.asc())
                .all())
        # Last two entries (room may have been seeded with prior state)
        assert rows[-2].new_status == "maintenance"
        assert rows[-1].previous_status == "maintenance"
        assert rows[-1].new_status == "cleaning"

    def test_log_captures_changed_by_username(self, client, db_session, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        client.patch(f"/api/v1/rooms/{room_id}/status",
                     json={"status": "out_of_service"}, headers=auth_headers_admin)
        latest = (db_session.query(RoomStatusLog)
                  .filter_by(room_id=room_id)
                  .order_by(RoomStatusLog.id.desc())
                  .first())
        assert latest.changed_by == "admin"


class TestGetStatusLogEndpoint:
    def test_returns_entries(self, client, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        client.patch(f"/api/v1/rooms/{room_id}/status",
                     json={"status": "cleaning", "reason": "post-checkout"},
                     headers=auth_headers_admin)

        r = client.get(f"/api/v1/rooms/{room_id}/status-log", headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        latest = data[0]  # newest-first
        assert latest["new_status"] == "cleaning"
        assert latest["reason"] == "post-checkout"
        assert latest["changed_by"] == "admin"

    def test_empty_log_for_unchanged_room(self, client, auth_headers_admin, seed_rooms):
        # Use the LAST seeded room (less likely to have been touched by other tests)
        room_id = seed_rooms["rooms"][-1].id
        r = client.get(f"/api/v1/rooms/{room_id}/status-log", headers=auth_headers_admin)
        assert r.status_code == 200
        assert r.json() == []

    def test_ordered_newest_first(self, client, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        for status in ["maintenance", "cleaning", "available"]:
            client.patch(f"/api/v1/rooms/{room_id}/status",
                         json={"status": status}, headers=auth_headers_admin)

        r = client.get(f"/api/v1/rooms/{room_id}/status-log", headers=auth_headers_admin)
        data = r.json()
        # Most recent change should be "available"
        assert data[0]["new_status"] == "available"
        # Second most recent should be "cleaning"
        assert data[1]["new_status"] == "cleaning"

    def test_limit_query_param(self, client, auth_headers_admin, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        for i in range(5):
            client.patch(f"/api/v1/rooms/{room_id}/status",
                         json={"status": "cleaning" if i % 2 == 0 else "available"},
                         headers=auth_headers_admin)

        r = client.get(f"/api/v1/rooms/{room_id}/status-log?limit=2", headers=auth_headers_admin)
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_404_for_unknown_room(self, client, auth_headers_admin, seed_rooms):
        r = client.get("/api/v1/rooms/does-not-exist/status-log", headers=auth_headers_admin)
        assert r.status_code == 404

    def test_recepcion_can_read_log(self, client, auth_headers_admin, auth_headers_recep, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        client.patch(f"/api/v1/rooms/{room_id}/status",
                     json={"status": "maintenance"}, headers=auth_headers_admin)

        r = client.get(f"/api/v1/rooms/{room_id}/status-log", headers=auth_headers_recep)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_unauthenticated_rejected(self, client, seed_rooms):
        room_id = seed_rooms["rooms"][0].id
        r = client.get(f"/api/v1/rooms/{room_id}/status-log")
        assert r.status_code in (401, 403)
