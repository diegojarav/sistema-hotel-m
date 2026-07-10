"""
Phase 6.5 — Late-checkout availability blocking.

A reservation with late check-out occupies its room INTO the checkout day
until `late_checkout_time`. The availability guard must:
  • Forward: reject a same-day arrival earlier than late_checkout_time +
    cleaning buffer (property-configurable, default 30 min).
  • Reverse: reject GRANTING a late check-out (on create or update) that
    collides with an arrival already booked for the checkout day.

Also regression-covers the update arrival_time crash: `update_reservation`
called `.time()` on a field that is already a `time` → AttributeError on
every update carrying an arrival time.
"""
from datetime import date, time, timedelta

import pytest

from database import Property, Reservation
from schemas import ReservationCreate
from services import ReservationService
from services.hotel_day import earliest_next_arrival

CI = date.today() + timedelta(days=30)  # hotel-day validator: future only
DAY_AFTER = CI + timedelta(days=1)


def _make(room_id, check_in, *, stay_days=1, doc="X", arrival=None,
          late=False, lct=None):
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
    )


class TestEarliestNextArrival:
    """Pure helper: late_checkout_time + buffer, capped at 23:59."""

    def test_normal_addition(self):
        assert earliest_next_arrival("14:00", 30) == time(14, 30)

    def test_zero_buffer(self):
        assert earliest_next_arrival("14:00", 0) == time(14, 0)

    def test_negative_buffer_clamped(self):
        assert earliest_next_arrival("14:00", -15) == time(14, 0)

    def test_midnight_overflow_capped(self):
        assert earliest_next_arrival("23:45", 30) == time(23, 59)

    def test_accepts_time_object(self):
        assert earliest_next_arrival(time(12, 0), 45) == time(12, 45)


