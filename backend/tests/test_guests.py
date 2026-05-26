"""
Service- and API-layer tests for the master Guest entity (v1.10.0 — Phase 2a).

Distinct from `test_checkin_service.py` which tests CheckInService (per-stay
registration records). The two services share a name-history but model
different concepts.
"""

from datetime import date, timedelta

import pytest

from database import Guest, Reservation
from services.guest_service import GuestService, GuestServiceError


# ----------------------------------------------------------------------
# conftest setup — Phase 2a tables (Guest, Building) need to live in the
# test DB. They're already in `database.Base.metadata`, so `db_session`
# creates them automatically. Importing the module here also makes
# pytest pick up the model on collection.
# ----------------------------------------------------------------------

@pytest.fixture
def seed_one_guest(db_session, seed_property):
    """Plant one guest for property `los-monges`."""
    g = Guest(
        property_id="los-monges",
        first_name="Juan",
        last_name="Pérez",
        document_number="1234567",
        email="juan@example.com",
        phone="+595 981 111 222",
        nationality="Paraguaya",
        country="Paraguay",
        is_active=True,
        total_stays=2,
        total_spent=300000.0,
    )
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


# ======================================================================
# CREATE
# ======================================================================
class TestCreateGuest:
    def test_minimum_fields(self, db_session, seed_property):
        g = GuestService.create_guest(
            db=db_session,
            property_id="los-monges",
            data={"first_name": "Ana", "last_name": "García"},
        )
        assert g.id is not None
        assert g.property_id == "los-monges"
        assert g.is_active is True
        assert g.source == "Direct"
        assert g.total_stays == 0

    def test_full_fields(self, db_session, seed_property):
        g = GuestService.create_guest(
            db=db_session,
            property_id="los-monges",
            data={
                "first_name": "Carlos",
                "last_name": "López",
                "document_type": "CI",
                "document_number": "9876543",
                "email": "carlos@example.com",
                "phone": "+595 21 555-1234",
                "nationality": "Argentina",
                "country": "Argentina",
                "city": "Asunción",
                "notes": "VIP — desayuno servido en la habitación.",
                "source": "Booking.com",
            },
        )
        assert g.document_number == "9876543"
        assert g.notes.startswith("VIP")
        assert g.source == "Booking.com"

    def test_blank_names_rejected(self, db_session, seed_property):
        with pytest.raises(GuestServiceError):
            GuestService.create_guest(
                db=db_session,
                property_id="los-monges",
                data={"first_name": "", "last_name": ""},
            )


# ======================================================================
# READ + LIST + COUNT
# ======================================================================
class TestReadGuest:
    def test_get_existing(self, db_session, seed_one_guest):
        got = GuestService.get_guest(db=db_session, guest_id=seed_one_guest.id)
        assert got is not None
        assert got.last_name == "Pérez"

    def test_get_missing_returns_none(self, db_session, seed_property):
        assert GuestService.get_guest(db=db_session, guest_id=99999) is None

    def test_list_paginated(self, db_session, seed_property):
        for i in range(5):
            GuestService.create_guest(
                db=db_session, property_id="los-monges",
                data={"first_name": f"G{i}", "last_name": f"L{i}"},
            )
        rows = GuestService.list_guests(db=db_session, property_id="los-monges", skip=0, limit=3)
        assert len(rows) == 3
        total = GuestService.count_guests(db=db_session, property_id="los-monges")
        assert total == 5

    def test_list_excludes_inactive(self, db_session, seed_property):
        g1 = GuestService.create_guest(db=db_session, property_id="los-monges",
                                       data={"first_name": "A", "last_name": "Active"})
        g2 = GuestService.create_guest(db=db_session, property_id="los-monges",
                                       data={"first_name": "B", "last_name": "Soft"})
        GuestService.update_guest(db=db_session, guest_id=g2.id, data={"is_active": False})
        rows = GuestService.list_guests(db=db_session, property_id="los-monges", active_only=True)
        ids = [r.id for r in rows]
        assert g1.id in ids
        assert g2.id not in ids


# ======================================================================
# UPDATE
# ======================================================================
class TestUpdateGuest:
    def test_partial_update(self, db_session, seed_one_guest):
        updated = GuestService.update_guest(
            db=db_session, guest_id=seed_one_guest.id,
            data={"phone": "+595 9999 9999", "notes": "Cliente frecuente"},
        )
        assert updated.phone == "+595 9999 9999"
        assert updated.notes == "Cliente frecuente"
        # untouched
        assert updated.last_name == "Pérez"

    def test_missing_returns_none(self, db_session, seed_property):
        assert GuestService.update_guest(db=db_session, guest_id=99999, data={"first_name": "X"}) is None

    def test_clear_field_via_empty_string(self, db_session, seed_one_guest):
        updated = GuestService.update_guest(
            db=db_session, guest_id=seed_one_guest.id, data={"email": ""},
        )
        assert updated.email is None


