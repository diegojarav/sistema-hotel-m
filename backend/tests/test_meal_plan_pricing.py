"""
Phase 4 — Meal Plan Pricing Tests (v1.7.0)
============================================

Verifies the pricing engine correctly injects the meal plan surcharge
according to the hotel's meal_inclusion_mode.
"""

from datetime import date, timedelta

import pytest

from services.pricing_service import PricingService


def test_no_meal_plan_no_modifier(seed_pricing_data):
    """No meal_plan_id → no extra modifier row."""
    r = PricingService.calculate_price(
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=2,
        client_type_id="los-monges-particular",
    )
    # Base total 150k × 2 = 300k
    assert r["final_price"] == 300000.0
    # No "Plan:" modifier
    assert not any(m["name"].startswith("Plan:") for m in r["breakdown"]["modifiers"])


def test_opcional_persona_surcharge(db_session, seed_pricing_data, enable_meals):
    """2 pax × 3 nts × 30 000 = 180 000 surcharge."""
    plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
    plan_id = plans["con_desayuno"].id

    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=3,
        client_type_id="los-monges-particular",
        meal_plan_id=plan_id,
        breakfast_guests=2,
    )
    # Base 150k × 3 = 450k + surcharge 180k = 630k
    assert r["final_price"] == 630000.0
    plan_mods = [m for m in r["breakdown"]["modifiers"] if m["name"].startswith("Plan:")]
    assert len(plan_mods) == 1
    assert plan_mods[0]["amount"] == 180000.0


def test_opcional_habitacion_flat_surcharge(db_session, seed_pricing_data, enable_meals):
    """OPCIONAL_HABITACION: flat per-room per-night; breakfast_guests ignored."""
    plans = enable_meals(
        mode="OPCIONAL_HABITACION",
        per_person_surcharge=0,
        per_room_surcharge=50000,
    )
    plan_id = plans["con_desayuno"].id

    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=3,
        client_type_id="los-monges-particular",
        meal_plan_id=plan_id,
        breakfast_guests=99,  # should be ignored in room-mode
    )
    # 150k × 3 = 450k + 50k × 3 = 150k surcharge = 600k
    assert r["final_price"] == 600000.0


def test_incluido_mode_no_surcharge(db_session, seed_pricing_data, enable_meals):
    """INCLUIDO mode: price unchanged even when a plan is passed."""
    plans = enable_meals(mode="INCLUIDO")
    # CON_DESAYUNO auto-seeded with surcharge=0
    plan_id = plans["con_desayuno"].id

    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=2,
        client_type_id="los-monges-particular",
        meal_plan_id=plan_id,
        breakfast_guests=4,
    )
    # 150k × 2 = 300k, no surcharge line
    assert r["final_price"] == 300000.0
    assert not any(m["name"].startswith("Plan:") for m in r["breakdown"]["modifiers"])


def test_zero_breakfast_guests_no_surcharge(db_session, seed_pricing_data, enable_meals):
    """breakfast_guests=0 → surcharge 0 → no modifier row."""
    plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=2,
        client_type_id="los-monges-particular",
        meal_plan_id=plans["con_desayuno"].id,
        breakfast_guests=0,
    )
    assert r["final_price"] == 300000.0
    assert not any(m["name"].startswith("Plan:") for m in r["breakdown"]["modifiers"])


def test_inactive_plan_ignored(db_session, seed_pricing_data, enable_meals):
    """An is_active=0 plan is ignored even when passed."""
    plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
    plan = plans["con_desayuno"]
    plan.is_active = 0
    db_session.commit()

    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=2,
        client_type_id="los-monges-particular",
        meal_plan_id=plan.id,
        breakfast_guests=2,
    )
    assert r["final_price"] == 300000.0


def test_solo_habitacion_plan_no_surcharge(db_session, seed_pricing_data, enable_meals):
    """SOLO_HABITACION is always zero-surcharge."""
    plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=2,
        client_type_id="los-monges-particular",
        meal_plan_id=plans["solo"].id,
        breakfast_guests=2,
    )
    assert r["final_price"] == 300000.0


def test_breakdown_modifier_shape(db_session, seed_pricing_data, enable_meals):
    """The appended modifier row has the expected keys."""
    plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=25000)
    r = PricingService.calculate_price(
        db=db_session,
        property_id="los-monges",
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=1),
        stay_days=2,
        client_type_id="los-monges-particular",
        meal_plan_id=plans["con_desayuno"].id,
        breakfast_guests=1,
    )
    plan_mods = [m for m in r["breakdown"]["modifiers"] if m["name"].startswith("Plan:")]
    assert len(plan_mods) == 1
    mod = plan_mods[0]
    assert "name" in mod and "percent" in mod and "amount" in mod
    assert mod["amount"] == 50000  # 1 pax × 2 nts × 25k
