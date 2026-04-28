"""
End-to-end flow tests for the guest data flows (v1.10.0 — Phase 2a Bug #2).
============================================================================

Each test exercises one of the canonical paths from the architectural review:

  Flow A: PC/mobile reservation form → guest_id explicit → ReservationService
  Flow B: Auto-CheckIn during reservation creation sets checkin.guest_id
  Flow C: update_checkin propagates new fields to master Guest (fill empty)
  Flow D: Duplicate-suspect detection in the manual-create form
  Flow E: Ficha pre-fill from master Guest

Plus edge cases:
  - Embedded doc number in name
  - Special characters in name (José María, O'Brien)
  - Guest with no data except name
  - OTA guest without document
  - Repeat guest across multiple reservations (same guest_id reused)
  - Reservation without guest_id falls back to find_or_create
"""

from datetime import date, timedelta

import pytest

from database import CheckIn, Guest, Reservation
from schemas import CheckInCreate, ReservationCreate
from services import CheckInService, GuestService, ReservationService


# ======================================================================
# FLOW A — Explicit guest_id on reservation creation
# ======================================================================
class TestFlowA_ExplicitGuestId:
    def test_dropdown_creates_reservation_with_guest_id(self, db_session, seed_full):
        """When guest_id is provided, the reservation links it directly."""
        # Seed a master guest the recepcionist would pick from the dropdown
        existing = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Picked", "last_name": "Guest", "phone": "+595 999"},
        )
        room_id = seed_full["rooms"][0].id

        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=3),
            stay_days=2,
            guest_name="Guest, Picked",  # snapshot — what the user typed/saw
            room_ids=[room_id],
            price=200000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            guest_id=existing.id,
        )
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.guest_id == existing.id

        # No NEW guest was created — explicit pick skips find_or_create
        guests_named_picked = (
            db_session.query(Guest)
            .filter(Guest.first_name == "Picked", Guest.last_name == "Guest")
            .all()
        )
        assert len(guests_named_picked) == 1

    def test_explicit_guest_id_for_wrong_property_falls_back(
        self, db_session, seed_full
    ):
        """If guest_id belongs to a different property, fallback to find_or_create."""
        # Seed guest in a non-matching property (simulate stale dropdown id)
        from database import Property
        other = Property(id="other-hotel", name="Other Hotel", slug="other-hotel")
        db_session.add(other); db_session.commit()
        wrong = GuestService.create_guest(
            db=db_session, property_id="other-hotel",
            data={"first_name": "Wrong", "last_name": "Property"},
        )

        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=4),
            stay_days=1,
            guest_name="Fallback, Person",
            guest_first_name="Person",
            guest_last_name="Fallback",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            guest_id=wrong.id,  # mismatched property
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        # Service silently fell back and created a new guest under los-monges
        assert r.guest_id is not None
        new_guest = db_session.query(Guest).filter(Guest.id == r.guest_id).first()
        assert new_guest.property_id == "los-monges"
        assert new_guest.last_name == "Fallback"

    def test_explicit_guest_id_for_inactive_guest_falls_back(
        self, db_session, seed_full
    ):
        """Inactive (soft-deleted) guests should not satisfy the explicit pick."""
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Soft", "last_name": "Deleted"},
        )
        GuestService.update_guest(db=db_session, guest_id=g.id, data={"is_active": False})

        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=5),
            stay_days=1,
            guest_name="New Person",
            guest_first_name="New",
            guest_last_name="Person",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            guest_id=g.id,
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        # Fallback created a fresh active guest
        assert r.guest_id != g.id
        new_guest = db_session.query(Guest).filter(Guest.id == r.guest_id).first()
        assert new_guest.is_active

    def test_explicit_guest_id_augments_master_with_form_data(
        self, db_session, seed_full
    ):
        """Form fields (e.g. new email) should backfill the picked guest."""
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Backfill", "last_name": "Me"},
        )
        assert g.email is None

        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=2),
            stay_days=1,
            guest_name="Me, Backfill",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            contact_email="backfill@example.com",
            guest_id=g.id,
        )
        ReservationService.create_reservations(db_session, data)
        db_session.refresh(g)
        assert g.email == "backfill@example.com"

    def test_no_guest_id_falls_back_to_find_or_create(self, db_session, seed_full):
        """The legacy path (no explicit guest_id) still works for OTA imports."""
        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=3),
            stay_days=2,
            guest_name="Legacy, Path",
            guest_first_name="Path",
            guest_last_name="Legacy",
            room_ids=[room_id],
            price=180000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.guest_id is not None
        g = db_session.query(Guest).filter(Guest.id == r.guest_id).first()
        assert g.last_name == "Legacy"


