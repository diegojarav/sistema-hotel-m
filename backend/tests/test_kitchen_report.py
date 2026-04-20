"""
Phase 4 — Kitchen Report Tests (v1.7.0)
==========================================

Tests for KitchenReportService + /api/v1/reportes/cocina endpoints.

Key business rules:
- Guest checking OUT today IS counted (they eat breakfast that morning)
- Guest checking IN today is NOT counted (arrives too late for breakfast)
- Cancelled reservations never counted
- INCLUIDO mode: all active guests counted; OPCIONAL_*: only breakfast_guests
"""

from datetime import date, datetime, timedelta

import pytest

from database import Reservation
from services.kitchen_report_service import KitchenReportService
from services.meal_plan_service import MealPlanService
from services.settings_service import SettingsService


def _make_reservation(
    db,
    reservation_id: str,
    room_id: str,
    check_in: date,
    stay_days: int,
    guest: str = "Test Guest",
    status: str = "CONFIRMADA",
    meal_plan_id=None,
    breakfast_guests=None,
) -> Reservation:
    res = Reservation(
        id=reservation_id,
        created_at=datetime.now(),
        check_in_date=check_in,
        stay_days=stay_days,
        guest_name=guest,
        room_id=room_id,
        room_type="Estandar",
        price=150000.0,
        final_price=150000.0,
        property_id="los-monges",
        category_id="los-monges-estandar",
        client_type_id="los-monges-particular",
        reserved_by="test",
        received_by="test",
        contact_phone="",
        status=status,
        meal_plan_id=meal_plan_id,
        breakfast_guests=breakfast_guests,
    )
    db.add(res)
    db.commit()
    return res


def test_disabled_returns_empty(db_session, seed_property):
    """When meals are disabled, returns enabled=False + empty rooms."""
    r = KitchenReportService.get_daily_report(db=db_session, fecha=date.today())
    assert r["enabled"] is False
    assert r["rooms"] == []
    assert r["total_with_breakfast"] == 0


def test_checkout_today_is_included(db_session, seed_rooms, enable_meals):
    """Guest who checks out today IS in today's breakfast count."""
    plans = enable_meals(mode="OPCIONAL_PERSONA")
    room_id = seed_rooms["rooms"][0].id

    today = date.today()
    # Guest checked in yesterday, 1-night stay → checks out today
    _make_reservation(
        db_session,
        "R-CHECKOUT-TODAY",
        room_id,
        check_in=today - timedelta(days=1),
        stay_days=1,
        meal_plan_id=plans["con_desayuno"].id,
        breakfast_guests=2,
    )
    r = KitchenReportService.get_daily_report(db=db_session, fecha=today)
    assert r["total_with_breakfast"] == 2
    assert len(r["rooms"]) == 1
    assert r["rooms"][0]["checkout_today"] is True


def test_checkin_today_is_excluded(db_session, seed_rooms, enable_meals):
    """Guest who checks in today is NOT in today's breakfast (arrives later)."""
    plans = enable_meals(mode="OPCIONAL_PERSONA")
    room_id = seed_rooms["rooms"][0].id

    today = date.today()
    _make_reservation(
        db_session,
        "R-CHECKIN-TODAY",
        room_id,
        check_in=today,
        stay_days=2,
        meal_plan_id=plans["con_desayuno"].id,
        breakfast_guests=3,
    )
    r = KitchenReportService.get_daily_report(db=db_session, fecha=today)
    assert r["total_with_breakfast"] == 0
    assert r["rooms"] == []


def test_mid_stay_is_included(db_session, seed_rooms, enable_meals):
    """Guest in the middle of their stay IS in today's breakfast count."""
    plans = enable_meals(mode="OPCIONAL_PERSONA")
    room_id = seed_rooms["rooms"][0].id

    today = date.today()
    # Check-in 2 days ago, 5-night stay → still mid-stay
    _make_reservation(
        db_session,
        "R-MID-STAY",
        room_id,
        check_in=today - timedelta(days=2),
        stay_days=5,
        meal_plan_id=plans["con_desayuno"].id,
        breakfast_guests=2,
    )
    r = KitchenReportService.get_daily_report(db=db_session, fecha=today)
    assert r["total_with_breakfast"] == 2
    assert r["rooms"][0]["checkout_today"] is False


def test_cancelled_excluded(db_session, seed_rooms, enable_meals):
    """CANCELADA reservations are never in the kitchen report."""
    plans = enable_meals(mode="OPCIONAL_PERSONA")
    room_id = seed_rooms["rooms"][0].id
    today = date.today()

    _make_reservation(
        db_session,
        "R-CANCELLED",
        room_id,
        check_in=today - timedelta(days=1),
        stay_days=2,
        status="CANCELADA",
        meal_plan_id=plans["con_desayuno"].id,
        breakfast_guests=2,
    )
    r = KitchenReportService.get_daily_report(db=db_session, fecha=today)
    assert r["total_with_breakfast"] == 0


def test_incluido_counts_all_guests(db_session, seed_rooms, enable_meals):
    """In INCLUIDO mode, every active overnight guest counts (no plan/pax needed)."""
    plans = enable_meals(mode="INCLUIDO")
    room_id = seed_rooms["rooms"][0].id
    today = date.today()

    # No plan/pax set — should still count (defaults to 1)
    _make_reservation(
        db_session,
        "R-INCL",
        room_id,
        check_in=today - timedelta(days=1),
        stay_days=2,
    )
    r = KitchenReportService.get_daily_report(db=db_session, fecha=today)
    assert r["total_with_breakfast"] >= 1
    assert r["mode"] == "INCLUIDO"


def test_opcional_with_zero_breakfast_counted_as_without(db_session, seed_rooms, enable_meals):
    """OPCIONAL_PERSONA with breakfast_guests=0 counts as 'sin desayuno'."""
    plans = enable_meals(mode="OPCIONAL_PERSONA")
    room_id = seed_rooms["rooms"][0].id
    today = date.today()

    # breakfast_guests left null → treated as 0; also set plan to SOLO_HABITACION
    _make_reservation(
        db_session,
        "R-NO-BF",
        room_id,
        check_in=today - timedelta(days=1),
        stay_days=2,
        meal_plan_id=plans["solo"].id,
        breakfast_guests=0,
    )
    r = KitchenReportService.get_daily_report(db=db_session, fecha=today)
    assert r["total_with_breakfast"] == 0


# ==========================================
# API Tests
# ==========================================

def test_api_cocina_requires_auth(client, seed_property):
    r = client.get("/api/v1/reportes/cocina")
    assert r.status_code == 401


def test_api_cocina_admin_allowed(client, seed_users, seed_property, auth_header):
    r = client.get(
        "/api/v1/reportes/cocina",
        headers=auth_header("admin", "admin123"),
    )
    # admin has access (returns 200 with empty report since meals disabled)
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_api_cocina_invalid_date(client, seed_users, seed_property, auth_header):
    r = client.get(
        "/api/v1/reportes/cocina?fecha=not-a-date",
        headers=auth_header("admin", "admin123"),
    )
    assert r.status_code == 400


def test_api_cocina_pdf_disabled_returns_404(client, seed_users, seed_property, auth_header):
    """When meals disabled, PDF endpoint returns 404 with a specific message."""
    r = client.get(
        "/api/v1/reportes/cocina/pdf",
        headers=auth_header("admin", "admin123"),
    )
    assert r.status_code == 404
    assert "no habilitado" in r.json()["detail"].lower()
