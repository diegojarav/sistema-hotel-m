"""
Multi-vehicle per reservation (v1.10.0 — Phase 2c).

Covers:
- ReservationCreate.vehicles list accepted on creation
- Quick-add mode (no guest link) writes reservation_vehicles snapshot
- Linked mode validates guest_vehicle_id + property; copies snapshot
- is_primary populates legacy reservations.vehicle_plate / model
- Default primary is index 0 when none flagged
- Parking-capacity cap: N vehicles > capacity → 400
- Per-vehicle parking accounting overrides per-room legacy count
- GET /reservations/{id} returns the vehicles list
- search_by_plate falls through to reservation_vehicles for quick-adds
- Empty vehicles list keeps legacy single-vehicle path untouched
- Quick-add vehicles get promoted to guest_vehicles best-effort
- ON DELETE CASCADE: reservation_vehicles rows die with the reservation
"""
from datetime import date, timedelta

import pytest
from fastapi import status

from database import (
    GuestVehicle,
    Reservation,
    ReservationVehicle,
)
from schemas import ReservationCreate, VehicleInput
from services import (
    GuestService,
    GuestVehicleService,
    ReservationService,
    SettingsService,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def guest_with_2_vehicles(db_session, seed_property):
    """Booker with 2 master vehicles registered — used for 'linked' mode."""
    g = GuestService.create_guest(
        db=db_session, property_id="los-monges",
        data={"first_name": "Multi", "last_name": "VehOwner", "document_number": "MV-001"},
    )
    v1 = GuestVehicleService.create_vehicle(
        db=db_session, guest_id=g.id, property_id="los-monges",
        data={"plate_number": "OWN-001", "model": "Toyota Hilux", "color": "Blanco"},
    )
    v2 = GuestVehicleService.create_vehicle(
        db=db_session, guest_id=g.id, property_id="los-monges",
        data={"plate_number": "OWN-002", "model": "Honda Civic", "color": "Negro"},
    )
    return {"guest": g, "vehicles": [v1, v2]}


def _base_reservation_payload(rooms):
    """Minimal valid ReservationCreate kwargs (caller adds vehicles + parking)."""
    return {
        "check_in_date": date.today() + timedelta(days=1),
        "stay_days": 2,
        "guest_name": "MultiTest, Cliente",
        "room_ids": [rooms[0].id],
        "price": 200000.0,
        "received_by": "tester",
    }


def _set_parking_capacity(db_session, capacity: int):
    """Use the proper SettingsService API (system_settings has integer
    autoincrement-less PK — raw INSERT fails). The service handles ID
    generation internally."""
    SettingsService.set_parking_capacity(db_session, capacity)


# ======================================================================
# Quick-add mode
# ======================================================================
class TestQuickAdd:
    def test_single_quick_vehicle_writes_reservation_vehicles_row(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number="qck-9", model="Fiat Mobi", color="Rojo")
            ],
        })
        data = ReservationCreate(**payload)
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1

        rvs = db_session.query(ReservationVehicle).filter(
            ReservationVehicle.reservation_id == ids[0]
        ).all()
        assert len(rvs) == 1
        rv = rvs[0]
        assert rv.guest_vehicle_id is None  # quick-add → no master link
        assert rv.plate_number == "QCK-9"   # normalised
        assert rv.model == "Fiat Mobi"
        assert rv.color == "Rojo"
        assert rv.is_primary is True        # only one → primary

    def test_quick_add_promotes_to_guest_vehicles_when_booker_known(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        """Quick-add chapas also land in the master catalogue under the
        booker's name (best-effort), so search_by_plate finds them and
        next time the same chapa returns it's already in linked mode."""
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number="PROMO-1", model="Renault Kwid")
            ],
        })
        data = ReservationCreate(**payload)
        ReservationService.create_reservations(db_session, data)

        # Master GuestVehicle should now exist for this chapa under the booker
        gv = db_session.query(GuestVehicle).filter(
            GuestVehicle.guest_id == guest_with_2_vehicles["guest"].id,
            GuestVehicle.plate_number == "PROMO-1",
        ).first()
        assert gv is not None


