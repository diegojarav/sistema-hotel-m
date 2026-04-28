"""
Service- and API-layer tests for the Building entity (v1.10.0 — Phase 2a).
"""

import pytest

from database import Building, Room
from services.building_service import BuildingService, BuildingServiceError


@pytest.fixture
def seed_one_building(db_session, seed_property):
    """Plant one building under los-monges."""
    b = Building(
        id="los-monges-principal",
        property_id="los-monges",
        name="Edificio Principal",
        sort_order=0,
        is_active=True,
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


# ======================================================================
# CREATE
# ======================================================================
class TestCreateBuilding:
    def test_minimum_fields(self, db_session, seed_property):
        b = BuildingService.create_building(
            db=db_session, property_id="los-monges",
            data={"id": "los-monges-anexo", "name": "Anexo Norte"},
        )
        assert b.id == "los-monges-anexo"
        assert b.is_active is True
        assert b.sort_order == 0

    def test_duplicate_id_rejected(self, db_session, seed_one_building):
        with pytest.raises(BuildingServiceError):
            BuildingService.create_building(
                db=db_session, property_id="los-monges",
                data={"id": "los-monges-principal", "name": "Otro"},
            )

    def test_duplicate_name_per_property_rejected(self, db_session, seed_one_building):
        with pytest.raises(BuildingServiceError):
            BuildingService.create_building(
                db=db_session, property_id="los-monges",
                data={"id": "los-monges-otro", "name": "Edificio Principal"},
            )

    def test_blank_name_rejected(self, db_session, seed_property):
        with pytest.raises(BuildingServiceError):
            BuildingService.create_building(
                db=db_session, property_id="los-monges",
                data={"id": "x", "name": "   "},
            )


# ======================================================================
# READ + LIST
# ======================================================================
class TestReadBuilding:
    def test_get_by_id(self, db_session, seed_one_building):
        b = BuildingService.get_building(db=db_session, building_id="los-monges-principal")
        assert b is not None
        assert b.name == "Edificio Principal"

    def test_get_missing(self, db_session, seed_property):
        assert BuildingService.get_building(db=db_session, building_id="nope") is None

    def test_list_includes_room_count(self, db_session, seed_one_building, seed_rooms):
        # Backfill rooms to point at the seeded building
        for r in db_session.query(Room).all():
            r.building_id = seed_one_building.id
        db_session.commit()

        rows = BuildingService.list_buildings(db=db_session, property_id="los-monges")
        assert len(rows) == 1
        assert rows[0]["room_count"] == len(seed_rooms["rooms"])

    def test_list_excludes_inactive(self, db_session, seed_one_building):
        BuildingService.update_building(
            db=db_session, building_id=seed_one_building.id, data={"is_active": False},
        )
        rows = BuildingService.list_buildings(db=db_session, property_id="los-monges", active_only=True)
        assert rows == []
        rows_all = BuildingService.list_buildings(db=db_session, property_id="los-monges", active_only=False)
        assert len(rows_all) == 1


# ======================================================================
# UPDATE
# ======================================================================
class TestUpdateBuilding:
    def test_rename(self, db_session, seed_one_building):
        b = BuildingService.update_building(
            db=db_session, building_id=seed_one_building.id, data={"name": "Edificio Norte"},
        )
        assert b.name == "Edificio Norte"

    def test_rename_collision(self, db_session, seed_one_building):
        BuildingService.create_building(
            db=db_session, property_id="los-monges",
            data={"id": "los-monges-anexo", "name": "Anexo"},
        )
        with pytest.raises(BuildingServiceError):
            BuildingService.update_building(
                db=db_session, building_id=seed_one_building.id,
                data={"name": "Anexo"},
            )

    def test_missing_returns_none(self, db_session, seed_property):
        assert BuildingService.update_building(db=db_session, building_id="nope", data={"name": "x"}) is None


# ======================================================================
# API LAYER
# ======================================================================
class TestBuildingsEndpoints:
    def test_list_unauthenticated(self, client, seed_property):
        r = client.get("/api/v1/buildings")
        assert r.status_code in (401, 403)

    def test_list_authenticated(self, client, auth_headers_admin, seed_one_building):
        r = client.get("/api/v1/buildings", headers=auth_headers_admin)
        assert r.status_code == 200
        assert any(b["name"] == "Edificio Principal" for b in r.json())

    def test_create_admin_only(self, client, auth_headers_recep, seed_property):
        r = client.post(
            "/api/v1/buildings",
            headers=auth_headers_recep,
            json={"id": "los-monges-anexo", "name": "Anexo"},
        )
        assert r.status_code == 403

    def test_create_admin_succeeds(self, client, auth_headers_admin, seed_property):
        r = client.post(
            "/api/v1/buildings",
            headers=auth_headers_admin,
            json={"id": "los-monges-anexo", "name": "Anexo Norte", "floors": 2},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "Anexo Norte"
        assert data["floors"] == 2
        assert data["room_count"] == 0

    def test_update_admin_only(self, client, auth_headers_recep, seed_one_building):
        r = client.put(
            f"/api/v1/buildings/{seed_one_building.id}",
            headers=auth_headers_recep,
            json={"name": "X"},
        )
        assert r.status_code == 403
