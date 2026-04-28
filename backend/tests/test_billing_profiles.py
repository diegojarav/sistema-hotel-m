"""
Service- and API-layer tests for BillingProfile (v1.10.0 — Phase 2a-ext).
"""
from datetime import date

import pytest

from database import BillingProfile, CheckIn, Guest
from schemas import CheckInCreate
from services import BillingProfileError, BillingProfileService, CheckInService, GuestService


@pytest.fixture
def seed_one_guest_for_billing(db_session, seed_property):
    g = GuestService.create_guest(
        db=db_session, property_id="los-monges",
        data={"first_name": "Bill", "last_name": "Test"},
    )
    return g


# ======================================================================
# CRUD
# ======================================================================
class TestCreateProfile:
    def test_minimum_fields(self, db_session, seed_one_guest_for_billing):
        prof = BillingProfileService.create_profile(
            db=db_session, guest_id=seed_one_guest_for_billing.id,
            property_id="los-monges",
            data={"label": "Personal"},
        )
        assert prof.id is not None
        assert prof.guest_id == seed_one_guest_for_billing.id
        assert prof.is_default is False
        assert prof.is_active is True

    def test_full_fields(self, db_session, seed_one_guest_for_billing):
        prof = BillingProfileService.create_profile(
            db=db_session, guest_id=seed_one_guest_for_billing.id,
            property_id="los-monges",
            data={
                "label": "Empresa XYZ",
                "is_default": True,
                "tax_id_type": "RUC",
                "tax_id_number": "80012345-6",
                "business_name": "Empresa XYZ S.A.",
                "address": "Av. España 1234",
                "city": "Asunción",
                "country": "Paraguay",
            },
        )
        assert prof.tax_id_type == "RUC"
        assert prof.business_name == "Empresa XYZ S.A."
        assert prof.is_default is True

    def test_create_for_unknown_guest_rejected(self, db_session, seed_property):
        with pytest.raises(BillingProfileError):
            BillingProfileService.create_profile(
                db=db_session, guest_id=99999, property_id="los-monges",
                data={"label": "Nope"},
            )

    def test_create_property_mismatch_rejected(self, db_session, seed_one_guest_for_billing):
        with pytest.raises(BillingProfileError):
            BillingProfileService.create_profile(
                db=db_session, guest_id=seed_one_guest_for_billing.id,
                property_id="other-hotel",
                data={"label": "Wrong"},
            )


class TestListProfiles:
    def test_returns_default_first(self, db_session, seed_one_guest_for_billing):
        gid = seed_one_guest_for_billing.id
        BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "Second", "is_default": False},
        )
        BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "Default", "is_default": True},
        )
        rows = BillingProfileService.get_profiles(db=db_session, guest_id=gid)
        assert len(rows) == 2
        assert rows[0].label == "Default"  # default first

    def test_excludes_inactive(self, db_session, seed_one_guest_for_billing):
        gid = seed_one_guest_for_billing.id
        p1 = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "Active"},
        )
        p2 = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "Soft"},
        )
        BillingProfileService.delete_profile(db=db_session, profile_id=p2.id)
        rows = BillingProfileService.get_profiles(db=db_session, guest_id=gid, active_only=True)
        ids = [r.id for r in rows]
        assert p1.id in ids
        assert p2.id not in ids


class TestUpdateProfile:
    def test_update_label(self, db_session, seed_one_guest_for_billing):
        prof = BillingProfileService.create_profile(
            db=db_session, guest_id=seed_one_guest_for_billing.id,
            property_id="los-monges", data={"label": "Old"},
        )
        updated = BillingProfileService.update_profile(
            db=db_session, profile_id=prof.id, data={"label": "New"},
        )
        assert updated.label == "New"

    def test_update_missing_returns_none(self, db_session, seed_property):
        assert BillingProfileService.update_profile(
            db=db_session, profile_id=99999, data={"label": "x"},
        ) is None


class TestSetDefault:
    def test_set_default_clears_siblings(self, db_session, seed_one_guest_for_billing):
        gid = seed_one_guest_for_billing.id
        p1 = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "First", "is_default": True},
        )
        p2 = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "Second"},
        )
        # Now make p2 the default
        BillingProfileService.set_default(db=db_session, guest_id=gid, profile_id=p2.id)
        db_session.refresh(p1)
        db_session.refresh(p2)
        assert p1.is_default is False
        assert p2.is_default is True

    def test_set_default_rejects_inactive(self, db_session, seed_one_guest_for_billing):
        gid = seed_one_guest_for_billing.id
        p = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"label": "X"},
        )
        BillingProfileService.delete_profile(db=db_session, profile_id=p.id)
        with pytest.raises(BillingProfileError):
            BillingProfileService.set_default(db=db_session, guest_id=gid, profile_id=p.id)


class TestDeleteProfile:
    def test_soft_delete_clears_default(self, db_session, seed_one_guest_for_billing):
        prof = BillingProfileService.create_profile(
            db=db_session, guest_id=seed_one_guest_for_billing.id,
            property_id="los-monges",
            data={"label": "Will delete", "is_default": True},
        )
        BillingProfileService.delete_profile(db=db_session, profile_id=prof.id)
        db_session.refresh(prof)
        assert prof.is_active is False
        assert prof.is_default is False