# ======================================================================
# Linked mode
# ======================================================================
class TestLinkedMode:
    def test_linked_validates_master_exists(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="linked", guest_vehicle_id=guest_with_2_vehicles["vehicles"][0].id)
            ],
        })
        data = ReservationCreate(**payload)
        ids = ReservationService.create_reservations(db_session, data)

        rv = db_session.query(ReservationVehicle).filter(
            ReservationVehicle.reservation_id == ids[0]
        ).first()
        assert rv.guest_vehicle_id == guest_with_2_vehicles["vehicles"][0].id
        # snapshot copied from master
        assert rv.plate_number == "OWN-001"
        assert rv.model == "Toyota Hilux"
        assert rv.color == "Blanco"

    def test_linked_rejects_unknown_vehicle_id_with_spanish_400(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [VehicleInput(mode="linked", guest_vehicle_id=99999)],
        })
        data = ReservationCreate(**payload)
        with pytest.raises(ValueError) as exc:
            ReservationService.create_reservations(db_session, data)
        assert "99999" in str(exc.value)
        assert "no encontrado" in str(exc.value).lower() or "no pertenece" in str(exc.value).lower()


# ======================================================================
# Primary vehicle / legacy back-compat
# ======================================================================
class TestPrimaryAndLegacy:
    def test_primary_vehicle_snapshots_to_legacy_columns(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        """is_primary=True row's plate/model also write to
        reservations.vehicle_plate / vehicle_model (back-compat)."""
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number="ABC-A1", model="A"),
                VehicleInput(mode="quick", plate_number="XYZ-Z9", model="Z", is_primary=True),
            ],
        })
        data = ReservationCreate(**payload)
        ids = ReservationService.create_reservations(db_session, data)
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.vehicle_plate == "XYZ-Z9"   # primary wins, not index 0
        assert res.vehicle_model == "Z"

    def test_default_primary_is_index_0_when_none_marked(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number="FIRST-1"),
                VehicleInput(mode="quick", plate_number="SECOND-2"),
            ],
        })
        data = ReservationCreate(**payload)
        ids = ReservationService.create_reservations(db_session, data)
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.vehicle_plate == "FIRST-1"

    def test_empty_vehicles_list_keeps_legacy_single_path(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        """When vehicles=[] is omitted, the old single vehicle_plate path runs."""
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicle_plate": "LEGACY-1",
            "vehicle_model": "Legacy Model",
        })
        data = ReservationCreate(**payload)
        ids = ReservationService.create_reservations(db_session, data)
        # No reservation_vehicles rows created
        rvs = db_session.query(ReservationVehicle).filter(
            ReservationVehicle.reservation_id == ids[0]
        ).all()
        assert rvs == []
        # Legacy columns populated
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert res.vehicle_plate == "LEGACY-1"


# ======================================================================
# Parking capacity rules
# ======================================================================
class TestParkingCapacity:
    def test_more_vehicles_than_capacity_rejected(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 2)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number=f"V-{i}") for i in range(3)
            ],
        })
        data = ReservationCreate(**payload)
        with pytest.raises(ValueError) as exc:
            ReservationService.create_reservations(db_session, data)
        msg = str(exc.value)
        assert "3" in msg and "2" in msg  # 3 vehicles vs 2 capacity
        assert "capacidad total" in msg.lower()

    def test_n_vehicles_consume_n_parking_slots(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        """Booking A has 2 vehicles. Booking B with 1 vehicle should fail if
        capacity is 2 (already full by A)."""
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 2)
        # A: 1 room, 2 vehicles
        a_payload = _base_reservation_payload(rooms)
        a_payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number="A-1"),
                VehicleInput(mode="quick", plate_number="A-2"),
            ],
        })
        ReservationService.create_reservations(db_session, ReservationCreate(**a_payload))

        # B: overlapping dates, 1 vehicle — should fail (parking full)
        b_payload = _base_reservation_payload(rooms)
        b_payload["room_ids"] = [rooms[1].id]
        b_payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [VehicleInput(mode="quick", plate_number="B-1")],
        })
        with pytest.raises(ValueError) as exc:
            ReservationService.create_reservations(db_session, ReservationCreate(**b_payload))
        assert "lleno" in str(exc.value).lower() or "ocupados" in str(exc.value).lower()


