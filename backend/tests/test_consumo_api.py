"""
API tests for Product + Consumo endpoints (v1.6.0 — Phase 3).

Focuses on RBAC (recepcion can't CRUD products or void consumos) and
the basic HTTP contract.
"""

import pytest


class TestProductEndpoints:
    def test_list_products_requires_auth(self, client, seed_products):
        resp = client.get("/api/v1/productos/")
        assert resp.status_code in (401, 403)

    def test_list_products_as_recepcion(
        self, client, auth_headers_recep, seed_products
    ):
        resp = client.get("/api/v1/productos/", headers=auth_headers_recep)
        assert resp.status_code == 200
        # Recepcion can list (needed for consumo form)
        assert isinstance(resp.json(), list)

    def test_list_products_filter_category(
        self, client, auth_headers_admin, seed_products
    ):
        resp = client.get(
            "/api/v1/productos/?category=BEBIDA", headers=auth_headers_admin
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(p["category"] == "BEBIDA" for p in data)

    def test_recepcion_cannot_create_product(
        self, client, auth_headers_recep, seed_products
    ):
        resp = client.post(
            "/api/v1/productos/",
            headers=auth_headers_recep,
            json={
                "id": "new-product",
                "name": "Nueva cosa",
                "category": "SNACK",
                "price": 1000.0,
                "is_stocked": True,
            },
        )
        assert resp.status_code == 403

    def test_admin_can_create_product(
        self, client, auth_headers_admin, seed_products
    ):
        resp = client.post(
            "/api/v1/productos/",
            headers=auth_headers_admin,
            json={
                "id": "new-product-admin",
                "name": "Nueva cosa",
                "category": "SNACK",
                "price": 1000.0,
                "stock_current": 10,
                "stock_minimum": 2,
                "is_stocked": True,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["id"] == "new-product-admin"

    def test_invalid_category_rejected(self, client, auth_headers_admin, seed_products):
        resp = client.post(
            "/api/v1/productos/",
            headers=auth_headers_admin,
            json={
                "id": "bad", "name": "X",
                "category": "PIZZA",
                "price": 100.0,
            },
        )
        assert resp.status_code == 422  # pydantic validator

    def test_adjust_stock(self, client, auth_headers_admin, seed_products):
        resp = client.post(
            "/api/v1/productos/test-agua-500/ajuste-stock",
            headers=auth_headers_admin,
            json={"quantity_change": 20, "reason": "COMPRA", "notes": "compra semanal"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_stock"] == 70

    def test_recepcion_cannot_adjust_stock(
        self, client, auth_headers_recep, seed_products
    ):
        resp = client.post(
            "/api/v1/productos/test-agua-500/ajuste-stock",
            headers=auth_headers_recep,
            json={"quantity_change": 10, "reason": "COMPRA"},
        )
        assert resp.status_code == 403

    def test_low_stock_endpoint(self, client, auth_headers_admin, seed_products):
        resp = client.get(
            "/api/v1/productos/stock-bajo", headers=auth_headers_admin
        )
        assert resp.status_code == 200
        data = resp.json()
        # test-papas is below min in the seed
        assert any(p["id"] == "test-papas" for p in data)


class TestConsumoEndpoints:
    def _create_reservation(self, client, headers):
        resp = client.post(
            "/api/v1/reservations",
            headers=headers,
            json={
                "check_in_date": "2026-07-10",
                "stay_days": 1,
                "guest_name": "Consumo Test",
                "room_ids": ["los-monges-room-001"],
                "arrival_time": "14:00",
                "reserved_by": "test",
                "contact_phone": "",
                "received_by": "admin",
                "property_id": "los-monges",
                "price": 150000.0,
                "paid": True,  # status becomes CONFIRMADA
                "source": "Direct",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()[0]

    def test_recepcion_can_register_consumo(
        self, client, auth_headers_admin, auth_headers_recep, seed_products
    ):
        res_id = self._create_reservation(client, auth_headers_admin)
        resp = client.post(
            "/api/v1/consumos/",
            headers=auth_headers_recep,
            json={
                "reserva_id": res_id,
                "producto_id": "test-agua-500",
                "quantity": 2,
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["total"] == 10000.0

    def test_recepcion_cannot_void_consumo(
        self, client, auth_headers_admin, auth_headers_recep, seed_products
    ):
        res_id = self._create_reservation(client, auth_headers_admin)
        created = client.post(
            "/api/v1/consumos/",
            headers=auth_headers_recep,
            json={
                "reserva_id": res_id,
                "producto_id": "test-agua-500",
                "quantity": 1,
            },
        ).json()
        resp = client.post(
            f"/api/v1/consumos/{created['id']}/anular",
            headers=auth_headers_recep,
            json={"reason": "error"},
        )
        assert resp.status_code == 403

    def test_admin_can_void_consumo(
        self, client, auth_headers_admin, seed_products
    ):
        res_id = self._create_reservation(client, auth_headers_admin)
        created = client.post(
            "/api/v1/consumos/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "producto_id": "test-agua-500",
                "quantity": 1,
            },
        ).json()
        resp = client.post(
            f"/api/v1/consumos/{created['id']}/anular",
            headers=auth_headers_admin,
            json={"reason": "cargo incorrecto"},
        )
        assert resp.status_code == 200
        assert resp.json()["voided"] is True

    def test_list_consumos_by_reserva(
        self, client, auth_headers_admin, seed_products
    ):
        res_id = self._create_reservation(client, auth_headers_admin)
        client.post(
            "/api/v1/consumos/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "producto_id": "test-coca-500",
                "quantity": 3,
            },
        )
        resp = client.get(
            f"/api/v1/consumos/reserva/{res_id}",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["quantity"] == 3

    def test_saldo_includes_consumos(
        self, client, auth_headers_admin, seed_products
    ):
        """/reservations/{id}/saldo must now include consumo_total."""
        res_id = self._create_reservation(client, auth_headers_admin)

        # Get the room_total before adding consumo (server may compute price
        # from the pricing engine, overriding what we sent in)
        saldo_before = client.get(
            f"/api/v1/reservations/{res_id}/saldo", headers=auth_headers_admin
        ).json()
        room_total = saldo_before["room_total"]

        client.post(
            "/api/v1/consumos/",
            headers=auth_headers_admin,
            json={
                "reserva_id": res_id,
                "producto_id": "test-agua-500",
                "quantity": 2,
            },
        )
        resp = client.get(
            f"/api/v1/reservations/{res_id}/saldo",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["consumo_total"] == 10000.0
        assert data["room_total"] == room_total  # unchanged by consumo
        assert data["total"] == room_total + 10000.0


class TestFolioEndpoint:
    def test_download_folio_for_existing_reservation(
        self, client, auth_headers_admin, seed_products
    ):
        # Create a reservation and a consumo
        res = client.post(
            "/api/v1/reservations",
            headers=auth_headers_admin,
            json={
                "check_in_date": "2026-07-15",
                "stay_days": 1,
                "guest_name": "Folio Test",
                "room_ids": ["los-monges-room-001"],
                "arrival_time": "14:00",
                "reserved_by": "test",
                "contact_phone": "",
                "received_by": "admin",
                "property_id": "los-monges",
                "price": 100000.0,
                "paid": True,
                "source": "Direct",
            },
        )
        assert res.status_code == 201
        res_id = res.json()[0]
        client.post(
            "/api/v1/consumos/",
            headers=auth_headers_admin,
            json={"reserva_id": res_id, "producto_id": "test-agua-500", "quantity": 1},
        )

        resp = client.get(
            f"/api/v1/documents/folio/{res_id}", headers=auth_headers_admin
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        # Verify the PDF has actual content
        assert len(resp.content) > 1000

    def test_download_folio_for_missing_reservation(
        self, client, auth_headers_admin, seed_products
    ):
        resp = client.get(
            "/api/v1/documents/folio/NOEXISTE", headers=auth_headers_admin
        )
        assert resp.status_code == 404

    def test_list_cuentas_folder(self, client, auth_headers_admin):
        resp = client.get(
            "/api/v1/documents/list/Cuentas", headers=auth_headers_admin
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_invalid_folder_rejected(self, client, auth_headers_admin):
        resp = client.get(
            "/api/v1/documents/list/BadFolder", headers=auth_headers_admin
        )
        assert resp.status_code == 400
