"""
Availability guards on the UPDATE path.

`update_reservation` used to rewrite check_in_date / stay_days / room_id
with ZERO availability checks — editing a reservation could silently
double-book a room or overflow parking, the exact bug class the E2E
marathon fixed on the create path (commit b246175). The guards are now
shared helpers (`_assert_rooms_available`, `_parking_spots_in_window`)
used by both create and update, with the edited reservation excluded
from its own conflict queries.
"""
from datetime import date, time, timedelta

import pytest

from database import Reservation
from schemas import ReservationCreate
from services import ReservationService, SettingsService

CI = date.today() + timedelta(days=40)  # hotel-day validator: future only


def _make(room_id, check_in, *, stay_days=1, doc="X", arrival=None,
          late=False, lct=None, parking=False):
    return ReservationCreate(
        check_in_date=check_in,
        stay_days=stay_days,
        guest_name=f"Guest {doc}",
        document_number=doc,
        room_ids=[room_id],
        price=120000.0,
        property_id="los-monges",
        client_type_id="los-monges-particular",
        arrival_time=arrival,
        late_checkout=late,
        late_checkout_time=lct,
        parking_needed=parking,
    )


class TestUpdateRoomOverlap:
    def test_moving_dates_onto_existing_booking_rejected(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="UOV-A"))
        ReservationService.create_reservations(
            db_session, _make(room_id, CI + timedelta(days=5), doc="UOV-B"))
        with pytest.raises(ValueError, match="ya reservada"):
            ReservationService.update_reservation(
                db_session, ids[0],
                _make(room_id, CI + timedelta(days=5), doc="UOV-A"))

    def test_switching_to_occupied_room_rejected(self, db_session, seed_full):
        room_a = seed_full["rooms"][0].id
        room_b = seed_full["rooms"][1].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_a, CI, doc="UOV-C"))
        ReservationService.create_reservations(
            db_session, _make(room_b, CI, doc="UOV-D"))
        with pytest.raises(ValueError, match="ya reservada"):
            ReservationService.update_reservation(
                db_session, ids[0], _make(room_b, CI, doc="UOV-C"))

    def test_resaving_own_window_never_self_conflicts(self, db_session, seed_full):
        # The single most important case: an edit that keeps the same dates
        # (price fix, phone fix) must not collide with the reservation itself.
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, stay_days=3, doc="UOV-E"))
        ok = ReservationService.update_reservation(
            db_session, ids[0], _make(room_id, CI, stay_days=3, doc="UOV-E"))
        assert ok is True

    def test_extending_stay_into_next_booking_rejected(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, stay_days=1, doc="UOV-F"))
        ReservationService.create_reservations(
            db_session, _make(room_id, CI + timedelta(days=2), doc="UOV-G"))
        # 1 → 3 nights would cover the other booking's night
        with pytest.raises(ValueError, match="ya reservada"):
            ReservationService.update_reservation(
                db_session, ids[0],
                _make(room_id, CI, stay_days=3, doc="UOV-F"))

    def test_moving_to_free_window_allowed(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="UOV-H"))
        ok = ReservationService.update_reservation(
            db_session, ids[0],
            _make(room_id, CI + timedelta(days=10), doc="UOV-H"))
        assert ok is True
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.check_in_date == CI + timedelta(days=10)


