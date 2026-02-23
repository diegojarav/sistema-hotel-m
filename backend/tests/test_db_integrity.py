"""
Tests for database schema integrity: tables, FK constraints, unique constraints.
"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from datetime import date, time

from database import (
    Base, User, Room, RoomCategory, Reservation, CheckIn,
    ICalFeed, Property,
)


def test_all_tables_created(db_session):
    """Verify all expected tables exist after create_all."""
    inspector = inspect(db_session.bind)
    tables = set(inspector.get_table_names())
    expected = {
        "users", "session_logs", "room_categories", "rooms",
        "reservations", "checkins", "system_settings",
        "client_types", "client_contracts", "pricing_seasons",
        "price_calculations", "properties", "ical_feeds",
        "ai_agent_permissions",
    }
    for t in expected:
        assert t in tables, f"Missing table: {t}"


def test_user_unique_username(db_session):
    """Duplicate username should raise IntegrityError."""
    u1 = User(username="testuser", password="hash1", role="admin")
    u2 = User(username="testuser", password="hash2", role="admin")
    db_session.add(u1)
    db_session.commit()
    db_session.add(u2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_room_category_fk(db_session, seed_rooms):
    """Room.category_id must reference an existing category."""
    room = seed_rooms["rooms"][0]
    assert room.category_id == "los-monges-estandar"
    # Verify category exists
    cat = db_session.query(RoomCategory).get(room.category_id)
    assert cat is not None
    assert cat.name == "Estandar"


def test_reservation_room_fk(db_session, seed_rooms):
    """Reservation.room_id references a valid room."""
    room = seed_rooms["rooms"][0]
    res = Reservation(
        id="0001000",
        check_in_date=date(2026, 6, 1),
        stay_days=2,
        guest_name="Test",
        room_id=room.id,
        status="Confirmada",
        price=100000,
        property_id="los-monges",
        reserved_by="test",
        received_by="test",
        contact_phone="",
    )
    db_session.add(res)
    db_session.commit()

    fetched = db_session.query(Reservation).get("0001000")
    assert fetched.room_id == room.id


def test_checkin_reservation_fk(db_session, seed_rooms):
    """CheckIn.reservation_id can link to an existing reservation."""
    room = seed_rooms["rooms"][0]
    res = Reservation(
        id="0001001",
        check_in_date=date(2026, 6, 1),
        stay_days=2,
        guest_name="Test",
        room_id=room.id,
        status="Confirmada",
        price=100000,
        property_id="los-monges",
        reserved_by="test",
        received_by="test",
        contact_phone="",
    )
    db_session.add(res)
    db_session.flush()

    ci = CheckIn(
        room_id=room.id,
        reservation_id="0001001",
        created_at=date.today(),
        check_in_time=time(14, 0),
        last_name="Test",
        first_name="Guest",
        document_number="12345",
    )
    db_session.add(ci)
    db_session.commit()

    fetched = db_session.query(CheckIn).first()
    assert fetched.reservation_id == "0001001"


def test_checkin_reservation_nullable(db_session, seed_rooms):
    """CheckIn.reservation_id is nullable (unlinked check-in)."""
    room = seed_rooms["rooms"][0]
    ci = CheckIn(
        room_id=room.id,
        reservation_id=None,
        created_at=date.today(),
        check_in_time=time(14, 0),
        last_name="NoReservation",
        document_number="99999",
    )
    db_session.add(ci)
    db_session.commit()

    fetched = db_session.query(CheckIn).first()
    assert fetched.reservation_id is None


def test_ical_feed_room_fk(db_session, seed_rooms):
    """ICalFeed.room_id references an existing room."""
    room = seed_rooms["rooms"][0]
    feed = ICalFeed(
        room_id=room.id,
        source="Booking.com",
        ical_url="https://example.com/feed.ics",
        sync_enabled=1,
    )
    db_session.add(feed)
    db_session.commit()

    fetched = db_session.query(ICalFeed).first()
    assert fetched.room_id == room.id
    assert fetched.source == "Booking.com"


def test_reservation_id_format(db_session, seed_rooms):
    """Reservation IDs are string format (zero-padded)."""
    room = seed_rooms["rooms"][0]
    res = Reservation(
        id="0001255",
        check_in_date=date(2026, 6, 1),
        stay_days=1,
        guest_name="Test",
        room_id=room.id,
        status="Confirmada",
        price=0,
        property_id="los-monges",
        reserved_by="test",
        received_by="test",
        contact_phone="",
    )
    db_session.add(res)
    db_session.commit()

    fetched = db_session.query(Reservation).get("0001255")
    assert fetched is not None
    assert len(fetched.id) == 7
