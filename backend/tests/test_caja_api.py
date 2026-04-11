"""
API tests for /caja, /transacciones, /reportes endpoints
==========================================================
"""

import pytest


class TestCajaAPI:
    """Tests for /api/v1/caja endpoints."""

    def test_abrir_caja(self, client, auth_headers_admin, seed_full):
        """POST /caja/abrir creates an open session."""
        resp = client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_admin,
            json={"opening_balance": 150000.0, "notes": "apertura"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ABIERTA"
        assert data["opening_balance"] == 150000.0
        assert data["user_name"] == "admin"

    def test_abrir_caja_requiere_auth(self, client, seed_full):
        """Unauthenticated request must be rejected."""
        resp = client.post("/api/v1/caja/abrir", json={"opening_balance": 100.0})
        assert resp.status_code in (401, 403)

    def test_abrir_caja_dos_veces_falla(self, client, auth_headers_admin, seed_full):
        """Second open without closing the first must return 400."""
        client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_admin,
            json={"opening_balance": 100.0},
        )
        resp = client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_admin,
            json={"opening_balance": 100.0},
        )
        assert resp.status_code == 400

    def test_get_caja_actual_abierta(self, client, auth_headers_admin, seed_full):
        """GET /caja/actual returns the user's open session."""
        client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_admin,
            json={"opening_balance": 50000.0},
        )
        resp = client.get("/api/v1/caja/actual", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["status"] == "ABIERTA"
        assert data["opening_balance"] == 50000.0

    def test_get_caja_actual_sin_sesion(self, client, auth_headers_admin, seed_full):
        """GET /caja/actual returns null when no session is open."""
        resp = client.get("/api/v1/caja/actual", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert resp.json() is None

    def test_cerrar_caja(self, client, auth_headers_admin, seed_full):
        """POST /caja/cerrar closes the session with computed difference."""
        opened = client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_admin,
            json={"opening_balance": 100000.0},
        ).json()

        resp = client.post(
            "/api/v1/caja/cerrar",
            headers=auth_headers_admin,
            json={
                "session_id": opened["id"],
                "closing_balance_declared": 100000.0,
                "notes": "cierre test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CERRADA"
        assert data["difference"] == 0.0

    def test_historial_no_admin_solo_ve_propio(
        self, client, auth_headers_recep, seed_full
    ):
        """Non-admin users only see their own sessions in /historial."""
        # Recep opens a session
        client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_recep,
            json={"opening_balance": 25000.0},
        )
        resp = client.get("/api/v1/caja/historial", headers=auth_headers_recep)
        assert resp.status_code == 200
        sessions = resp.json()
        assert all(s["user_name"] == "recepcion" for s in sessions)


class TestTransaccionAPI:
    """Tests for /api/v1/transacciones endpoints."""

    def _create_reservation(self, client, auth_headers_admin):
        """Helper: create a reservation via the API and return its ID. Base price = 150,000."""
        resp = client.post(
            "/api/v1/reservations",
            headers=auth_headers_admin,
            json={
                "check_in_date": "2026-06-01",
                "stay_days": 1,
                "guest_name": "Test Payment",
                "room_ids": ["los-monges-room-001"],
                "arrival_time": "14:00",
                "reserved_by": "test",
                "contact_phone": "+595-981-000000",
                "received_by": "admin",
                "property_id": "los-monges",
                "price": 150000.0,
                "paid": False,
                "source": "Direct",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()[0]

    def test_registrar_transferencia(self, client, auth_headers_admin, seed_full):
        """Register a TRANSFERENCIA payment without needing an open caja."""
        res_id = self._create_reservation(client, auth_headers_admin)

        resp = client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "amount": 100000.0,
                "payment_method": "TRANSFERENCIA",
                "reference_number": "BANK-123",
                "description": "seña",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["amount"] == 100000.0
        assert data["payment_method"] == "TRANSFERENCIA"
        assert data["voided"] is False

    def test_registrar_efectivo_sin_caja_falla(
        self, client, auth_headers_admin, seed_full
    ):
        """EFECTIVO without an open caja must return 400."""
        res_id = self._create_reservation(client, auth_headers_admin)

        resp = client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "amount": 50000.0,
                "payment_method": "EFECTIVO",
            },
        )
        assert resp.status_code == 400
        assert "caja" in resp.json()["detail"].lower()

    def test_registrar_efectivo_con_caja_ok(
        self, client, auth_headers_admin, seed_full
    ):
        """EFECTIVO works once caja is open."""
        # Open caja first
        client.post(
            "/api/v1/caja/abrir",
            headers=auth_headers_admin,
            json={"opening_balance": 0.0},
        )
        res_id = self._create_reservation(client, auth_headers_admin)

        resp = client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "amount": 100000.0,
                "payment_method": "EFECTIVO",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["payment_method"] == "EFECTIVO"
        assert data["caja_sesion_id"] is not None

    def test_anular_transaccion(self, client, auth_headers_admin, seed_full):
        """Void a transaction with a valid reason."""
        res_id = self._create_reservation(client, auth_headers_admin)
        trans = client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "amount": 50000.0,
                "payment_method": "TRANSFERENCIA",
                "reference_number": "xx",
            },
        ).json()

        resp = client.post(
            f"/api/v1/transacciones/{trans['id']}/anular",
            headers=auth_headers_admin,
            json={"reason": "Pago duplicado por error"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["voided"] is True
        assert data["void_reason"] == "Pago duplicado por error"

    def test_anular_razon_corta_falla(
        self, client, auth_headers_admin, seed_full
    ):
        """Voiding with a reason < 3 chars fails validation."""
        res_id = self._create_reservation(client, auth_headers_admin)
        trans = client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "amount": 50000.0,
                "payment_method": "TRANSFERENCIA",
            },
        ).json()

        resp = client.post(
            f"/api/v1/transacciones/{trans['id']}/anular",
            headers=auth_headers_admin,
            json={"reason": "x"},
        )
        assert resp.status_code == 422  # Pydantic validation

    def test_saldo_endpoint(self, client, auth_headers_admin, seed_full):
        """GET /reservations/{id}/saldo returns total/paid/pending."""
        res_id = self._create_reservation(client, auth_headers_admin)

        client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "amount": 75000.0,
                "payment_method": "TRANSFERENCIA",
                "reference_number": "part-1",
            },
        )

        resp = client.get(
            f"/api/v1/reservations/{res_id}/saldo",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 150000.0  # 1 day * 150k base price
        assert data["paid"] == 75000.0
        assert data["pending"] == 75000.0
        assert len(data["transacciones"]) == 1

    def test_saldo_reserva_inexistente(self, client, auth_headers_admin, seed_full):
        """Saldo for a non-existent reservation returns 404."""
        resp = client.get(
            "/api/v1/reservations/NOEXISTE/saldo",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 404


class TestReportesFinancierosAPI:
    """Tests for /api/v1/reportes endpoints."""

    def test_ingresos_diarios(self, client, auth_headers_admin, seed_full):
        """GET /reportes/ingresos-diarios returns breakdown by method."""
        # Create reservation + payments
        res = client.post(
            "/api/v1/reservations",
            headers=auth_headers_admin,
            json={
                "check_in_date": "2026-07-01",
                "stay_days": 1,
                "guest_name": "Report Test",
                "room_ids": ["los-monges-room-001"],
                "arrival_time": "14:00",
                "reserved_by": "test",
                "contact_phone": "",
                "received_by": "admin",
                "property_id": "los-monges",
                "price": 150000.0,
                "paid": False,
                "source": "Direct",
            },
        ).json()[0]

        client.post(
            "/api/v1/transacciones/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res,
                "amount": 150000.0,
                "payment_method": "TRANSFERENCIA",
                "reference_number": "t1",
            },
        )

        resp = client.get(
            "/api/v1/reportes/ingresos-diarios",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transferencia"]["total"] == 150000.0
        assert data["transferencia"]["count"] == 1
        assert data["efectivo"]["total"] == 0.0
        assert data["total_general"] == 150000.0

    def test_reportes_requieren_auth(self, client, seed_full):
        """Reports endpoints require authentication."""
        resp = client.get("/api/v1/reportes/ingresos-diarios")
        assert resp.status_code in (401, 403)