# ======================================================================
# search_by_plate falls through to reservation_vehicles
# ======================================================================
class TestSearchByPlateFallthrough:
    def test_quick_add_companion_findable_by_plate(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        """A quick-add plate (no master guest record) should still surface
        via search_by_plate (used by AI agent + future OCR)."""
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                # First vehicle is the booker's linked one
                VehicleInput(mode="linked", guest_vehicle_id=guest_with_2_vehicles["vehicles"][0].id),
                # Second is a stranger's companion car — no master
                VehicleInput(mode="quick", plate_number="COMP-ANION"),
            ],
        })
        data = ReservationCreate(**payload)
        ReservationService.create_reservations(db_session, data)

        # search_by_plate should find the companion via fallthrough.
        # Note: the quick-add promotion to master also happens, so this
        # MIGHT match via guest_vehicles. Either path is acceptable —
        # the contract is "findable by plate".
        result = GuestVehicleService.search_by_plate(
            db=db_session, property_id="los-monges", plate="COMP-ANION"
        )
        assert result is not None
        assert result["vehicle"].plate_number == "COMP-ANION"


# ======================================================================
# Endpoint integration
# ======================================================================
class TestEndpointReturnsVehiclesList:
    def test_get_reservation_includes_vehicles_field(
        self, client, db_session, seed_rooms, auth_headers_admin, guest_with_2_vehicles
    ):
        """GET /api/v1/reservations/{id} must include the vehicles list."""
        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [
                VehicleInput(mode="quick", plate_number="API-001", model="Demo", is_primary=True),
                VehicleInput(mode="quick", plate_number="API-002"),
            ],
        })
        ids = ReservationService.create_reservations(db_session, ReservationCreate(**payload))

        r = client.get(
            f"/api/v1/reservations/{ids[0]}",
            headers=auth_headers_admin,
        )
        assert r.status_code == status.HTTP_200_OK
        body = r.json()
        assert "vehicles" in body
        plates = sorted([v["plate_number"] for v in body["vehicles"]])
        assert plates == ["API-001", "API-002"]
        # Primary flag preserved
        primary = [v for v in body["vehicles"] if v["is_primary"]]
        assert len(primary) == 1
        assert primary[0]["plate_number"] == "API-001"


# ======================================================================
# Cascade delete
# ======================================================================
class TestCascadeDelete:
    def test_reservation_delete_cascades_to_reservation_vehicles(
        self, db_session, seed_rooms, guest_with_2_vehicles
    ):
        """Dropping a reservation should remove its reservation_vehicles rows
        via ON DELETE CASCADE.

        SQLite needs PRAGMA foreign_keys=ON per connection to honour FK
        cascades; we set it explicitly here (the test_db_constraints suite
        does the same — without it, the StaticPool connection has FKs off
        by default)."""
        from sqlalchemy import text

        rooms = seed_rooms["rooms"]
        _set_parking_capacity(db_session, 5)
        # Enable FK enforcement on this connection
        db_session.execute(text("PRAGMA foreign_keys=ON"))

        payload = _base_reservation_payload(rooms)
        payload.update({
            "parking_needed": True,
            "guest_id": guest_with_2_vehicles["guest"].id,
            "vehicles": [VehicleInput(mode="quick", plate_number="DEL-1")],
        })
        ids = ReservationService.create_reservations(db_session, ReservationCreate(**payload))
        # Sanity: row exists
        assert db_session.query(ReservationVehicle).filter(
            ReservationVehicle.reservation_id == ids[0]
        ).count() == 1

        # Delete reservation — FK CASCADE should sweep reservation_vehicles
        res = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        db_session.delete(res)
        db_session.commit()

        remaining = db_session.query(ReservationVehicle).filter(
            ReservationVehicle.reservation_id == ids[0]
        ).count()
        assert remaining == 0