# ======================================================================
# find_or_create_from_checkin
# ======================================================================
class TestFindOrCreateFromCheckin:
    def test_creates_when_none_exist(self, db_session, seed_one_guest_for_billing):
        prof = BillingProfileService.find_or_create_from_checkin(
            db=db_session, guest_id=seed_one_guest_for_billing.id,
            property_id="los-monges",
            razon_social="Mi Empresa S.A.", ruc="80012345-6",
        )
        assert prof is not None
        assert prof.business_name == "Mi Empresa S.A."
        assert prof.tax_id_number == "80012345-6"
        assert prof.is_default is True  # first one

    def test_matches_by_tax_id(self, db_session, seed_one_guest_for_billing):
        gid = seed_one_guest_for_billing.id
        existing = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"business_name": "Old Name", "tax_id_number": "MATCH-1"},
        )
        match = BillingProfileService.find_or_create_from_checkin(
            db=db_session, guest_id=gid, property_id="los-monges",
            razon_social="New Different Name", ruc="MATCH-1",
        )
        assert match.id == existing.id  # matched, not created

    def test_matches_by_business_name_when_no_tax_id(self, db_session, seed_one_guest_for_billing):
        gid = seed_one_guest_for_billing.id
        existing = BillingProfileService.create_profile(
            db=db_session, guest_id=gid, property_id="los-monges",
            data={"business_name": "Same Co"},
        )
        match = BillingProfileService.find_or_create_from_checkin(
            db=db_session, guest_id=gid, property_id="los-monges",
            razon_social="Same Co", ruc=None,
        )
        assert match.id == existing.id

    def test_blank_input_returns_none(self, db_session, seed_one_guest_for_billing):
        prof = BillingProfileService.find_or_create_from_checkin(
            db=db_session, guest_id=seed_one_guest_for_billing.id,
            property_id="los-monges",
            razon_social=None, ruc=None,
        )
        assert prof is None


# ======================================================================
# Integration: checkin auto-creates BillingProfile
# ======================================================================
class TestCheckinAutoCreatesProfile:
    def test_register_checkin_creates_profile_and_links(self, db_session, seed_full):
        room_id = seed_full["rooms"][0].id
        # Note: CheckInCreate.billing_ruc validator strips non-digit/non-hyphen
        # chars (RUC paraguayo: XXXXXXXX-X), so use only digits + hyphens here.
        ci_data = CheckInCreate(
            room_id=room_id,
            last_name="Bill",
            first_name="Auto",
            document_number="BILL-AUTO-1",
            billing_name="My Company SRL",
            billing_ruc="80012345-6",
        )
        cid = CheckInService.register_checkin(db_session, ci_data)
        ci = db_session.query(CheckIn).filter(CheckIn.id == cid).first()
        assert ci.guest_id is not None
        assert ci.billing_profile_id is not None

        prof = db_session.query(BillingProfile).filter(BillingProfile.id == ci.billing_profile_id).first()
        assert prof is not None
        assert prof.guest_id == ci.guest_id
        assert prof.business_name == "My Company SRL"
        assert prof.tax_id_number == "80012345-6"


# ======================================================================
# API LAYER
# ======================================================================
class TestBillingEndpoints:
    def test_unauthenticated(self, client, seed_property):
        r = client.get("/api/v1/huespedes/1/billing")
        assert r.status_code in (401, 403)

    def test_create_and_list(self, client, auth_headers_admin, seed_property):
        # Create guest first
        rg = client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "API", "last_name": "Bill"},
        )
        gid = rg.json()["id"]

        # Create profile
        rp = client.post(
            f"/api/v1/huespedes/{gid}/billing",
            headers=auth_headers_admin,
            json={"label": "Empresa", "tax_id_type": "RUC", "tax_id_number": "RUC-001"},
        )
        assert rp.status_code == 200, rp.text
        pid = rp.json()["id"]

        # List
        rl = client.get(f"/api/v1/huespedes/{gid}/billing", headers=auth_headers_admin)
        assert rl.status_code == 200
        items = rl.json()
        assert any(p["id"] == pid for p in items)

    def test_set_default_endpoint(self, client, auth_headers_admin, seed_property):
        rg = client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "X", "last_name": "Default"},
        )
        gid = rg.json()["id"]
        rp1 = client.post(
            f"/api/v1/huespedes/{gid}/billing",
            headers=auth_headers_admin,
            json={"label": "First"},
        )
        rp2 = client.post(
            f"/api/v1/huespedes/{gid}/billing",
            headers=auth_headers_admin,
            json={"label": "Second"},
        )
        rd = client.post(
            f"/api/v1/huespedes/{gid}/billing/{rp2.json()['id']}/default",
            headers=auth_headers_admin,
        )
        assert rd.status_code == 200
        assert rd.json()["is_default"] is True

    def test_delete_returns_404_when_missing(self, client, auth_headers_admin, seed_property):
        rg = client.post(
            "/api/v1/huespedes",
            headers=auth_headers_admin,
            json={"first_name": "X", "last_name": "Y"},
        )
        gid = rg.json()["id"]
        r = client.delete(
            f"/api/v1/huespedes/{gid}/billing/99999",
            headers=auth_headers_admin,
        )
        assert r.status_code == 404
