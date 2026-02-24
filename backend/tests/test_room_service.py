"""
Phase 2 — Service-layer tests for RoomService (PC/Streamlit path).
"""

from datetime import date, timedelta
from services.room_service import RoomService
from database import Room


class TestGetAllCategories:
    def test_returns_categories(self, db_session, seed_rooms):
        cats = RoomService.get_all_categories(db_session)
        assert len(cats) == 2
        names = {c["name"] for c in cats}
        assert "Estandar" in names
        assert "Suite" in names

    def test_category_has_price(self, db_session, seed_rooms):
        cats = RoomService.get_all_categories(db_session)
        estandar = next(c for c in cats if c["name"] == "Estandar")
        assert estandar["base_price"] == 150000.0

    def test_empty_when_no_categories(self, db_session, seed_property):
        cats = RoomService.get_all_categories(db_session)
        assert cats == []


class TestGetAvailableRooms:
    def test_all_free(self, db_session, seed_rooms):
        ci = date.today() + timedelta(days=30)
        co = ci + timedelta(days=2)
        rooms = RoomService.get_available_rooms(db_session, ci, co)
        assert len(rooms) == 6

    def test_one_occupied(self, db_session, seed_rooms, make_reservation):
        ci = date.today() + timedelta(days=30)
        co = ci + timedelta(days=2)
        make_reservation(check_in_date=ci, stay_days=2,
                         room_id=seed_rooms["rooms"][0].id)
        rooms = RoomService.get_available_rooms(db_session, ci, co)
        assert len(rooms) == 5
        ids = {r["id"] for r in rooms}
        assert seed_rooms["rooms"][0].id not in ids

    def test_filter_by_category(self, db_session, seed_rooms):
        ci = date.today() + timedelta(days=30)
        co = ci + timedelta(days=2)
        rooms = RoomService.get_available_rooms(
            db_session, ci, co, category_id="los-monges-suite"
        )
        assert len(rooms) == 2
        for r in rooms:
            assert r["category_name"] == "Suite"

    def test_room_has_expected_fields(self, db_session, seed_rooms):
        ci = date.today() + timedelta(days=30)
        co = ci + timedelta(days=2)
        rooms = RoomService.get_available_rooms(db_session, ci, co)
        r = rooms[0]
        assert "id" in r
        assert "internal_code" in r
        assert "category_name" in r
        assert "base_price" in r


class TestGetRoomPrice:
    def test_category_base_price(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        price = RoomService.get_room_price(db_session, room.id)
        assert price == 150000.0

    def test_custom_price(self, db_session, seed_rooms):
        room = seed_rooms["rooms"][0]
        room.custom_price = 180000.0
        db_session.commit()
        price = RoomService.get_room_price(db_session, room.id)
        assert price == 180000.0

    def test_not_found(self, db_session, seed_rooms):
        price = RoomService.get_room_price(db_session, "nonexistent")
        assert price == 0.0


class TestGetAllRooms:
    def test_returns_all_active(self, db_session, seed_rooms):
        rooms = RoomService.get_all_rooms(db_session)
        assert len(rooms) == 6

    def test_excludes_inactive(self, db_session, seed_rooms):
        seed_rooms["rooms"][0].active = 0
        db_session.commit()
        rooms = RoomService.get_all_rooms(db_session, active_only=True)
        assert len(rooms) == 5

    def test_includes_inactive(self, db_session, seed_rooms):
        seed_rooms["rooms"][0].active = 0
        db_session.commit()
        rooms = RoomService.get_all_rooms(db_session, active_only=False)
        assert len(rooms) == 6