# ======================================================================
# SEARCH
# ======================================================================
class TestSearchGuests:
    def _seed_three(self, db_session):
        GuestService.create_guest(db=db_session, property_id="los-monges",
                                  data={"first_name": "Ana", "last_name": "Pérez", "document_number": "111"})
        GuestService.create_guest(db=db_session, property_id="los-monges",
                                  data={"first_name": "Pedro", "last_name": "García", "email": "pedro@example.com"})
        GuestService.create_guest(db=db_session, property_id="los-monges",
                                  data={"first_name": "Luis", "last_name": "Pereira", "phone": "+595 981 555 000"})

    def test_finds_by_lastname(self, db_session, seed_property):
        self._seed_three(db_session)
        results = GuestService.search_guests(db=db_session, property_id="los-monges", query="Pérez")
        assert len(results) >= 1
        assert any(r.last_name == "Pérez" for r in results)

    def test_finds_by_document(self, db_session, seed_property):
        self._seed_three(db_session)
        results = GuestService.search_guests(db=db_session, property_id="los-monges", query="111")
        assert len(results) == 1
        assert results[0].document_number == "111"

    def test_finds_by_email(self, db_session, seed_property):
        self._seed_three(db_session)
        results = GuestService.search_guests(db=db_session, property_id="los-monges", query="pedro@")
        assert len(results) == 1
        assert results[0].first_name == "Pedro"

    def test_short_query_returns_empty(self, db_session, seed_property):
        self._seed_three(db_session)
        # Length 1 → no scan
        assert GuestService.search_guests(db=db_session, property_id="los-monges", query="P") == []


# ======================================================================
# FIND OR CREATE
# ======================================================================
class TestFindOrCreate:
    def test_match_by_document(self, db_session, seed_one_guest):
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="Juan", last_name="Pérez", document_number="1234567",
        )
        assert g is not None
        assert g.id == seed_one_guest.id  # matched, not created

    def test_match_by_email(self, db_session, seed_one_guest):
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="X", last_name="Y", email="juan@example.com",
        )
        assert g.id == seed_one_guest.id

    def test_phone_no_longer_a_match_tier(self, db_session, seed_one_guest):
        """Bug #1 fix: phone is NOT a match tier (false positives across family/couples).

        Pre-fix this returned the seed guest because phone matched.
        Post-fix: a different person with no doc/email/name match is created
        as a new row even if their phone happens to match.
        """
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="Brother", last_name="Different",
            phone="+595 981 111 222",  # same digits as seed_one_guest
        )
        assert g is not None
        assert g.id != seed_one_guest.id
        assert g.first_name == "Brother"

    def test_create_when_no_match(self, db_session, seed_property):
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="Brand", last_name="New",
        )
        assert g is not None
        assert g.first_name == "Brand"
        assert g.last_name == "New"

    def test_split_lastname_firstname_format(self, db_session, seed_property):
        # "Lastname, Firstname" → split correctly
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            guest_name="González, María",
        )
        assert g is not None
        assert g.last_name == "González"
        assert g.first_name == "María"

    def test_blank_input_returns_none(self, db_session, seed_property):
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="", last_name="", guest_name="",
        )
        assert g is None


