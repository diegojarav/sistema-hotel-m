"""
Service- and API-layer tests for GuestVehicle (v1.10.0 — Phase 2a-ext).
Includes the per-stay CheckinVehicle link + the plate-search lookup.
"""
from datetime import date, timedelta

import pytest

from database import CheckIn, CheckinVehicle, Guest, GuestVehicle, Reservation
from schemas import CheckInCreate, ReservationCreate
from services import (
    CheckInService,
    GuestService,
    GuestVehicleError,
    GuestVehicleService,
    MAX_VEHICLES_PER_GUEST,
    ReservationService,
)


@pytest.fixture
def seed_one_guest_for_vehicles(db_session, seed_property):
    g = GuestService.create_guest(
        db=db_session, property_id="los-monges",
        data={"first_name": "Veh", "last_name": "Owner"},
    )
    return g


# ======================================================================
# Vehicle CRUD
# ======================================================================
class TestCreateVehicle:
    def test_basic(self, db_session, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges",
            data={"plate_number": "abc-123", "model": "Toyota Corolla 2020", "color": "Blanco"},
        )
        # Plate normalised to uppercase
        assert v.plate_number == "ABC-123"
        assert v.is_active is True

    def test_dedup_returns_existing(self, db_session, seed_one_guest_for_vehicles):
        gid = seed_one_guest_for_vehicles.id
        v1 = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"plate_number": "DUP-1"},
        )
        v2 = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"plate_number": "dup-1"},
        )
        assert v2.id == v1.id  # same row returned

    def test_blank_plate_rejected(self, db_session, seed_one_guest_for_vehicles):
        with pytest.raises(GuestVehicleError):
            GuestVehicleService.create_vehicle(
                db=db_session, guest_id=seed_one_guest_for_vehicles.id,
                property_id="los-monges", data={"plate_number": "   "},
            )

    def test_max_5_per_guest(self, db_session, seed_one_guest_for_vehicles):
        gid = seed_one_guest_for_vehicles.id
        for i in range(MAX_VEHICLES_PER_GUEST):
            GuestVehicleService.create_vehicle(
                db=db_session, guest_id=gid, property_id="los-monges",
                data={"plate_number": f"PLATE-{i}"},
            )
        # The 6th must fail
        with pytest.raises(GuestVehicleError) as exc:
            GuestVehicleService.create_vehicle(
                db=db_session, guest_id=gid, property_id="los-monges",
                data={"plate_number": "PLATE-OVERFLOW"},
            )
        assert "Límite" in str(exc.value)

    def test_soft_deleted_does_not_count_toward_limit(self, db_session, seed_one_guest_for_vehicles):
        gid = seed_one_guest_for_vehicles.id
        first = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"plate_number": "ZZZ-001"},
        )
        for i in range(1, MAX_VEHICLES_PER_GUEST):
            GuestVehicleService.create_vehicle(
                db=db_session, guest_id=gid, property_id="los-monges",
                data={"plate_number": f"FILLER-{i}"},
            )
        # At limit — soft-delete one and add another
        GuestVehicleService.delete_vehicle(db=db_session, vehicle_id=first.id)
        new_v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"plate_number": "REPLACEMENT-1"},
        )
        assert new_v.id != first.id

    def test_create_for_unknown_guest_rejected(self, db_session, seed_property):
        with pytest.raises(GuestVehicleError):
            GuestVehicleService.create_vehicle(
                db=db_session, guest_id=99999, property_id="los-monges",
                data={"plate_number": "X"},
            )


class TestUpdateVehicle:
    def test_update_color(self, db_session, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges",
            data={"plate_number": "UPD-1", "color": "Negro"},
        )
        u = GuestVehicleService.update_vehicle(
            db=db_session, vehicle_id=v.id, data={"color": "Rojo"},
        )
        assert u.color == "Rojo"

    def test_update_normalises_plate(self, db_session, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "OLD-1"},
        )
        u = GuestVehicleService.update_vehicle(
            db=db_session, vehicle_id=v.id, data={"plate_number": "  new-2 "},
        )
        assert u.plate_number == "NEW-2"


