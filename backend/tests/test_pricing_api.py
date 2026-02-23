"""
Phase 4 — API endpoint tests for Pricing.
"""

from datetime import date, timedelta


class TestCalculatePrice:
    def test_base_price(self, client, auth_headers_admin, seed_pricing_data):
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 2,
            "client_type_id": "los-monges-particular",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert data["final_price"] == 300000.0  # 150000 * 2 nights
        assert data["currency"] == "PYG"

    def test_corporate_discount(self, client, auth_headers_admin, seed_pricing_data):
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 2,
            "client_type_id": "los-monges-empresa",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        # 150000 * 2 = 300000, -15% = 255000
        assert data["final_price"] == 255000.0

    def test_seasonal_price(self, client, auth_headers_admin, seed_pricing_data):
        """Semana Santa +30% (March 29 - April 5, 2026)."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": "2026-04-01",
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert data["final_price"] == 195000.0  # 150000 * 1.30

    def test_response_structure(self, client, auth_headers_admin, seed_pricing_data):
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
        }, headers=auth_headers_admin)
        data = r.json()
        assert "breakdown" in data
        assert "base_unit_price" in data["breakdown"]
        assert "base_total" in data["breakdown"]
        assert "modifiers" in data["breakdown"]


class TestGetClientTypes:
    def test_returns_list(self, client, auth_headers_admin, seed_pricing_data):
        r = client.get("/api/v1/pricing/client-types",
                        headers=auth_headers_admin)
        assert r.status_code == 200
        types = r.json()
        assert len(types) >= 2
        names = {t["name"] for t in types}
        assert "Particular" in names
        assert "Empresa" in names
