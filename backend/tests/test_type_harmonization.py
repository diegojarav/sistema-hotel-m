"""
Phase 2b — Type harmonization tests (v1.10.0)
================================================

Validates the model-level changes from migrations 014 + 015:

  * Boolean-as-Integer columns now round-trip as Python `bool`, not `int`.
  * JSON-in-String columns now round-trip as Python dict/list, not str.
  * `checkins.created_at` is a DateTime, not a Date (captures time-of-day).
  * `Property.breakfast_included` was dropped from the model.
  * `Property.slug` is required (NOT NULL).
  * Retention script prunes the right rows without touching the wrong ones.

These tests use the in-memory SQLite test DB so they don't depend on the
state of the real `hotel.db`. They DO assume the model in `database.py`
reflects the Phase 2b changes (true after `pip install` of the worktree).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError


def _load_retention_module():
    """Load scripts/cleanup_retention.py without requiring it on sys.path.

    The script lives outside the backend/ package and pytest's cwd is backend/,
    so a plain `import scripts.cleanup_retention` fails. importlib.util gives
    us a clean module handle without polluting sys.path globally.
    """
    here = Path(__file__).resolve()
    script_path = here.parents[2] / "scripts" / "cleanup_retention.py"
    spec = importlib.util.spec_from_file_location("cleanup_retention", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

from database import (
    AIAgentPermission,
    CheckIn,
    ICalFeed,
    MealPlan,
    PriceCalculation,
    PricingSeason,
    Property,
    Reservation,
    Room,
    RoomCategory,
    SessionLog,
)


# ----------------------------------------------------------------------
# Boolean harmonization
# ----------------------------------------------------------------------

class TestBooleanRoundTrip:
    """Reads from existing 0/1 data MUST come back as Python bool."""

    def test_property_active_is_bool(self, db_session, seed_property):
        prop = db_session.query(Property).filter(Property.id == "los-monges").first()
        assert prop is not None
        assert isinstance(prop.active, bool)
        assert prop.active is True

    def test_property_parking_available_is_bool(self, db_session, seed_property):
        prop = db_session.query(Property).filter(Property.id == "los-monges").first()
        assert isinstance(prop.parking_available, bool)

    def test_property_meals_enabled_is_bool(self, db_session, seed_property):
        prop = db_session.query(Property).filter(Property.id == "los-monges").first()
        assert isinstance(prop.meals_enabled, bool)
        # seed_property fixture leaves it default (False)
        assert prop.meals_enabled is False

    def test_room_active_is_bool(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        db_session.refresh(room)
        assert isinstance(room.active, bool)
        assert room.active is True

    def test_room_category_active_is_bool(self, db_session, seed_rooms):
        cat = seed_rooms["cat_std"]
        db_session.refresh(cat)
        assert isinstance(cat.active, bool)

    def test_ai_permission_can_view_reservations_is_bool(self, db_session, seed_property):
        perm = AIAgentPermission(
            id="role-recepcion",
            property_id="los-monges",
            role="recepcion",
        )
        db_session.add(perm)
        db_session.commit()
        db_session.refresh(perm)
        # All 14 can_* flags should be Python bools
        for col in (
            "can_view_reservations", "can_create_reservations",
            "can_modify_reservations", "can_cancel_reservations",
            "can_view_guests", "can_modify_guests",
            "can_view_rooms", "can_modify_rooms", "can_modify_room_status",
            "can_view_prices", "can_modify_prices",
            "can_view_reports", "can_export_data", "can_modify_settings",
            "requires_confirmation",
        ):
            assert isinstance(getattr(perm, col), bool), f"{col} is not bool"

    def test_meal_plan_is_active_is_bool(self, db_session, seed_property):
        mp = MealPlan(
            id="los-monges-plan-x",
            property_id="los-monges",
            code="X_PLAN",
            name="Test plan",
        )
        db_session.add(mp)
        db_session.commit()
        db_session.refresh(mp)
        assert isinstance(mp.is_system, bool)
        assert isinstance(mp.is_active, bool)
        assert mp.is_active is True  # default
        assert mp.is_system is False


# ----------------------------------------------------------------------
# JSON column round-trip
# ----------------------------------------------------------------------

class TestJSONRoundTrip:
    """Storing a dict/list MUST come back as the same dict/list."""

    def test_room_category_amenities_dict(self, db_session, seed_property):
        cat = RoomCategory(
            id="los-monges-test-cat",
            property_id="los-monges",
            name="Test",
            base_price=100000.0,
            max_capacity=2,
            amenities=["wifi", "tv", "ac"],
            bed_configuration={"matrimonial": 1},
        )
        db_session.add(cat)
        db_session.commit()
        db_session.refresh(cat)
        # JSON column returns Python types, not the JSON string
        assert cat.amenities == ["wifi", "tv", "ac"]
        assert cat.bed_configuration == {"matrimonial": 1}
        assert isinstance(cat.amenities, list)
        assert isinstance(cat.bed_configuration, dict)

    def test_reservation_price_breakdown_dict(
        self, db_session, seed_rooms, make_reservation
    ):
        res = make_reservation()
        # price_breakdown set by ReservationService — should be a dict, not str
        db_session.refresh(res)
        # Default may be None or dict; if present must be dict
        if res.price_breakdown is not None:
            assert isinstance(res.price_breakdown, (dict, list)), (
                f"price_breakdown is {type(res.price_breakdown).__name__}, "
                f"expected dict/list (JSON type)"
            )


# ----------------------------------------------------------------------
# checkins.created_at — Date → DateTime
# ----------------------------------------------------------------------

class TestCheckinCreatedAtDatetime:
    def test_new_checkin_has_full_timestamp(self, db_session, seed_rooms):
        ci = CheckIn(
            room_id=seed_rooms["rooms"][0].id,
            last_name="TestPaxA",
            first_name="Demo",
            origin="",
            destination="",
            civil_status="",
            document_number="999999",
            country="",
            billing_name="",
            billing_ruc="",
            vehicle_model="",
            vehicle_plate="",
            digital_signature="Pendiente",
        )
        db_session.add(ci)
        db_session.commit()
        db_session.refresh(ci)
        assert isinstance(ci.created_at, datetime), (
            f"created_at is {type(ci.created_at).__name__}, expected datetime"
        )
        # New row should have time-of-day (i.e. not all-zero)
        assert (
            ci.created_at.hour != 0
            or ci.created_at.minute != 0
            or ci.created_at.second != 0
        ), "created_at appears to be a Date with all-zero time"


# ----------------------------------------------------------------------
# breakfast_included dropped from model
# ----------------------------------------------------------------------

class TestBreakfastIncludedRemoved:
    def test_property_class_has_no_breakfast_included_attr(self):
        assert not hasattr(Property, "breakfast_included"), (
            "Property still exposes breakfast_included — must be dropped in v1.10.0"
        )

    def test_table_columns_have_no_breakfast_included(self):
        cols = [c.name for c in Property.__table__.columns]
        assert "breakfast_included" not in cols, (
            f"properties columns still include breakfast_included: {cols}"
        )

    def test_api_response_derives_breakfast_included(self, db_session, seed_property):
        """Backward compat: API still returns the field, derived from meals fields."""
        from services.settings_service import SettingsService

        # meals_enabled=False (fixture default) → breakfast_included False
        settings = SettingsService.get_property_settings(
            db=db_session, property_id="los-monges"
        )
        assert settings["breakfast_included"] is False

        # Set INCLUIDO mode → derived True
        seed_property.meals_enabled = True
        seed_property.meal_inclusion_mode = "INCLUIDO"
        db_session.commit()
        settings = SettingsService.get_property_settings(
            db=db_session, property_id="los-monges"
        )
        assert settings["breakfast_included"] is True


# ----------------------------------------------------------------------
# Property.slug — NOT NULL
# ----------------------------------------------------------------------

class TestPropertySlugNotNull:
    def test_slug_required(self, db_session):
        prop = Property(
            id="test-prop-no-slug",
            name="Test Hotel",
            slug=None,
        )
        db_session.add(prop)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_slug_unique(self, db_session, seed_property):
        # Try to create another property with the same slug as los-monges
        dup = Property(id="other-prop", name="Other", slug="los-monges")
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


# ----------------------------------------------------------------------
# Retention script
# ----------------------------------------------------------------------

class TestRetentionScript:
    """The script reads/writes its own sqlite3 connection (not the test ORM
    session). We point it at a temp DB seeded with the rows we care about.
    """

    def _seed_test_db(self, db_path: Path) -> None:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE price_calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id TEXT,
                property_id TEXT NOT NULL,
                base_price_per_night REAL NOT NULL,
                nights INTEGER NOT NULL,
                base_total REAL NOT NULL,
                final_price REAL NOT NULL,
                calculated_at TIMESTAMP
            );
            CREATE TABLE session_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                username TEXT NOT NULL,
                login_time TIMESTAMP NOT NULL,
                logout_time TIMESTAMP,
                device_type TEXT NOT NULL DEFAULT 'PC',
                status TEXT NOT NULL DEFAULT 'active'
            );
            """
        )
        now = datetime.now()
        old = now - timedelta(days=400)
        recent = now - timedelta(days=10)
        prune_window = now - timedelta(days=120)
        # price_calculations: one old-no-reserva (PRUNE), one recent-no-reserva (KEEP),
        # one old-with-reserva (KEEP)
        conn.executemany(
            "INSERT INTO price_calculations (reservation_id, property_id, base_price_per_night, "
            "nights, base_total, final_price, calculated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (None, "p", 100.0, 1, 100.0, 100.0, prune_window.isoformat()),  # PRUNE
                (None, "p", 100.0, 1, 100.0, 100.0, recent.isoformat()),         # KEEP (too recent)
                ("R1", "p", 100.0, 1, 100.0, 100.0, prune_window.isoformat()),   # KEEP (has reserva)
            ],
        )
        # session_logs: one old (PRUNE), one recent (KEEP)
        conn.executemany(
            "INSERT INTO session_logs (session_id, username, login_time) VALUES (?, ?, ?)",
            [
                ("s-old",    "u1", old.isoformat()),
                ("s-recent", "u2", recent.isoformat()),
            ],
        )
        conn.commit()
        conn.close()

    def test_prunes_old_price_calculations_without_reservation(self, tmp_path):
        db_path = tmp_path / "ret.db"
        self._seed_test_db(db_path)

        import sqlite3
        run = _load_retention_module().run

        deleted = run(db_path=db_path, price_days=90, session_days=365, dry_run=False)
        assert deleted >= 1

        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        # Old no-reserva should be gone
        assert c.execute(
            "SELECT COUNT(*) FROM price_calculations WHERE reservation_id IS NULL"
        ).fetchone()[0] == 1  # only the recent one survived
        # Old with-reserva should still be there (rule keeps it)
        assert c.execute(
            "SELECT COUNT(*) FROM price_calculations WHERE reservation_id = 'R1'"
        ).fetchone()[0] == 1
        conn.close()

    def test_prunes_old_session_logs(self, tmp_path):
        db_path = tmp_path / "ret.db"
        self._seed_test_db(db_path)

        run = _load_retention_module().run

        run(db_path=db_path, price_days=90, session_days=365, dry_run=False)

        import sqlite3
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        # old session pruned, recent kept
        assert c.execute("SELECT COUNT(*) FROM session_logs WHERE session_id='s-old'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM session_logs WHERE session_id='s-recent'").fetchone()[0] == 1
        conn.close()

    def test_dry_run_changes_nothing(self, tmp_path):
        db_path = tmp_path / "ret.db"
        self._seed_test_db(db_path)

        run = _load_retention_module().run

        import sqlite3
        conn = sqlite3.connect(str(db_path))
        before_pc = conn.execute("SELECT COUNT(*) FROM price_calculations").fetchone()[0]
        before_sl = conn.execute("SELECT COUNT(*) FROM session_logs").fetchone()[0]
        conn.close()

        run(db_path=db_path, price_days=90, session_days=365, dry_run=True)

        conn = sqlite3.connect(str(db_path))
        after_pc = conn.execute("SELECT COUNT(*) FROM price_calculations").fetchone()[0]
        after_sl = conn.execute("SELECT COUNT(*) FROM session_logs").fetchone()[0]
        conn.close()

        assert before_pc == after_pc
        assert before_sl == after_sl

    def test_idempotent(self, tmp_path):
        db_path = tmp_path / "ret.db"
        self._seed_test_db(db_path)

        run = _load_retention_module().run

        # First run prunes
        run(db_path=db_path, price_days=90, session_days=365, dry_run=False)
        # Second run is a no-op
        deleted_again = run(db_path=db_path, price_days=90, session_days=365, dry_run=False)
        assert deleted_again == 0
