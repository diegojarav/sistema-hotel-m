"""
Phase 4 — Meal Service Configuration Tests (v1.7.0)
=====================================================

Tests for `SettingsService.get_meals_config` / `set_meals_config` and the
`/api/v1/settings/meals-config` endpoints. Covers the zero-regression
(disabled) state + all 3 modes + role enforcement.
"""

import pytest
from services.settings_service import SettingsService


def test_default_meals_disabled(seed_property):
    """Fresh property defaults to meals disabled."""
    cfg = SettingsService.get_meals_config(property_id="los-monges")
    assert cfg["meals_enabled"] is False
    assert cfg["meal_inclusion_mode"] is None


def test_enable_incluido_seeds_con_desayuno(db_session, seed_property):
    """Enabling INCLUIDO mode auto-seeds the CON_DESAYUNO plan with 0 surcharge."""
    from database import MealPlan
    SettingsService.set_meals_config(
        db=db_session, meals_enabled=True, meal_inclusion_mode="INCLUIDO"
    )
    cfg = SettingsService.get_meals_config(db=db_session)
    assert cfg["meals_enabled"] is True
    assert cfg["meal_inclusion_mode"] == "INCLUIDO"

    con_desayuno = (
        db_session.query(MealPlan)
        .filter(MealPlan.property_id == "los-monges", MealPlan.code == "CON_DESAYUNO")
        .first()
    )
    assert con_desayuno is not None
    assert con_desayuno.is_system == 1
    assert con_desayuno.surcharge_per_person == 0
    assert con_desayuno.surcharge_per_room == 0


def test_enable_opcional_persona(db_session, seed_property):
    """OPCIONAL_PERSONA enables but does NOT auto-create CON_DESAYUNO."""
    from database import MealPlan
    SettingsService.set_meals_config(
        db=db_session, meals_enabled=True, meal_inclusion_mode="OPCIONAL_PERSONA"
    )
    # SOLO_HABITACION is always seeded
    solo = (
        db_session.query(MealPlan)
        .filter(MealPlan.code == "SOLO_HABITACION")
        .first()
    )
    assert solo is not None
    # CON_DESAYUNO is NOT auto-seeded (admin creates it manually with a real price)
    con_desayuno = (
        db_session.query(MealPlan)
        .filter(MealPlan.code == "CON_DESAYUNO")
        .first()
    )
    assert con_desayuno is None


def test_disable_clears_mode(db_session, seed_property):
    """Setting meals_enabled=False clears the mode but preserves existing plans."""
    SettingsService.set_meals_config(
        db=db_session, meals_enabled=True, meal_inclusion_mode="OPCIONAL_PERSONA"
    )
    SettingsService.set_meals_config(db=db_session, meals_enabled=False)
    cfg = SettingsService.get_meals_config(db=db_session)
    assert cfg["meals_enabled"] is False
    assert cfg["meal_inclusion_mode"] is None


def test_invalid_mode_rejected(db_session, seed_property):
    """An invalid mode string raises ValueError."""
    with pytest.raises(ValueError):
        SettingsService.set_meals_config(
            db=db_session, meals_enabled=True, meal_inclusion_mode="NOT_A_MODE"
        )


def test_enable_without_mode_rejected(db_session, seed_property):
    """Enabling meals without providing a mode is rejected."""
    with pytest.raises(ValueError):
        SettingsService.set_meals_config(
            db=db_session, meals_enabled=True, meal_inclusion_mode=None
        )


# ==========================================
# API tests
# ==========================================

def test_api_get_meals_config_public(client, seed_property):
    """GET /meals-config is public (no auth needed)."""
    r = client.get("/api/v1/settings/meals-config")
    assert r.status_code == 200
    assert r.json() == {"meals_enabled": False, "meal_inclusion_mode": None}


def test_api_put_meals_config_requires_admin(client, seed_users, seed_property, auth_header):
    """PUT /meals-config requires admin role."""
    # Recepcion → 403
    r = client.put(
        "/api/v1/settings/meals-config",
        json={"meals_enabled": True, "meal_inclusion_mode": "INCLUIDO"},
        headers=auth_header("recepcion", "recep123"),
    )
    assert r.status_code == 403


def test_api_put_meals_config_admin_succeeds(client, seed_users, seed_property, auth_header):
    """Admin can enable meals via API."""
    r = client.put(
        "/api/v1/settings/meals-config",
        json={"meals_enabled": True, "meal_inclusion_mode": "OPCIONAL_HABITACION"},
        headers=auth_header("admin", "admin123"),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["meals_enabled"] is True
    assert data["meal_inclusion_mode"] == "OPCIONAL_HABITACION"
