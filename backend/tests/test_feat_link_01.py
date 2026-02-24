"""
Phase 2 — Integration tests for FEAT-LINK-01 (Smart Reservation ↔ Check-in Linking).

Tests the full flow: creating a reservation with document_number auto-creates
a CheckIn, prevents duplicates, and supports manual linking.
"""

from datetime import date, timedelta
from services.reservation_service import ReservationService
from services.guest_service import GuestService
from schemas import ReservationCreate, CheckInCreate
from database import CheckIn, Reservation


def _make_res_data(room_id, doc_number="", **kwargs):
    """Build a valid ReservationCreate with optional doc_number."""
    defaults = {
        "check_in_date": date.today() + timedelta(days=10),
        "stay_days": 2,
        "guest_name": "Test, Guest",
        "room_ids": [room_id],
        "price": 150000,
        "property_id": "los-monges",
        "document_number": doc_number,
        "guest_last_name": "Test",
        "guest_first_name": "Guest",
        "nationality": "Paraguaya",
        "country": "Paraguay",
    }
    defaults.update(kwargs)
    return ReservationCreate(**defaults)


class TestAutoCreateCheckin:
    def test_reservation_with_doc_creates_checkin(self, db_session, seed_rooms):
        """When document_number is provided, CheckIn is auto-created."""
        data = _make_res_data(seed_rooms["rooms"][0].id, doc_number="AUTO001")
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1

        ci = db_session.query(CheckIn).filter(
            CheckIn.document_number == "AUTO001"
        ).first()
        assert ci is not None
        assert ci.last_name == "Test"
        assert ci.reservation_id == ids[0]

    def test_reservation_without_doc_no_checkin(self, db_session, seed_rooms):
        """When document_number is empty, no CheckIn is created."""
        data = _make_res_data(seed_rooms["rooms"][0].id, doc_number="")
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1

        count = db_session.query(CheckIn).count()
        assert count == 0


class TestDuplicatePrevention:
    def test_second_reservation_same_doc_no_duplicate(self, db_session, seed_rooms):
        """Two reservations with same doc_number: only ONE CheckIn exists."""
        data1 = _make_res_data(seed_rooms["rooms"][0].id, doc_number="DUP001")
        ReservationService.create_reservations(db_session, data1)

        data2 = _make_res_data(
            seed_rooms["rooms"][1].id, doc_number="DUP001",
            check_in_date=date.today() + timedelta(days=20),
        )
        ReservationService.create_reservations(db_session, data2)

        checkins = db_session.query(CheckIn).filter(
            CheckIn.document_number == "DUP001"
        ).all()
        assert len(checkins) == 1  # Only one, not two


class TestManualLinking:
    def test_manual_link_via_reservation_id(self, db_session, seed_rooms, make_reservation):
        """A CheckIn can be manually linked to a reservation."""
        res = make_reservation(guest_name="Manual Link")

        ci_data = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            reservation_id=res.id,
            last_name="Manual",
            first_name="Link",
            document_number="MAN001",
        )
        cid = GuestService.register_checkin(db_session, ci_data)

        ci = db_session.query(CheckIn).filter(CheckIn.id == cid).first()
        assert ci.reservation_id == res.id

    def test_unlinked_list_excludes_linked(self, db_session, seed_rooms, make_reservation):
        """After linking, reservation disappears from unlinked list."""
        res = make_reservation(guest_name="To Be Linked")

        # Before linking
        unlinked = GuestService.get_unlinked_reservations(db_session)
        assert any(u["id"] == res.id for u in unlinked)

        # Link it
        ci = CheckIn(
            room_id=seed_rooms["rooms"][0].id,
            reservation_id=res.id,
            created_at=date.today(),
            last_name="Linked",
            document_number="LNK999",
        )
        db_session.add(ci)
        db_session.commit()

        # After linking
        unlinked = GuestService.get_unlinked_reservations(db_session)
        assert not any(u["id"] == res.id for u in unlinked)