class TestDeleteVehicle:
    def test_soft_delete(self, db_session, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "DEL-1"},
        )
        ok = GuestVehicleService.delete_vehicle(db=db_session, vehicle_id=v.id)
        assert ok is True
        db_session.refresh(v)
        assert v.is_active is False


# ======================================================================
# Plate search — "whose car is this?"
# ======================================================================
class TestSearchByPlate:
    def test_finds_exact_match(self, db_session, seed_one_guest_for_vehicles):
        GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges",
            data={"plate_number": "EXACT-99", "model": "Hilux"},
        )
        result = GuestVehicleService.search_by_plate(
            db=db_session, property_id="los-monges", plate="EXACT-99",
        )
        assert result is not None
        assert result["vehicle"].plate_number == "EXACT-99"
        assert result["guest"].id == seed_one_guest_for_vehicles.id

    def test_case_insensitive_partial_match(self, db_session, seed_one_guest_for_vehicles):
        GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "AAA-9999"},
        )
        result = GuestVehicleService.search_by_plate(
            db=db_session, property_id="los-monges", plate="aaa",  # partial + lowercase
        )
        assert result is not None

    def test_returns_none_when_no_match(self, db_session, seed_property):
        result = GuestVehicleService.search_by_plate(
            db=db_session, property_id="los-monges", plate="NOTFOUND",
        )
        assert result is None

    def test_returns_active_reservation(
        self, db_session, seed_full, make_reservation
    ):
        # Create guest + vehicle + active reservation
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Active", "last_name": "Reserv"},
        )
        GuestVehicleService.create_vehicle(
            db=db_session, guest_id=g.id, property_id="los-monges",
            data={"plate_number": "ACT-1"},
        )
        r = make_reservation(
            check_in_date=date.today(),
            stay_days=2,
            guest_name="Reserv, Active",
            status="Confirmada",
        )
        r.guest_id = g.id
        db_session.commit()

        result = GuestVehicleService.search_by_plate(
            db=db_session, property_id="los-monges", plate="ACT-1",
        )
        assert result is not None
        assert result["active_reservation"] is not None
        assert result["active_reservation"]["id"] == r.id

    def test_no_active_reservation_returns_none_for_that_field(
        self, db_session, seed_one_guest_for_vehicles
    ):
        GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "NORES-1"},
        )
        result = GuestVehicleService.search_by_plate(
            db=db_session, property_id="los-monges", plate="NORES-1",
        )
        assert result is not None
        assert result["active_reservation"] is None