class TestForwardBlocking:
    """Existing late check-out blocks a too-early same-day arrival."""

    def _book_late_checkout(self, db, room_id, doc="LCO-A"):
        return ReservationService.create_reservations(
            db, _make(room_id, CI, doc=doc, late=True, lct="14:00"))

    def test_blocks_arrival_without_time(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        self._book_late_checkout(db_session, room_id)
        with pytest.raises(ValueError, match="late check-out hasta las 14:00"):
            ReservationService.create_reservations(
                db_session, _make(room_id, DAY_AFTER, doc="LCO-B"))

    def test_blocks_arrival_before_buffer(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        self._book_late_checkout(db_session, room_id)
        with pytest.raises(ValueError, match="a partir de las 14:30"):
            ReservationService.create_reservations(
                db_session,
                _make(room_id, DAY_AFTER, doc="LCO-C", arrival=time(14, 0)))

    def test_allows_arrival_at_buffer_boundary(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        self._book_late_checkout(db_session, room_id)
        ids = ReservationService.create_reservations(
            db_session,
            _make(room_id, DAY_AFTER, doc="LCO-D", arrival=time(14, 30)))
        assert len(ids) == 1

    def test_plain_adjacency_still_allowed(self, db_session, seed_full):
        # No late check-out → back-to-back stays keep working (marathon
        # regression test_adjacent_dates_allowed must not regress)
        room_id = seed_full["rooms"][0].id
        ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="LCO-E"))
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, DAY_AFTER, doc="LCO-F"))
        assert len(ids) == 1

    def test_cancelled_late_checkout_does_not_block(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = self._book_late_checkout(db_session, room_id, doc="LCO-G")
        ReservationService.cancel_reservation(
            db_session, ids[0], "test cleanup", "admin")
        ids2 = ReservationService.create_reservations(
            db_session, _make(room_id, DAY_AFTER, doc="LCO-H"))
        assert len(ids2) == 1

    def test_respects_property_buffer_config(self, db_session, seed_full):
        prop = db_session.query(Property).filter(
            Property.id == "los-monges").first()
        prop.cleaning_buffer_minutes = 60
        db_session.commit()
        room_id = seed_full["rooms"][0].id
        self._book_late_checkout(db_session, room_id, doc="LCO-I")
        # 14:30 would pass with the default 30 — must fail with buffer=60
        with pytest.raises(ValueError, match="a partir de las 15:00"):
            ReservationService.create_reservations(
                db_session,
                _make(room_id, DAY_AFTER, doc="LCO-J", arrival=time(14, 30)))
        ids = ReservationService.create_reservations(
            db_session,
            _make(room_id, DAY_AFTER, doc="LCO-K", arrival=time(15, 0)))
        assert len(ids) == 1


class TestReverseBlocking:
    """Granting late check-out must not collide with a booked arrival."""

    def test_create_blocked_by_next_day_early_arrival(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ReservationService.create_reservations(
            db_session,
            _make(room_id, DAY_AFTER, doc="REV-A", arrival=time(11, 0)))
        with pytest.raises(ValueError, match="choca con la reserva"):
            ReservationService.create_reservations(
                db_session, _make(room_id, CI, doc="REV-B", late=True, lct="14:00"))

    def test_create_blocked_by_next_day_unknown_arrival(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ReservationService.create_reservations(
            db_session, _make(room_id, DAY_AFTER, doc="REV-C"))
        with pytest.raises(ValueError, match="sin hora definida"):
            ReservationService.create_reservations(
                db_session, _make(room_id, CI, doc="REV-D", late=True, lct="14:00"))

    def test_create_allowed_when_next_arrival_late_enough(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ReservationService.create_reservations(
            db_session,
            _make(room_id, DAY_AFTER, doc="REV-E", arrival=time(15, 0)))
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="REV-F", late=True, lct="14:00"))
        assert len(ids) == 1


class TestUpdateGuard:
    """Granting late check-out via edit — THE desk workflow — is guarded."""

    def test_update_blocked_by_next_day_arrival(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="UPD-A"))
        ReservationService.create_reservations(
            db_session,
            _make(room_id, DAY_AFTER, doc="UPD-B", arrival=time(11, 0)))
        with pytest.raises(ValueError, match="choca con la reserva"):
            ReservationService.update_reservation(
                db_session, ids[0],
                _make(room_id, CI, doc="UPD-A", late=True, lct="14:00"))

    def test_update_allowed_when_no_collision(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="UPD-C"))
        ReservationService.create_reservations(
            db_session,
            _make(room_id, DAY_AFTER, doc="UPD-D", arrival=time(16, 0)))
        ok = ReservationService.update_reservation(
            db_session, ids[0],
            _make(room_id, CI, doc="UPD-C", late=True, lct="14:00"))
        assert ok is True
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.late_checkout is True
        assert r.late_checkout_time == "14:00"

    def test_update_with_arrival_time_does_not_crash(self, db_session, seed_full):
        # Regression: update_reservation called .time() on a `time` →
        # AttributeError on EVERY update carrying an arrival time.
        room_id = seed_full["rooms"][0].id
        ids = ReservationService.create_reservations(
            db_session, _make(room_id, CI, doc="UPD-E"))
        ok = ReservationService.update_reservation(
            db_session, ids[0],
            _make(room_id, CI, doc="UPD-E", arrival=time(15, 30)))
        assert ok is True
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.arrival_time == time(15, 30)


class TestUpdateEndpoint:
    """PUT surfaces the guard as 400 + Spanish detail (not a 500)."""

    def _payload(self, room_id, check_in, **extra):
        base = {
            "check_in_date": check_in.isoformat(),
            "stay_days": 1,
            "guest_name": "API Late Checkout",
            "room_ids": [room_id],
            "price": 120000.0,
            "property_id": "los-monges",
            "client_type_id": "los-monges-particular",
        }
        base.update(extra)
        return base

    def test_put_collision_returns_400_spanish(
            self, client, auth_headers_admin, seed_full):
        room_id = seed_full["rooms"][0].id
        r1 = client.post("/api/v1/reservations", headers=auth_headers_admin,
                         json=self._payload(room_id, CI))
        assert r1.status_code == 201, r1.text
        res_id = r1.json()[0]
        r2 = client.post("/api/v1/reservations", headers=auth_headers_admin,
                         json=self._payload(
                             room_id, DAY_AFTER, arrival_time="11:00",
                             guest_name="Next Guest"))
        assert r2.status_code == 201, r2.text

        upd = client.put(f"/api/v1/reservations/{res_id}",
                         headers=auth_headers_admin,
                         json=self._payload(
                             room_id, CI, late_checkout=True,
                             late_checkout_time="14:00"))
        assert upd.status_code == 400, upd.text
        assert "choca" in upd.json()["detail"]