class TestFindOrCreateBugFix:
    """v1.10.0 Phase 2a Bug #1: dedup duplicates from embedded-doc names."""

    def test_extracts_embedded_doc_from_guest_name(self, db_session, seed_one_guest):
        """`'Pérez, Juan (1234567)'` should match the seeded guest by extracted doc."""
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            guest_name="Pérez, Juan (1234567)",
        )
        assert g is not None
        assert g.id == seed_one_guest.id  # matched via extracted doc, not created
        # Sanity: original guest name unchanged (snapshots don't re-write)
        assert g.last_name == "Pérez"
        assert g.first_name == "Juan"

    def test_extracts_embedded_doc_from_first_name(self, db_session, seed_one_guest):
        """The migration-bug case: doc embedded in first_name field."""
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            last_name="Pérez",
            first_name="Juan (1234567)",
        )
        assert g.id == seed_one_guest.id

    def test_normalises_whitespace_in_name(self, db_session, seed_one_guest):
        """Multiple spaces and trailing whitespace should not block name match."""
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="  Juan  ",
            last_name="Pérez ",
        )
        assert g.id == seed_one_guest.id

    def test_doc_first_match_wins_over_name(self, db_session, seed_property):
        """A guest with doc='X' + name='Foo Bar' must NOT match a doc='X' + name='Different Other'."""
        from database import Guest
        g1 = Guest(
            property_id="los-monges", first_name="Foo", last_name="Bar",
            document_number="DOC-AAA", is_active=True, total_stays=0, total_spent=0.0,
        )
        db_session.add(g1)
        db_session.commit()

        # Match by doc, even though name differs completely
        match = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="Different", last_name="Other",
            document_number="DOC-AAA",
        )
        assert match is not None
        assert match.id == g1.id

    def test_doc_provided_does_not_fallback_to_name(self, db_session, seed_one_guest):
        """If a doc is provided but doesn't match, do NOT fall back to name match.

        Prevents false positives: 'this is Juan Pérez but with NEW document' → new row.
        """
        g = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            first_name="Juan", last_name="Pérez",
            document_number="DIFFERENT-DOC",  # doesn't match seed
        )
        assert g is not None
        assert g.id != seed_one_guest.id  # NEW row created
        assert g.document_number == "DIFFERENT-DOC"

    def test_backfill_email_on_existing_guest(self, db_session, seed_property):
        """find_or_create_guest fills empty fields on existing guests, never overwrites."""
        from database import Guest
        g = Guest(
            property_id="los-monges", first_name="Ana", last_name="Soto",
            document_number="SOTO-1", email=None,  # no email yet
            is_active=True, total_stays=0, total_spent=0.0,
        )
        db_session.add(g); db_session.commit()

        match = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            document_number="SOTO-1",
            email="ana@example.com",  # this should be backfilled
            phone="+595 9999",
        )
        assert match.id == g.id
        assert match.email == "ana@example.com"
        assert match.phone == "+595 9999"

    def test_backfill_does_not_overwrite_existing(self, db_session, seed_property):
        """Existing email is not overwritten by a different one."""
        from database import Guest
        g = Guest(
            property_id="los-monges", first_name="Bea", last_name="Toro",
            document_number="TORO-1", email="original@example.com",
            is_active=True, total_stays=0, total_spent=0.0,
        )
        db_session.add(g); db_session.commit()

        match = GuestService.find_or_create_guest(
            db=db_session, property_id="los-monges",
            document_number="TORO-1",
            email="new@example.com",
        )
        assert match.id == g.id
        assert match.email == "original@example.com"  # NOT overwritten