# ======================================================================
# Per-stay link (CheckinVehicle)
# ======================================================================
class TestLinkToCheckin:
    def test_link_creates_row(self, db_session, seed_full, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "LINK-1"},
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=seed_one_guest_for_vehicles.id,
            last_name="Link",
            first_name="Test",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()
        link = GuestVehicleService.link_to_checkin(
            db=db_session, checkin_id=ci.id, vehicle_id=v.id, parking_spot="A-12",
        )
        assert link.id is not None
        assert link.parking_spot == "A-12"

    def test_link_idempotent(self, db_session, seed_full, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "IDEM-1"},
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=seed_one_guest_for_vehicles.id,
            last_name="Idem",
            first_name="Test",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()

        l1 = GuestVehicleService.link_to_checkin(
            db=db_session, checkin_id=ci.id, vehicle_id=v.id,
        )
        l2 = GuestVehicleService.link_to_checkin(
            db=db_session, checkin_id=ci.id, vehicle_id=v.id, parking_spot="B-05",
        )
        assert l1.id == l2.id  # same row
        # parking spot updated
        db_session.refresh(l1)
        assert l1.parking_spot == "B-05"

    def test_unlink(self, db_session, seed_full, seed_one_guest_for_vehicles):
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=seed_one_guest_for_vehicles.id,
            property_id="los-monges", data={"plate_number": "UNLINK-1"},
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=seed_one_guest_for_vehicles.id,
            last_name="Unlink",
            first_name="Test",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()
        GuestVehicleService.link_to_checkin(
            db=db_session, checkin_id=ci.id, vehicle_id=v.id,
        )
        ok = GuestVehicleService.unlink_from_checkin(
            db=db_session, checkin_id=ci.id, vehicle_id=v.id,
        )
        assert ok is True
        # Second unlink returns False (idempotent)
        ok2 = GuestVehicleService.unlink_from_checkin(
            db=db_session, checkin_id=ci.id, vehicle_id=v.id,
        )
        assert ok2 is False

    def test_get_checkin_vehicles(self, db_session, seed_full, seed_one_guest_for_vehicles):
        gid = seed_one_guest_for_vehicles.id
        v1 = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"plate_number": "CV-1", "model": "Civic"},
        )
        v2 = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"plate_number": "CV-2", "color": "Negro"},
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=gid,
            last_name="Multi", first_name="Vehicle",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()
        GuestVehicleService.link_to_checkin(db=db_session, checkin_id=ci.id, vehicle_id=v1.id)
        GuestVehicleService.link_to_checkin(db=db_session, checkin_id=ci.id, vehicle_id=v2.id)
        rows = GuestVehicleService.get_checkin_vehicles(db=db_session, checkin_id=ci.id)
        assert len(rows) == 2
        plates = sorted(r["plate_number"] for r in rows)
        assert plates == ["CV-1", "CV-2"]