# ======================================================================
# FLOW B — Auto-CheckIn during reservation creation links guest_id
# ======================================================================
class TestFlowB_AutoCheckinGuestId:
    def test_auto_checkin_inherits_guest_id(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=4),
            stay_days=1,
            guest_name="Doc, Scanned",
            guest_first_name="Scanned",
            guest_last_name="Doc",
            document_number="AUTO-LINK-001",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        ci = (
            db_session.query(CheckIn)
            .filter(CheckIn.document_number == "AUTO-LINK-001")
            .first()
        )
        assert ci is not None
        assert ci.guest_id is not None
        assert ci.guest_id == r.guest_id

    def test_existing_checkin_gets_guest_id_when_relinked(self, db_session, seed_full):
        """A pre-existing checkin without guest_id is back-filled when its
        document is reused on a new reservation."""
        room_id = seed_full["rooms"][0].id

        # Plant a checkin without guest_id (legacy data)
        ci = CheckIn(
            created_at=date.today(),
            room_id=room_id,
            last_name="Pre",
            first_name="Existing",
            document_number="EXIST-DOC-1",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()
        assert ci.guest_id is None

        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=5),
            stay_days=1,
            guest_name="Existing, Pre",
            guest_first_name="Existing",
            guest_last_name="Pre",
            document_number="EXIST-DOC-1",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
        )
        ReservationService.create_reservations(db_session, data)
        db_session.refresh(ci)
        assert ci.guest_id is not None  # back-filled


# ======================================================================
# FLOW C — update_checkin propagates new fields to Guest (fill empty)
# ======================================================================
class TestFlowC_UpdateCheckinAugmentsGuest:
    def test_fills_empty_guest_phone(self, db_session, seed_full):
        # Plant guest with no phone
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "NoPhone", "last_name": "Yet", "document_number": "DOC-NP"},
        )
        # Plant checkin linked to the guest
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=g.id,
            last_name="Yet",
            first_name="NoPhone",
            document_number="DOC-NP",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()

        # User edits the ficha and adds a phone
        update = CheckInCreate(
            room_id=seed_full["rooms"][0].id,
            last_name="Yet",
            first_name="NoPhone",
            document_number="DOC-NP",
            contact_phone="+595 9 1111 1111",
        )
        ok = CheckInService.update_checkin(db_session, ci.id, update)
        assert ok is True
        db_session.refresh(g)
        assert g.phone == "+595 9 1111 1111"

    def test_does_not_overwrite_existing_phone(self, db_session, seed_full):
        # Guest already has a phone
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={
                "first_name": "Has",
                "last_name": "Phone",
                "document_number": "DOC-HP",
                "phone": "+595 ORIGINAL",
            },
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=g.id,
            last_name="Phone",
            first_name="Has",
            document_number="DOC-HP",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()

        update = CheckInCreate(
            room_id=seed_full["rooms"][0].id,
            last_name="Phone",
            first_name="Has",
            document_number="DOC-HP",
            contact_phone="+595 NEW NUMBER",
        )
        CheckInService.update_checkin(db_session, ci.id, update)
        db_session.refresh(g)
        assert g.phone == "+595 ORIGINAL"  # NOT overwritten

    def test_register_checkin_existing_doc_augments_guest(self, db_session, seed_full):
        """register_checkin's duplicate-doc branch also propagates."""
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Dup", "last_name": "Doc", "document_number": "DUPDOC-1"},
        )
        ci = CheckIn(
            created_at=date.today(),
            room_id=seed_full["rooms"][0].id,
            guest_id=g.id,
            last_name="Doc",
            first_name="Dup",
            document_number="DUPDOC-1",
            digital_signature="Pendiente",
        )
        db_session.add(ci); db_session.commit()

        # Re-register with same doc + new email
        again = CheckInCreate(
            room_id=seed_full["rooms"][0].id,
            last_name="Doc",
            first_name="Dup",
            document_number="DUPDOC-1",
            contact_email="dup.doc@example.com",
        )
        CheckInService.register_checkin(db_session, again)
        db_session.refresh(g)
        assert g.email == "dup.doc@example.com"


# ======================================================================
# FLOW D — Duplicate suspect detection (service-level)
# ======================================================================
class TestFlowD_DuplicateSuspectSearch:
    """The PC UI builds the suspect list by querying /huespedes/search.
    These tests verify the underlying search returns appropriate candidates."""

    def test_search_finds_same_lastname(self, db_session, seed_property):
        GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Marcos A.", "last_name": "Barrios", "document_number": "B-1"},
        )
        GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Marcos B.", "last_name": "Barrios", "document_number": "B-2"},
        )
        results = GuestService.search_guests(
            db=db_session, property_id="los-monges", query="Barrios",
        )
        assert len(results) >= 2

    def test_search_finds_by_doc(self, db_session, seed_property):
        GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Find", "last_name": "Me", "document_number": "FINDDOC1"},
        )
        results = GuestService.search_guests(
            db=db_session, property_id="los-monges", query="FINDDOC1",
        )
        assert len(results) == 1


