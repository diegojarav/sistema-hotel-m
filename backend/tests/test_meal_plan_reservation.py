"""
Phase 4 — Meal Plan ↔ Reservation integration tests
====================================================

Verifies that reservations created via ReservationService propagate the
meal plan + breakfast guest count correctly, that the surcharge lands on
the reservation price, and that the backend rejects over-capacity payloads
(defense-in-depth against bypassing the PC/mobile UI caps).

Covers the bugs fixed in the v1.10.0 meal plan UI sweep:
- PC was creating reservations with NO meal plan (UI section was missing)
- Mobile allowed any number of breakfast guests regardless of room capacity
- Backend had no capacity guard at all
"""

from datetime import date, timedelta

import pytest

from database import Reservation
from schemas import ReservationCreate
from services.reservation_service import ReservationService


def _make_res(**overrides) -> ReservationCreate:
    """Build a valid ReservationCreate with sensible defaults."""
    defaults = dict(
        check_in_date=date.today() + timedelta(days=7),
        stay_days=2,
        guest_name="Carlos Gonzalez",
        room_ids=["los-monges-room-001"],  # Estandar, max_capacity=2
        room_type="Estandar",
        price=300000.0,
        reserved_by="test",
        contact_phone="0981555000",
        received_by="recepcion",
        source="Direct",
    )
    defaults.update(overrides)
    return ReservationCreate(**defaults)


# ==========================================
# Reservation persists meal plan fields
# ==========================================

class TestMealPlanPersistsOnReservation:
    """meal_plan_id + breakfast_guests must round-trip through create."""

    def test_with_plan_and_pax_persists(self, db_session, seed_full, enable_meals):
        """OPCIONAL_PERSONA + plan + pax → both fields stored on the row."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(meal_plan_id=plans["con_desayuno"].id, breakfast_guests=2)
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.meal_plan_id == plans["con_desayuno"].id
        assert r.breakfast_guests == 2

    def test_without_plan_persists_null(self, db_session, seed_full, enable_meals):
        """Hotel has meals enabled, but the reservation doesn't pick a plan."""
        enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res()  # no meal_plan_id
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.meal_plan_id is None
        assert r.breakfast_guests is None

    def test_surcharge_lands_on_price(self, db_session, seed_full, enable_meals):
        """Final price reflects the meal plan surcharge.

        Estandar 150k × 2 nts = 300k base + 1 pax × 2 nts × 30k = 60k → 360k.
        """
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(
            price=0.0,  # let pricing engine compute
            meal_plan_id=plans["con_desayuno"].id,
            breakfast_guests=1,
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.final_price == 360000.0

    def test_incluido_mode_auto_assigns_con_desayuno(
        self, db_session, seed_full, enable_meals
    ):
        """INCLUIDO mode: backend auto-assigns CON_DESAYUNO when caller sends nothing.

        Pricing engine still charges 0 (the surcharge column is 0 by design),
        but the reservation row gets the plan id so the kitchen report can
        count the guests.
        """
        plans = enable_meals(mode="INCLUIDO")
        data = _make_res()  # no meal_plan_id, no breakfast_guests
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.meal_plan_id == plans["con_desayuno"].id
        assert r.breakfast_guests is not None and r.breakfast_guests >= 1


# ==========================================
# Capacity validation (defense-in-depth)
# ==========================================

class TestBreakfastGuestsCapacityValidation:
    """The backend must reject breakfast_guests > sum(room capacities)."""

    def test_over_capacity_single_room_rejected(
        self, db_session, seed_full, enable_meals
    ):
        """Estandar capacity=2 → asking for 3 breakfast guests must fail."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(
            room_ids=["los-monges-room-001"],
            meal_plan_id=plans["con_desayuno"].id,
            breakfast_guests=3,
        )
        with pytest.raises(ValueError, match="excede la capacidad"):
            ReservationService.create_reservations(db_session, data)

    def test_at_capacity_passes(self, db_session, seed_full, enable_meals):
        """breakfast_guests == capacity must succeed (boundary case)."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(
            room_ids=["los-monges-room-001"],
            meal_plan_id=plans["con_desayuno"].id,
            breakfast_guests=2,
        )
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1

    def test_capacity_sums_across_rooms(self, db_session, seed_full, enable_meals):
        """Selecting 2 Estandar (cap=2 each) + 1 Suite (cap=4) → total=8 allowed."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(
            room_ids=[
                "los-monges-room-001",  # Estandar
                "los-monges-room-002",  # Estandar
                "los-monges-room-005",  # Suite
            ],
            price=0.0,
            meal_plan_id=plans["con_desayuno"].id,
            breakfast_guests=8,
        )
        ids = ReservationService.create_reservations(db_session, data)
        # Backend creates one reservation per room (3 rooms in payload)
        assert len(ids) == 3

    def test_over_summed_capacity_rejected(
        self, db_session, seed_full, enable_meals
    ):
        """3 rooms with cap (2+2+4)=8 → asking for 9 must fail."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(
            room_ids=[
                "los-monges-room-001",
                "los-monges-room-002",
                "los-monges-room-005",
            ],
            meal_plan_id=plans["con_desayuno"].id,
            breakfast_guests=9,
        )
        with pytest.raises(ValueError, match="excede la capacidad"):
            ReservationService.create_reservations(db_session, data)

    def test_zero_breakfast_guests_is_noop(
        self, db_session, seed_full, enable_meals
    ):
        """breakfast_guests=0 must skip capacity validation entirely."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(
            meal_plan_id=plans["con_desayuno"].id,
            breakfast_guests=0,
        )
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1


# ==========================================
# update_reservation: meal-plan sync
# ==========================================

class TestUpdateReservationMealPlanSync:
    """Editing a reservation must keep meal_plan_id and breakfast_guests in sync."""

    def test_clearing_plan_clears_breakfast_guests(
        self, db_session, seed_full, enable_meals
    ):
        """Setting meal_plan_id=None on update must also null out breakfast_guests.

        Otherwise a reservation can end up with "2 guests with breakfast" but
        no plan attached — the kitchen report would over-count.
        """
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        # Create with plan + pax
        data = _make_res(meal_plan_id=plans["con_desayuno"].id, breakfast_guests=2)
        ids = ReservationService.create_reservations(db_session, data)

        # Now clear the plan via update
        cleared = _make_res(meal_plan_id=None, breakfast_guests=None)
        ok = ReservationService.update_reservation(db_session, ids[0], cleared)
        assert ok is True

        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.meal_plan_id is None
        assert r.breakfast_guests is None

    def test_get_reservation_returns_meal_fields(
        self, db_session, seed_full, enable_meals
    ):
        """get_reservation must include meal_plan_id + breakfast_guests so the
        edit form can pre-fill the section."""
        plans = enable_meals(mode="OPCIONAL_PERSONA", per_person_surcharge=30000)
        data = _make_res(meal_plan_id=plans["con_desayuno"].id, breakfast_guests=2)
        ids = ReservationService.create_reservations(db_session, data)

        loaded = ReservationService.get_reservation(db_session, ids[0])
        assert loaded is not None
        assert loaded.meal_plan_id == plans["con_desayuno"].id
        assert loaded.breakfast_guests == 2
