"""
Phase 4 — API endpoint tests for Pricing.

Covers:
- Base price calculation
- Corporate discount
- Auto-detected seasonal pricing
- Manual season override (season_id parameter)
- GET /pricing/seasons endpoint
- GET /pricing/client-types endpoint
- Response structure validation
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


class TestSeasonOverride:
    """Tests for manual season_id override in price calculation."""

    def test_manual_season_applies_modifier(self, client, auth_headers_admin, seed_pricing_data):
        """Passing season_id forces that season's modifier, even outside its date range."""
        # Use a date far from Semana Santa (60 days ahead), but force Semana Santa season
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
            "season_id": "los-monges-semana-santa-2026",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        # 150000 * 1.30 = 195000
        assert data["final_price"] == 195000.0

    def test_manual_season_shows_manual_label(self, client, auth_headers_admin, seed_pricing_data):
        """When season_id is provided, breakdown modifier label includes '(manual)'."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
            "season_id": "los-monges-semana-santa-2026",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        modifiers = data["breakdown"]["modifiers"]
        season_mods = [m for m in modifiers if "Temporada" in m["name"]]
        assert len(season_mods) == 1
        assert "(manual)" in season_mods[0]["name"]
        assert "Semana Santa" in season_mods[0]["name"]

    def test_auto_detect_does_not_show_manual_label(self, client, auth_headers_admin, seed_pricing_data):
        """When season_id is NOT provided, auto-detected season label has no '(manual)'."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": "2026-04-01",  # Within Semana Santa range
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        modifiers = data["breakdown"]["modifiers"]
        season_mods = [m for m in modifiers if "Temporada" in m["name"]]
        assert len(season_mods) == 1
        assert "(manual)" not in season_mods[0]["name"]

    def test_manual_low_season_discount(self, client, auth_headers_admin, seed_pricing_data):
        """Force low season (-10%) on an arbitrary date."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
            "season_id": "los-monges-baja-feb-2026",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        # 150000 * 0.90 = 135000
        assert data["final_price"] == 135000.0

    def test_manual_season_combined_with_corporate(self, client, auth_headers_admin, seed_pricing_data):
        """Manual season + corporate discount stack correctly."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
            "client_type_id": "los-monges-empresa",
            "season_id": "los-monges-semana-santa-2026",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        # Base: 150000, -15% corp = 127500, +30% season on base = +45000
        # Total: 150000 - 22500 + 45000 = 172500
        assert data["final_price"] == 172500.0

    def test_null_season_id_uses_auto_detect(self, client, auth_headers_admin, seed_pricing_data):
        """Explicit null season_id behaves like omitting it (auto-detect)."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": "2026-04-01",  # Within Semana Santa
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
            "season_id": None,
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert data["final_price"] == 195000.0  # Auto-detected Semana Santa +30%

    def test_invalid_season_id_no_modifier(self, client, auth_headers_admin, seed_pricing_data):
        """Non-existent season_id is silently ignored (no modifier applied)."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
            "season_id": "nonexistent-season-id",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        # No season found → base price only
        assert data["final_price"] == 150000.0

    def test_inactive_season_id_ignored(self, client, auth_headers_admin, seed_pricing_data):
        """Inactive season (active=0) is not applied even when explicitly passed."""
        r = client.post("/api/v1/pricing/calculate", json={
            "category_id": "los-monges-estandar",
            "check_in": (date.today() + timedelta(days=60)).isoformat(),
            "stay_days": 1,
            "client_type_id": "los-monges-particular",
            "season_id": "los-monges-inactive",
        }, headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        # Inactive season ignored → base price only
        assert data["final_price"] == 150000.0


class TestGetSeasons:
    """Tests for GET /pricing/seasons endpoint."""

    def test_returns_active_seasons(self, client, auth_headers_admin, seed_pricing_data):
        r = client.get("/api/v1/pricing/seasons", headers=auth_headers_admin)
        assert r.status_code == 200
        seasons = r.json()
        # 2 active seasons (Semana Santa + Baja Febrero); inactive excluded
        assert len(seasons) == 2

    def test_excludes_inactive_seasons(self, client, auth_headers_admin, seed_pricing_data):
        r = client.get("/api/v1/pricing/seasons", headers=auth_headers_admin)
        seasons = r.json()
        names = {s["name"] for s in seasons}
        assert "Inactiva" not in names

    def test_season_dto_structure(self, client, auth_headers_admin, seed_pricing_data):
        r = client.get("/api/v1/pricing/seasons", headers=auth_headers_admin)
        seasons = r.json()
        assert len(seasons) >= 1
        s = seasons[0]
        assert "id" in s
        assert "name" in s
        assert "price_modifier" in s
        assert "color" in s
        assert isinstance(s["price_modifier"], (int, float))

    def test_season_has_description(self, client, auth_headers_admin, seed_pricing_data):
        r = client.get("/api/v1/pricing/seasons", headers=auth_headers_admin)
        seasons = r.json()
        semana_santa = next((s for s in seasons if s["name"] == "Semana Santa"), None)
        assert semana_santa is not None
        assert semana_santa["description"] == "Temporada alta - Semana Santa"
        assert semana_santa["color"] == "#EF4444"

    def test_seasons_ordered_by_priority(self, client, auth_headers_admin, seed_pricing_data):
        r = client.get("/api/v1/pricing/seasons", headers=auth_headers_admin)
        seasons = r.json()
        # Semana Santa (priority=10) should come before Baja Febrero (priority=5)
        names = [s["name"] for s in seasons]
        assert names.index("Semana Santa") < names.index("Temporada Baja Febrero")


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