# ======================================================================
# FLOW E — Ficha pre-fill via Guest master search
# ======================================================================
class TestFlowE_FichaPrefillFromMaster:
    """The PC UI uses GuestService.search_guests + manual prefill in a
    session_state key. Test the search returns the data the UI would use."""

    def test_search_returns_phone_email_for_prefill(self, db_session, seed_property):
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={
                "first_name": "Ana",
                "last_name": "Returning",
                "document_number": "RET-1",
                "phone": "+595 9 9999",
                "email": "ana@example.com",
            },
        )
        results = GuestService.search_guests(
            db=db_session, property_id="los-monges", query="Returning",
        )
        assert len(results) == 1
        hit = results[0]
        # All the fields the ficha pre-fill needs
        assert hit.id == g.id
        assert hit.phone == "+595 9 9999"
        assert hit.email == "ana@example.com"
        assert hit.document_number == "RET-1"


# ======================================================================
# Edge cases
# ======================================================================
class TestEdgeCases:
    def test_guest_name_with_embedded_doc(self, db_session, seed_full):
        """Reservation form text 'Acosta, Rosa (12345)' should NOT create dup."""
        # Seed clean guest
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Rosa", "last_name": "Acosta", "document_number": "ED-001"},
        )
        room_id = seed_full["rooms"][0].id

        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=2),
            stay_days=1,
            guest_name="Acosta, Rosa (ED-001)",  # legacy embedded doc
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.guest_id == g.id  # matched, no new row

    def test_special_characters_in_name(self, db_session, seed_full):
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "José María", "last_name": "O'Brien Martínez"},
        )
        # Find again by exact name
        found = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="José María", last_name="O'Brien Martínez",
        )
        assert found.id == g.id

    def test_minimal_guest_no_data_except_name(self, db_session, seed_property):
        g = GuestService.create_guest(
            db=db_session, property_id="los-monges",
            data={"first_name": "Pedro", "last_name": "Desconocido"},
        )
        assert g.id is not None
        assert g.email is None
        assert g.phone is None
        assert g.document_number is None

    def test_ota_guest_no_document(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=10),
            stay_days=3,
            guest_name="Hans Müller",
            guest_first_name="Hans",
            guest_last_name="Müller",
            contact_email="hans@example.com",
            room_ids=[room_id],
            price=300000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
            source="Booking.com",
        )
        ids = ReservationService.create_reservations(db_session, data)
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        g = db_session.query(Guest).filter(Guest.id == r.guest_id).first()
        assert g.last_name == "Müller"
        assert g.document_number is None
        assert g.email == "hans@example.com"

    def test_repeat_guest_three_reservations_same_id(self, db_session, seed_full):
        """3 bookings with same doc → 1 Guest, 3 Reservations all linked."""
        room_id = seed_full["rooms"][0].id
        for i in range(3):
            data = ReservationCreate(
                check_in_date=date.today() + timedelta(days=10 + i * 5),
                stay_days=1,
                guest_name="Repeat, Visitor",
                guest_first_name="Visitor",
                guest_last_name="Repeat",
                document_number="REPEAT-DOC",
                room_ids=[room_id],
                price=150000.0,
                property_id="los-monges",
                client_type_id="los-monges-particular",
            )
            ReservationService.create_reservations(db_session, data)

        # 1 guest
        guests = db_session.query(Guest).filter(Guest.document_number == "REPEAT-DOC").all()
        assert len(guests) == 1
        # 3 reservations, all linked
        reservations = (
            db_session.query(Reservation)
            .filter(Reservation.guest_id == guests[0].id)
            .all()
        )
        assert len(reservations) == 3


# ======================================================================
# API LAYER — Dropdown endpoint
# ======================================================================
class TestDropdownEndpoint:
    def test_dropdown_unauthenticated(self, client, seed_property):
        r = client.get("/api/v1/huespedes/dropdown")
        assert r.status_code in (401, 403)

    def test_dropdown_returns_clean_labels(
        self, client, auth_headers_admin, seed_property
    ):
        # Seed two guests via service
        client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "Clean", "last_name": "Label", "document_number": "CL-1"},
        )
        client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "Other", "last_name": "Person"},
        )
        r = client.get("/api/v1/huespedes/dropdown", headers=auth_headers_admin)
        assert r.status_code == 200
        items = r.json()
        # Find our seeded ones
        labels = [i["label"] for i in items]
        assert any("Label, Clean — Doc CL-1" in lab for lab in labels)
        assert any("Person, Other" in lab for lab in labels)
        # No embedded parens (the bug we fixed)
        assert all("(" not in lab for lab in labels)
