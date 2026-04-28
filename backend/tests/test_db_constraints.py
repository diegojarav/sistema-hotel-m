"""
Schema constraint tests (v1.10.0 — Phase 2a Bonus #3.3).
========================================================

Verify that the constraints declared in `database.py` (Phase 1 + Phase 2a)
are actually enforced on a fresh DB. The `db_session` fixture uses
in-memory SQLite with `Base.metadata.create_all`, so every CHECK / UNIQUE
declared in the model is materialised — this is the test surface for
those constraints today.

CASCADE / SET NULL / RESTRICT behaviour requires `PRAGMA foreign_keys=ON`,
which the production engine listener sets. The in-memory test engine in
`conftest.py` does NOT set the pragma (because `set_sqlite_pragma` only
fires for the production `engine`), so cascade tests below either:
  - enable the pragma manually before exercising the cascade, or
  - skip and document as "Postgres-only" if the rebuild dance is too
    invasive for an in-memory test.

These tests are the quickest signal that a model edit didn't drop a
constraint silently. Run them before every commit that touches
`database.py` __table_args__.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from database import (
    AjusteInventario, CajaSesion, EmailLog, Guest, ICalFeed, MealPlan,
    Producto, Reservation, Room, RoomCategory, SystemSetting, Transaccion,
    Building,
)


def _enable_fk(db_session):
    """Enable PRAGMA foreign_keys=ON on the in-memory test connection."""
    db_session.execute_options = getattr(db_session, "execute_options", None)
    db_session.connection().execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=ON"))


# ======================================================================
# UNIQUE constraints
# ======================================================================
class TestUniqueConstraints:
    def test_meal_plans_property_code_unique(self, db_session, seed_property):
        p1 = MealPlan(
            id="m1", property_id="los-monges", code="CON_DESAYUNO",
            name="Con desayuno", surcharge_per_person=0, surcharge_per_room=0,
            applies_to_mode="ANY",
        )
        p2 = MealPlan(
            id="m2", property_id="los-monges", code="CON_DESAYUNO",
            name="Otra cosa", surcharge_per_person=0, surcharge_per_room=0,
            applies_to_mode="ANY",
        )
        db_session.add(p1)
        db_session.commit()
        db_session.add(p2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_system_settings_property_key_unique(self, db_session, seed_property):
        s1 = SystemSetting(id="s1", property_id="los-monges", setting_key="foo", setting_value="bar")
        s2 = SystemSetting(id="s2", property_id="los-monges", setting_key="foo", setting_value="baz")
        db_session.add(s1)
        db_session.commit()
        db_session.add(s2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_buildings_property_name_unique(self, db_session, seed_property):
        b1 = Building(id="b1", property_id="los-monges", name="Principal")
        b2 = Building(id="b2", property_id="los-monges", name="Principal")
        db_session.add(b1)
        db_session.commit()
        db_session.add(b2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


# ======================================================================
# CHECK constraints
# ======================================================================
class TestCheckConstraints:
    def test_rooms_status_invalid_rejected(self, db_session, seed_property):
        cat = RoomCategory(id="c1", property_id="los-monges", name="Test", base_price=100, max_capacity=2)
        db_session.add(cat); db_session.commit()
        r = Room(id="r1", property_id="los-monges", category_id="c1", status="INVALIDO")
        db_session.add(r)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_caja_sesion_status_invalid_rejected(self, db_session, seed_users):
        admin = seed_users["admin"]
        s = CajaSesion(user_id=admin.id, opening_balance=0, status="INVALIDO")
        db_session.add(s)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_transaccion_payment_method_invalid_rejected(self, db_session):
        t = Transaccion(amount=100, payment_method="BITCOIN")
        db_session.add(t)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_producto_category_invalid_rejected(self, db_session, seed_property):
        p = Producto(id="p1", property_id="los-monges", name="X", category="INVENTADA", price=100)
        db_session.add(p)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_ajuste_inventario_reason_invalid_rejected(self, db_session, seed_products):
        prod = next(iter(seed_products.values()))
        a = AjusteInventario(producto_id=prod.id, quantity_change=1, reason="MAGIA")
        db_session.add(a)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_email_log_status_invalid_rejected(self, db_session, make_reservation):
        res = make_reservation()
        e = EmailLog(
            reserva_id=res.id, recipient_email="x@y.com", subject="t", status="WHATEVER",
        )
        db_session.add(e)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_ical_feeds_last_sync_status_invalid_rejected(self, db_session, seed_rooms):
        f = ICalFeed(
            room_id=seed_rooms["rooms"][0].id,
            source="Booking.com",
            ical_url="https://example.com/x.ics",
            last_sync_status="MAYBE",
        )
        db_session.add(f)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_meal_plans_applies_to_mode_invalid_rejected(self, db_session, seed_property):
        mp = MealPlan(
            id="m1", property_id="los-monges", code="X", name="X",
            surcharge_per_person=0, surcharge_per_room=0,
            applies_to_mode="UNKNOWN_MODE",
        )
        db_session.add(mp)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    # --- positive controls (the valid value lands fine) ---
    def test_rooms_status_valid_accepted(self, db_session, seed_property):
        cat = RoomCategory(id="c1", property_id="los-monges", name="Test", base_price=100, max_capacity=2)
        db_session.add(cat); db_session.commit()
        for valid in ("available", "occupied", "maintenance", "cleaning", "out_of_service"):
            r = Room(id=f"r-{valid}", property_id="los-monges", category_id="c1", status=valid)
            db_session.add(r)
            db_session.commit()


# ======================================================================
# CASCADE / SET NULL / RESTRICT
# (Postgres-style enforcement requires PRAGMA foreign_keys=ON which the
# in-memory test engine doesn't enable by default. We enable it here.)
# ======================================================================
class TestCascadeBehaviour:
    def test_room_status_log_cascades_with_room(self, db_session, seed_rooms):
        from database import RoomStatusLog
        _enable_fk(db_session)
        room = seed_rooms["rooms"][0]
        db_session.add(RoomStatusLog(
            room_id=room.id, previous_status="available",
            new_status="maintenance", changed_by="admin",
        ))
        db_session.commit()
        assert db_session.query(RoomStatusLog).filter_by(room_id=room.id).count() == 1
        db_session.delete(room)
        db_session.commit()
        # Cascade: log row should be gone
        assert db_session.query(RoomStatusLog).filter_by(room_id=room.id).count() == 0

    def test_ical_feed_cascades_with_room(self, db_session, seed_rooms):
        _enable_fk(db_session)
        room = seed_rooms["rooms"][0]
        db_session.add(ICalFeed(
            room_id=room.id,
            source="Booking.com",
            ical_url="https://example.com/x.ics",
        ))
        db_session.commit()
        assert db_session.query(ICalFeed).filter_by(room_id=room.id).count() == 1
        db_session.delete(room)
        db_session.commit()
        assert db_session.query(ICalFeed).filter_by(room_id=room.id).count() == 0


class TestSetNullBehaviour:
    def test_reservation_meal_plan_set_null_on_plan_delete(self, db_session, seed_full):
        _enable_fk(db_session)
        plan = MealPlan(
            id="mp1", property_id="los-monges", code="X", name="X",
            surcharge_per_person=0, surcharge_per_room=0, applies_to_mode="ANY",
        )
        db_session.add(plan); db_session.commit()
        r = Reservation(
            id="0099001", check_in_date=date.today() + timedelta(days=1),
            stay_days=1, guest_name="X", room_id=seed_full["rooms"][0].id,
            status="Confirmada", price=100, property_id="los-monges",
            meal_plan_id=plan.id,
        )
        db_session.add(r); db_session.commit()
        assert r.meal_plan_id == "mp1"
        db_session.delete(plan); db_session.commit()
        db_session.refresh(r)
        assert r.meal_plan_id is None
