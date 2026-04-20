"""
Phase 4 — Meal Plan CRUD Tests (v1.7.0)
=========================================

Tests for MealPlanService + /api/v1/meal-plans endpoints.
"""

import pytest
from services.meal_plan_service import MealPlanService, MealPlanError


def test_create_plan_success(db_session, seed_property):
    plan = MealPlanService.create_plan(
        db=db_session,
        property_id="los-monges",
        code="CON_DESAYUNO",
        name="Con desayuno",
        surcharge_per_person=30000,
        applies_to_mode="OPCIONAL_PERSONA",
    )
    assert plan["code"] == "CON_DESAYUNO"
    assert plan["surcharge_per_person"] == 30000
    assert plan["is_system"] is False
    assert plan["is_active"] is True


def test_duplicate_code_rejected(db_session, seed_property):
    MealPlanService.create_plan(
        db=db_session, property_id="los-monges",
        code="CON_DESAYUNO", name="Con desayuno",
        surcharge_per_person=30000, applies_to_mode="OPCIONAL_PERSONA",
    )
    with pytest.raises(MealPlanError):
        MealPlanService.create_plan(
            db=db_session, property_id="los-monges",
            code="CON_DESAYUNO", name="Otro nombre",
            surcharge_per_person=40000, applies_to_mode="OPCIONAL_PERSONA",
        )


def test_negative_surcharge_rejected(db_session, seed_property):
    with pytest.raises(MealPlanError):
        MealPlanService.create_plan(
            db=db_session, property_id="los-monges",
            code="BAD", name="Bad",
            surcharge_per_person=-1000, applies_to_mode="OPCIONAL_PERSONA",
        )


def test_invalid_mode_rejected(db_session, seed_property):
    with pytest.raises(MealPlanError):
        MealPlanService.create_plan(
            db=db_session, property_id="los-monges",
            code="BAD", name="Bad",
            surcharge_per_person=30000, applies_to_mode="NOT_A_MODE",
        )


def test_update_plan_works(db_session, seed_property):
    plan = MealPlanService.create_plan(
        db=db_session, property_id="los-monges",
        code="CON_DESAYUNO", name="Con desayuno",
        surcharge_per_person=30000, applies_to_mode="OPCIONAL_PERSONA",
    )
    updated = MealPlanService.update_plan(
        db=db_session, plan_id=plan["id"], surcharge_per_person=40000, name="Con desayuno premium"
    )
    assert updated["surcharge_per_person"] == 40000
    assert updated["name"] == "Con desayuno premium"


def test_soft_delete_user_plan(db_session, seed_property):
    plan = MealPlanService.create_plan(
        db=db_session, property_id="los-monges",
        code="CON_DESAYUNO", name="Con desayuno",
        surcharge_per_person=30000, applies_to_mode="OPCIONAL_PERSONA",
    )
    MealPlanService.soft_delete(db=db_session, plan_id=plan["id"])
    refreshed = MealPlanService.get_plan(db=db_session, plan_id=plan["id"])
    assert refreshed["is_active"] is False


def test_cannot_delete_system_plan(db_session, seed_property):
    """System plans (is_system=1) are protected — soft_delete raises."""
    from services.settings_service import SettingsService
    SettingsService.set_meals_config(
        db=db_session, meals_enabled=True, meal_inclusion_mode="INCLUIDO"
    )
    from database import MealPlan
    solo = db_session.query(MealPlan).filter(MealPlan.code == "SOLO_HABITACION").first()
    assert solo is not None
    assert solo.is_system == 1
    with pytest.raises(MealPlanError):
        MealPlanService.soft_delete(db=db_session, plan_id=solo.id)


def test_list_plans_filter_by_mode(db_session, seed_property):
    """list_plans(mode_filter=X) returns only plans applicable to that mode or ANY."""
    # Seed SOLO (ANY) + CON_DESAYUNO (OPCIONAL_PERSONA) + EXPEDITIONARY (OPCIONAL_HABITACION)
    from services.settings_service import SettingsService
    SettingsService.set_meals_config(
        db=db_session, meals_enabled=True, meal_inclusion_mode="OPCIONAL_PERSONA"
    )
    MealPlanService.create_plan(
        db=db_session, property_id="los-monges",
        code="CON_DESAYUNO", name="Desayuno",
        surcharge_per_person=30000, applies_to_mode="OPCIONAL_PERSONA",
    )
    MealPlanService.create_plan(
        db=db_session, property_id="los-monges",
        code="HAB_PLAN", name="Hab flat",
        surcharge_per_room=50000, applies_to_mode="OPCIONAL_HABITACION",
    )

    # Filter by OPCIONAL_PERSONA → CON_DESAYUNO + ANY plans (SOLO_HABITACION)
    result = MealPlanService.list_plans(
        db=db_session, mode_filter="OPCIONAL_PERSONA"
    )
    codes = {p["code"] for p in result}
    assert "CON_DESAYUNO" in codes
    assert "SOLO_HABITACION" in codes
    assert "HAB_PLAN" not in codes


# ==========================================
# API Tests
# ==========================================

def test_api_list_plans_requires_auth(client, seed_property):
    r = client.get("/api/v1/meal-plans")
    # Without JWT → 401
    assert r.status_code == 401


def test_api_create_plan_admin_only(client, seed_users, seed_property, auth_header):
    # Recepcion → 403
    r = client.post(
        "/api/v1/meal-plans",
        json={"code": "TEST", "name": "Test", "surcharge_per_person": 30000, "applies_to_mode": "OPCIONAL_PERSONA"},
        headers=auth_header("recepcion", "recep123"),
    )
    assert r.status_code == 403

    # Admin → 201
    r = client.post(
        "/api/v1/meal-plans",
        json={"code": "TEST", "name": "Test", "surcharge_per_person": 30000, "applies_to_mode": "OPCIONAL_PERSONA"},
        headers=auth_header("admin", "admin123"),
    )
    assert r.status_code == 201
    assert r.json()["code"] == "TEST"
