"""
Phase 3 — API endpoint tests for User Management (admin only).
"""


class TestListUsers:
    def test_admin(self, client, auth_headers_admin):
        r = client.get("/api/v1/users", headers=auth_headers_admin)
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 2  # admin + recepcion

    def test_non_admin(self, client, auth_headers_recep):
        r = client.get("/api/v1/users", headers=auth_headers_recep)
        assert r.status_code == 403


class TestCreateUser:
    def test_success(self, client, auth_headers_admin):
        r = client.post("/api/v1/users", json={
            "username": "newuser",
            "password": "newpass123",
            "role": "recepcionista",
            "real_name": "New User",
        }, headers=auth_headers_admin)
        assert r.status_code == 200

    def test_duplicate(self, client, auth_headers_admin):
        # Create first
        client.post("/api/v1/users", json={
            "username": "dupuser",
            "password": "pass123",
            "role": "recepcionista",
            "real_name": "Dup",
        }, headers=auth_headers_admin)
        # Create duplicate
        r = client.post("/api/v1/users", json={
            "username": "dupuser",
            "password": "pass456",
            "role": "recepcionista",
            "real_name": "Dup2",
        }, headers=auth_headers_admin)
        assert r.status_code == 400

    def test_non_admin(self, client, auth_headers_recep):
        r = client.post("/api/v1/users", json={
            "username": "test",
            "password": "test123",
            "role": "recepcionista",
            "real_name": "Test",
        }, headers=auth_headers_recep)
        assert r.status_code == 403


class TestResetPassword:
    def test_success(self, client, auth_headers_admin, db_session, seed_users):
        uid = seed_users["recepcionista"].id
        r = client.patch(f"/api/v1/users/{uid}/password", json={
            "new_password": "newpass456",
        }, headers=auth_headers_admin)
        assert r.status_code == 200


class TestDeleteUser:
    def test_success(self, client, auth_headers_admin, seed_users):
        uid = seed_users["recepcionista"].id
        r = client.delete(f"/api/v1/users/{uid}",
                           headers=auth_headers_admin)
        assert r.status_code == 200

    def test_delete_self(self, client, auth_headers_admin, seed_users):
        uid = seed_users["admin"].id
        r = client.delete(f"/api/v1/users/{uid}",
                           headers=auth_headers_admin)
        assert r.status_code == 400

    def test_non_admin(self, client, auth_headers_recep, seed_users):
        uid = seed_users["admin"].id
        r = client.delete(f"/api/v1/users/{uid}",
                           headers=auth_headers_recep)
        assert r.status_code == 403


class TestSessionLogs:
    def test_returns_list(self, client, auth_headers_admin):
        r = client.get("/api/v1/users/sessions",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