class TestExtractEmbeddedDoc:
    """Unit tests for the helper that strips parenthetical doc numbers."""

    def test_extracts_simple_doc(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc("Acosta, Rosa (2362693)")
        assert cleaned == "Acosta, Rosa"
        assert doc == "2362693"

    def test_extracts_doc_from_first_name_field(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc("Rosa (2362693)")
        assert cleaned == "Rosa"
        assert doc == "2362693"

    def test_no_paren_returns_unchanged(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc("García López")
        assert cleaned == "García López"
        assert doc is None

    def test_paren_with_non_digits_strips_but_no_extract(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc("Pedro (alias)")
        assert cleaned == "Pedro"
        assert doc is None  # "alias" has 0 digits

    def test_paren_with_dotted_doc_extracts_digits_only(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc("María (CI 4.567.890)")
        assert cleaned == "María"
        assert doc == "4567890"

    def test_empty_string(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc("")
        assert cleaned == ""
        assert doc is None

    def test_none_input(self):
        from services.guest_service import _extract_embedded_doc
        cleaned, doc = _extract_embedded_doc(None)
        assert cleaned == ""
        assert doc is None


# ======================================================================
# HISTORY + AGGREGATES
# ======================================================================
class TestGuestHistory:
    def test_no_reservations(self, db_session, seed_one_guest):
        h = GuestService.get_guest_history(db=db_session, guest_id=seed_one_guest.id)
        assert h is not None
        assert h["total_stays"] == 0
        assert h["reservations"] == []

    def test_history_includes_reservations(self, db_session, seed_one_guest, seed_rooms, make_reservation):
        # Create a reservation linked to this guest
        r = make_reservation(guest_name="Pérez, Juan", price=200000.0, status="Confirmada")
        r.guest_id = seed_one_guest.id
        db_session.commit()

        h = GuestService.get_guest_history(db=db_session, guest_id=seed_one_guest.id)
        assert h["total_stays"] == 1
        assert h["total_spent"] == 200000.0
        assert len(h["reservations"]) == 1

    def test_cancelled_excluded_from_aggregates(self, db_session, seed_one_guest, seed_rooms, make_reservation):
        r1 = make_reservation(price=100000.0, status="Confirmada")
        r1.guest_id = seed_one_guest.id
        r2 = make_reservation(price=999999.0, status="Cancelada")
        r2.guest_id = seed_one_guest.id
        db_session.commit()

        h = GuestService.get_guest_history(db=db_session, guest_id=seed_one_guest.id)
        assert h["total_stays"] == 1  # only Confirmada counted
        assert h["total_spent"] == 100000.0


# ======================================================================
# RESERVATION INTEGRATION (find_or_create_guest wired into create flow)
# ======================================================================
class TestReservationCreatesGuest:
    def test_new_reservation_creates_guest(self, db_session, seed_full):
        from services import ReservationService
        from schemas import ReservationCreate

        room_id = seed_full["rooms"][0].id
        data = ReservationCreate(
            check_in_date=date.today() + timedelta(days=5),
            stay_days=2,
            guest_name="Apellido, Nombre",
            guest_first_name="Nombre",
            guest_last_name="Apellido",
            room_ids=[room_id],
            price=150000.0,
            property_id="los-monges",
            client_type_id="los-monges-particular",
        )
        ids = ReservationService.create_reservations(db_session, data)
        assert len(ids) == 1
        # Verify guest was created and linked
        r = db_session.query(Reservation).filter(Reservation.id == ids[0]).first()
        assert r.guest_id is not None
        g = db_session.query(Guest).filter(Guest.id == r.guest_id).first()
        assert g is not None
        assert g.first_name == "Nombre"
        assert g.last_name == "Apellido"

    def test_repeat_guest_links_existing(self, db_session, seed_full):
        from services import ReservationService
        from schemas import ReservationCreate

        room_id = seed_full["rooms"][0].id
        # Two reservations for the same person (matched by document).
        # Use distinct date ranges so the room-overlap guard doesn't reject
        # the second booking — this test asserts guest dedup, not room
        # availability behaviour.
        for offset in (10, 20):
            data = ReservationCreate(
                check_in_date=date.today() + timedelta(days=offset),
                stay_days=1,
                guest_name="Test, Repeat",
                guest_first_name="Repeat",
                guest_last_name="Test",
                document_number="REPEAT-DOC-001",
                room_ids=[room_id],
                price=120000.0,
                property_id="los-monges",
                client_type_id="los-monges-particular",
            )
            ReservationService.create_reservations(db_session, data)

        # Only ONE Guest created, both reservations point to it
        guests = db_session.query(Guest).filter(Guest.document_number == "REPEAT-DOC-001").all()
        assert len(guests) == 1
        reservations = db_session.query(Reservation).filter(
            Reservation.guest_id == guests[0].id
        ).all()
        assert len(reservations) == 2


# ======================================================================
# API LAYER (mobile/Next.js path)
# ======================================================================
class TestGuestEndpoints:
    def test_search_unauthenticated(self, client, seed_property):
        r = client.get("/api/v1/huespedes/search?q=Per")
        assert r.status_code in (401, 403)

    def test_create_and_get(self, client, auth_headers_admin, seed_property):
        r = client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "API", "last_name": "Tester"},
        )
        assert r.status_code == 200, r.text
        guest_id = r.json()["id"]

        r2 = client.get(f"/api/v1/huespedes/{guest_id}", headers=auth_headers_admin)
        assert r2.status_code == 200
        assert r2.json()["last_name"] == "Tester"

    def test_get_history_404(self, client, auth_headers_admin, seed_property):
        r = client.get("/api/v1/huespedes/99999/history", headers=auth_headers_admin)
        assert r.status_code == 404

    def test_search_returns_results(self, client, auth_headers_admin, seed_property):
        client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "Searchable", "last_name": "Person", "document_number": "SEARCH-001"},
        )
        r = client.get("/api/v1/huespedes/search?q=Searchable", headers=auth_headers_admin)
        assert r.status_code == 200
        assert any(item["last_name"] == "Person" for item in r.json())

    def test_search_min_length_validation(self, client, auth_headers_admin, seed_property):
        # query with single char fails validation (Field min_length=2)
        r = client.get("/api/v1/huespedes/search?q=A", headers=auth_headers_admin)
        assert r.status_code == 422
