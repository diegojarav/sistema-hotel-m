"""
Phase 2 — Service-layer tests for GuestService (PC/Streamlit path).
"""

from datetime import date, timedelta
from services.guest_service import GuestService
from schemas import CheckInCreate
from database import CheckIn


class TestRegisterCheckin:
    def test_creates_new(self, db_session, seed_rooms):
        data = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="García",
            first_name="Juan",
            document_number="1234567",
            nationality="Paraguaya",
        )
        cid = GuestService.register_checkin(db_session, data)
        assert cid is not None
        assert isinstance(cid, int)

    def test_duplicate_updates(self, db_session, seed_rooms):
        data1 = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="García",
            first_name="Juan",
            document_number="1234567",
        )
        id1 = GuestService.register_checkin(db_session, data1)

        data2 = CheckInCreate(
            room_id=seed_rooms["rooms"][1].id,
            last_name="García Updated",
            first_name="Juan",
            document_number="1234567",
        )
        id2 = GuestService.register_checkin(db_session, data2)
        assert id1 == id2  # Same record updated

        checkin = db_session.query(CheckIn).filter(CheckIn.id == id1).first()
        assert checkin.last_name == "García Updated"

    def test_fields_stored(self, db_session, seed_rooms):
        data = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="López",
            first_name="María",
            document_number="9876543",
            nationality="Argentina",
            country="Argentina",
            billing_name="Corp SA",
            billing_ruc="80012345-6",
        )
        cid = GuestService.register_checkin(db_session, data)
        ci = db_session.query(CheckIn).filter(CheckIn.id == cid).first()
        assert ci.last_name == "López"
        assert ci.nationality == "Argentina"
        assert ci.billing_name == "Corp SA"


class TestGetCheckin:
    def test_found(self, db_session, seed_rooms):
        data = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="Test",
            document_number="111111",
        )
        cid = GuestService.register_checkin(db_session, data)
        result = GuestService.get_checkin(db_session, cid)
        assert result is not None
        assert result.last_name == "Test"

    def test_not_found(self, db_session):
        result = GuestService.get_checkin(db_session, 99999)
        assert result is None


class TestUpdateCheckin:
    def test_success(self, db_session, seed_rooms):
        data = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="Original",
            document_number="222222",
        )
        cid = GuestService.register_checkin(db_session, data)

        updated_data = CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="Updated",
            document_number="222222",
        )
        result = GuestService.update_checkin(db_session, cid, updated_data)
        assert result is True

        ci = db_session.query(CheckIn).filter(CheckIn.id == cid).first()
        assert ci.last_name == "Updated"

    def test_not_found(self, db_session):
        data = CheckInCreate(last_name="X", document_number="000")
        result = GuestService.update_checkin(db_session, 99999, data)
        assert result is False


class TestSearchCheckins:
    def test_finds_by_name(self, db_session, seed_rooms):
        GuestService.register_checkin(db_session, CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="Fernández",
            first_name="Carlos",
            document_number="333333",
        ))
        results = GuestService.search_checkins(db_session, "Fernández")
        assert len(results) >= 1
        assert results[0]["last_name"] == "Fernández"


class TestGuestNames:
    def test_returns_sorted(self, db_session, seed_rooms):
        GuestService.register_checkin(db_session, CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="Zelaya", first_name="Ana", document_number="A1",
        ))
        GuestService.register_checkin(db_session, CheckInCreate(
            room_id=seed_rooms["rooms"][1].id,
            last_name="Acuña", first_name="Pedro", document_number="A2",
        ))
        names = GuestService.get_all_guest_names(db_session)
        assert len(names) >= 2
        assert names[0].startswith("Acuña")


class TestBillingProfiles:
    def test_returns_unique(self, db_session, seed_rooms):
        GuestService.register_checkin(db_session, CheckInCreate(
            room_id=seed_rooms["rooms"][0].id,
            last_name="X", document_number="B1",
            billing_name="Empresa SA", billing_ruc="12345-6",
        ))
        profiles = GuestService.get_all_billing_profiles(db_session)
        assert len(profiles) >= 1
        assert profiles[0]["name"] == "Empresa SA"


class TestUnlinkedReservations:
    def test_returns_unlinked(self, db_session, seed_rooms, make_reservation):
        res = make_reservation(guest_name="Unlinked Guest")
        unlinked = GuestService.get_unlinked_reservations(db_session)
        ids = [u["id"] for u in unlinked]
        assert res.id in ids

    def test_excludes_linked(self, db_session, seed_rooms, make_reservation):
        res = make_reservation(guest_name="Linked Guest")
        # Create a checkin linked to this reservation
        ci = CheckIn(
            room_id=seed_rooms["rooms"][0].id,
            reservation_id=res.id,
            created_at=date.today(),
            last_name="Linked",
            document_number="LNK001",
        )
        db_session.add(ci)
        db_session.commit()

        unlinked = GuestService.get_unlinked_reservations(db_session)
        ids = [u["id"] for u in unlinked]
        assert res.id not in ids