# ======================================================================
# Integration: checkin auto-creates GuestVehicle + link
# ======================================================================
class TestCheckinAutoCreatesVehicle:
    def test_register_checkin_creates_vehicle_and_link(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ci_data = CheckInCreate(
            room_id=room_id,
            last_name="Veh", first_name="Auto",
            document_number="VEH-AUTO-1",
            vehicle_model="Mustang 2024",
            vehicle_plate="MST-2024",
        )
        cid = CheckInService.register_checkin(db_session, ci_data)
        ci = db_session.query(CheckIn).filter(CheckIn.id == cid).first()
        assert ci.guest_id is not None

        # Vehicle was auto-created under the guest
        vehicles = db_session.query(GuestVehicle).filter(
            GuestVehicle.guest_id == ci.guest_id
        ).all()
        assert len(vehicles) == 1
        assert vehicles[0].plate_number == "MST-2024"
        assert vehicles[0].model == "Mustang 2024"

        # CheckinVehicle link exists
        links = db_session.query(CheckinVehicle).filter(
            CheckinVehicle.checkin_id == ci.id
        ).all()
        assert len(links) == 1
        assert links[0].vehicle_id == vehicles[0].id


# ======================================================================
# API LAYER
# ======================================================================
class TestVehicleEndpoints:
    def test_unauthenticated(self, client, seed_property):
        r = client.get("/api/v1/huespedes/1/vehicles")
        assert r.status_code in (401, 403)

    def test_create_and_list(self, client, auth_headers_admin, seed_property):
        rg = client.post(
            "/api/v1/huespedes", headers=auth_headers_admin,
            json={"first_name": "API", "last_name": "Vehic"},
        )
        gid = rg.json()["id"]
        rv = client.post(
            f"/api/v1/huespedes/{gid}/vehicles", headers=auth_headers_admin,
            json={"plate_number": "API-001", "model": "Camry"},
        )
        assert rv.status_code == 200, rv.text
        assert rv.json()["plate_number"] == "API-001"
        rl = client.get(f"/api/v1/huespedes/{gid}/vehicles", headers=auth_headers_admin)
        assert any(v["plate_number"] == "API-001" for v in rl.json())

    def test_search_endpoint_finds(self, client, auth_headers_admin, seed_property):
        rg = client.post(
            "/api/v1/huespedes", headers=auth_headers_admin,
            json={"first_name": "Search", "last_name": "Plate"},
        )
        gid = rg.json()["id"]
        client.post(
            f"/api/v1/huespedes/{gid}/vehicles", headers=auth_headers_admin,
            json={"plate_number": "SRC-9999"},
        )
        r = client.get("/api/v1/vehicles/search?plate=SRC", headers=auth_headers_admin)
        assert r.status_code == 200
        assert r.json()["vehicle"]["plate_number"] == "SRC-9999"

    def test_search_returns_404_when_missing(self, client, auth_headers_admin, seed_property):
        r = client.get("/api/v1/vehicles/search?plate=NOTFOUND", headers=auth_headers_admin)
        assert r.status_code == 404

    def test_link_to_checkin_endpoint(
        self, client, auth_headers_admin, db_session, seed_full
    ):
        # Seed: guest + vehicle + checkin
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Link", "last_name": "API"},
        )
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=g.id, property_id="los-monges",
            data={"plate_number": "LNK-API"},
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=g.id,
            last_name="API", first_name="Link",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()

        r = client.post(
            f"/api/v1/checkins/{ci.id}/vehicles/{v.id}",
            headers=auth_headers_admin,
            json={"parking_spot": "A-99", "key_deposited": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["parking_spot"] == "A-99"
        assert r.json()["key_deposited"] is True


# ======================================================================
# Reservation → GuestVehicle propagation (Phase 2a-ext fix)
# ======================================================================
class TestReservationPropagatesVehicle:
    """Pre-fix the vehicle data on a reservation never reached guest_vehicles
    until check-in. Now it propagates the moment the booking is created."""

    def _make_res(self, room_id, **overrides):
        defaults = dict(
            check_in_date=date.today() + timedelta(days=7),
            stay_days=1,
            guest_name="Reserva, Vehículo",
            guest_first_name="Vehículo",
            guest_last_name="Reserva",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            parking_needed=True,
        )
        defaults.update(overrides)
        return ReservationCreate(**defaults)

    def test_reservation_creates_master_vehicle(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        data = self._make_res(
            room_id,
            vehicle_plate="RES-AUTO-001",
            vehicle_model="Hilux 2024",
            vehicle_color="Blanco",
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.guest_id is not None
        # Vehicle was auto-registered under the guest
        vehicles = (
            db_session.query(GuestVehicle)
            .filter(GuestVehicle.guest_id == r.guest_id)
            .all()
        )
        assert len(vehicles) == 1
        assert vehicles[0].plate_number == "RES-AUTO-001"
        assert vehicles[0].model == "Hilux 2024"
        assert vehicles[0].color == "Blanco"

    def test_reservation_color_optional(self, db_session, seed_full):
        """Color blank → vehicle still created, color stays None."""
        room_id = seed_full["rooms"][0].id
        data = self._make_res(
            room_id,
            vehicle_plate="NOCOLOR-1",
            vehicle_model="Civic",
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        v = (
            db_session.query(GuestVehicle)
            .filter(GuestVehicle.guest_id == r.guest_id)
            .first()
        )
        assert v.plate_number == "NOCOLOR-1"
        assert v.color is None

    def test_reservation_no_plate_no_vehicle(self, db_session, seed_full):
        """Plate blank → propagation skipped (no vehicle row)."""
        room_id = seed_full["rooms"][0].id
        data = self._make_res(
            room_id,
            vehicle_model="No plate model",
            vehicle_plate="",  # blank
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        vehicles = (
            db_session.query(GuestVehicle)
            .filter(GuestVehicle.guest_id == r.guest_id)
            .count()
        )
        assert vehicles == 0

    def test_reservation_then_checkin_dedup_same_plate(self, db_session, seed_full):
        """Reservation creates vehicle. Subsequent checkin with same plate
        finds existing instead of creating a 2nd row."""
        room_id = seed_full["rooms"][0].id
        # 1) Reservation creates the vehicle
        ResData = self._make_res(
            room_id,
            vehicle_plate="DEDUP-1",
            vehicle_model="Onix",
            vehicle_color="Rojo",
        )
        ResData.document_number = "DEDUP-DOC-001"  # triggers auto-CheckIn too
        ResData.guest_first_name = "Dedup"
        ResData.guest_last_name = "Same"
        ids = ReservationService.create_reservations(db_session, ResData)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        gid = r.guest_id

        # Vehicle from reservation propagation
        vehicles_after_res = (
            db_session.query(GuestVehicle)
            .filter(GuestVehicle.guest_id == gid)
            .all()
        )
        assert len(vehicles_after_res) == 1

        # CheckinVehicle link from the inline auto-checkin (also from Phase 2a-ext)
        ci = (
            db_session.query(CheckIn)
            .filter(CheckIn.document_number == "DEDUP-DOC-001")
            .first()
        )
        assert ci is not None
        links_after_res = (
            db_session.query(CheckinVehicle)
            .filter(CheckinVehicle.checkin_id == ci.id)
            .count()
        )
        assert links_after_res == 1

        # 2) A separate update_checkin with same plate must NOT create another
        update = CheckInCreate(
            room_id=room_id,
            last_name="Same", first_name="Dedup",
            document_number="DEDUP-DOC-001",
            vehicle_model="Onix",
            vehicle_plate="DEDUP-1",   # same plate
            vehicle_color="Negro",     # changed color — should NOT overwrite
        )
        CheckInService.update_checkin(db_session, ci.id, update)
        vehicles_after_ci = (
            db_session.query(GuestVehicle)
            .filter(GuestVehicle.guest_id == gid)
            .all()
        )
        assert len(vehicles_after_ci) == 1  # still one
        # color stayed at original "Rojo" — never overwrite (Phase 2a-ext rule)
        assert vehicles_after_ci[0].color == "Rojo"

    def test_reservation_at_5_limit_does_not_fail_booking(self, db_session, seed_full):
        """6th vehicle from reservation form → propagation logs+swallows,
        reservation still succeeds."""
        # Pre-seed a guest + 5 active vehicles (the limit)
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={
                "first_name": "Five",
                "last_name": "Vehicles",
                "document_number": "FIVE-LIMIT-1",
            },
        )
        for i in range(MAX_VEHICLES_PER_GUEST):
            GuestVehicleService.create_vehicle(
                db=db_session, guest_id=g.id, property_id="los-monges",
                data={"plate_number": f"PLATE-{i}"},
            )

        # New reservation with a 6th plate — should NOT fail
        room_id = seed_full["rooms"][0].id
        data = self._make_res(
            room_id,
            guest_first_name="Five",
            guest_last_name="Vehicles",
            document_number="FIVE-LIMIT-1",  # matches the seeded guest
            vehicle_plate="OVERFLOW-PLATE",
            vehicle_color="Azul",
        )
        ids = ReservationService.create_reservations(db_session, data)
        # Reservation created OK
        assert len(ids) == 1
        # Master Guest still has exactly 5 active vehicles (overflow rejected)
        active_count = (
            db_session.query(GuestVehicle)
            .filter(
                GuestVehicle.guest_id == g.id,
                GuestVehicle.is_active == True,  # noqa: E712
            )
            .count()
        )
        assert active_count == MAX_VEHICLES_PER_GUEST

    def test_color_backfills_on_existing_vehicle(self, db_session, seed_full):
        """Existing vehicle has no color. Reservation with same plate +
        color set → vehicle gets the color filled (fill empty)."""
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Color", "last_name": "Backfill"},
        )
        v = GuestVehicleService.create_vehicle(
            db=db_session, guest_id=g.id, property_id="los-monges",
            data={"plate_number": "BACKFILL-1", "model": "Yaris"},
        )
        assert v.color is None

        room_id = seed_full["rooms"][0].id
        data = self._make_res(
            room_id,
            guest_first_name="Color",
            guest_last_name="Backfill",
            vehicle_plate="BACKFILL-1",
            vehicle_color="Verde",
        )
        ReservationService.create_reservations(db_session, data)
        db_session.refresh(v)
        assert v.color == "Verde"