class TestUpdateLateCheckoutForward:
    def test_moving_onto_late_checkout_day_early_arrival_rejected(
            self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="ULC-A", late=True, lct="14:00"))
        other_room = seed_full["rooms"][1].id
        ids = ReservationService.create_reservations(
            db_session,
            _make(other_room, CI + timedelta(days=1), doc="ULC-B",
                  arrival=time(10, 0)))
        # Move ULC-B onto the room whose guest leaves late that same day
        with pytest.raises(ValueError, match="late check-out hasta las 14:00"):
            ReservationService.update_reservation(
                db_session, ids[0],
                _make(room_id, CI + timedelta(days=1), doc="ULC-B",
                      arrival=time(10, 0)))

    def test_moving_onto_late_checkout_day_late_arrival_allowed(
            self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="ULC-C", late=True, lct="14:00"))
        other_room = seed_full["rooms"][1].id
        ids = ReservationService.create_reservations(
            db_session,
            _make(other_room, CI + timedelta(days=1), doc="ULC-D",
                  arrival=time(15, 0)))
        ok = ReservationService.update_reservation(
            db_session, ids[0],
            _make(room_id, CI + timedelta(days=1), doc="ULC-D",
                  arrival=time(15, 0)))
        assert ok is True


class TestUpdateParking:
    def test_moving_parked_booking_into_full_lot_rejected(self, db_session, seed_full):
        SettingsService.set_parking_capacity(db_session, 2)
        room_a, room_b, room_c = (seed_full["rooms"][i].id for i in range(3))
        target = CI + timedelta(days=5)
        # Fill the lot on the target window
        ReservationService.create_reservations(
            db_session, _make(room_a, target, doc="UPK-A", parking=True))
        ReservationService.create_reservations(
            db_session, _make(room_b, target, doc="UPK-B", parking=True))
        # A parked booking elsewhere...
        ids = ReservationService.create_reservations(
            db_session, _make(room_c, CI, doc="UPK-C", parking=True))
        # ...moved into the full window must be rejected
        with pytest.raises(ValueError, match="Estacionamiento lleno"):
            ReservationService.update_reservation(
                db_session, ids[0], _make(room_c, target, doc="UPK-C"))

    def test_non_parked_booking_moves_freely(self, db_session, seed_full):
        SettingsService.set_parking_capacity(db_session, 2)
        room_a, room_b, room_c = (seed_full["rooms"][i].id for i in range(3))
        target = CI + timedelta(days=5)
        ReservationService.create_reservations(
            db_session, _make(room_a, target, doc="UPK-D", parking=True))
        ReservationService.create_reservations(
            db_session, _make(room_b, target, doc="UPK-E", parking=True))
        ids = ReservationService.create_reservations(
            db_session, _make(room_c, CI, doc="UPK-F", parking=False))
        ok = ReservationService.update_reservation(
            db_session, ids[0], _make(room_c, target, doc="UPK-F"))
        assert ok is True

    def test_parked_booking_resaves_own_window(self, db_session, seed_full):
        # Self-exclusion on the parking count: with capacity 1, the only
        # parked booking must be able to re-save its own dates.
        SettingsService.set_parking_capacity(db_session, 1)
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="UPK-G", parking=True))
        ok = ReservationService.update_reservation(
            db_session, ids[0], _make(room_id, CI, doc="UPK-G"))
        assert ok is True


class TestUpdateEndpoint:
    def test_put_overlap_returns_400_spanish(self, client, auth_headers_admin, seed_full):
        room_id = seed_full["rooms"][0].id
        payload = {
            "check_in_date": CI.isoformat(),
            "stay_days": 1,
            "guest_name": "API Update Overlap",
            "room_ids": [room_id],
            "price": 120000.0,
            "property_id": "los-monges",
            "client_type_id": "los-monges-particular",
        }
        r1 = client.post("/api/v1/reservations", headers=auth_headers_admin, json=payload)
        assert r1.status_code == 201, r1.text
        res_id = r1.json()[0]
        p2 = dict(payload, check_in_date=(CI + timedelta(days=5)).isoformat(),
                  guest_name="Second Guest")
        r2 = client.post("/api/v1/reservations", headers=auth_headers_admin, json=p2)
        assert r2.status_code == 201, r2.text

        upd = client.put(f"/api/v1/reservations/{res_id}",
                         headers=auth_headers_admin, json=p2)
        assert upd.status_code == 400, upd.text
        assert "ya reservada" in upd.json()["detail"]
