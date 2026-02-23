"""
Tests for Pydantic schema validations.

Ensures business rules are enforced at the DTO level.
"""

import pytest
from datetime import date, timedelta
from pydantic import ValidationError
from schemas import (
    ReservationCreate,
    CheckInCreate,
    PriceCalculationRequest,
    validate_phone_format,
    validate_document_format,
)


# ==========================================
# HELPER
# ==========================================

def _valid_reservation(**overrides):
    """Build a valid ReservationCreate dict with optional overrides."""
    data = {
        "check_in_date": date.today() + timedelta(days=7),
        "stay_days": 2,
        "guest_name": "García, Juan",
        "room_ids": ["los-monges-room-001"],
        "price": 150000.0,
    }
    data.update(overrides)
    return data


# ==========================================
# ReservationCreate
# ==========================================

def test_reservation_create_valid():
    r = ReservationCreate(**_valid_reservation())
    assert r.guest_name == "García, Juan"
    assert r.stay_days == 2


def test_reservation_create_name_too_short():
    with pytest.raises(ValidationError, match="2 characters"):
        ReservationCreate(**_valid_reservation(guest_name="A"))


def test_reservation_create_past_date():
    with pytest.raises(ValidationError, match="anterior a hoy"):
        ReservationCreate(**_valid_reservation(
            check_in_date=date.today() - timedelta(days=1)
        ))


def test_reservation_create_zero_stay():
    with pytest.raises(ValidationError):
        ReservationCreate(**_valid_reservation(stay_days=0))


def test_reservation_create_negative_price():
    with pytest.raises(ValidationError):
        ReservationCreate(**_valid_reservation(price=-100))


def test_reservation_create_empty_rooms():
    with pytest.raises(ValidationError, match="too_short|at least 1"):
        ReservationCreate(**_valid_reservation(room_ids=[]))


def test_reservation_create_whitespace_rooms():
    """Room IDs that are just whitespace should be rejected."""
    with pytest.raises(ValidationError, match="al menos una habitación"):
        ReservationCreate(**_valid_reservation(room_ids=["  ", ""]))


def test_reservation_create_phone_normalized():
    r = ReservationCreate(**_valid_reservation(contact_phone="(0981) 123-456"))
    assert r.contact_phone == "+0981123456" or r.contact_phone == "0981123456"
    # The validator strips everything except digits and +
    assert all(c.isdigit() or c == "+" for c in r.contact_phone)


def test_reservation_create_today_is_valid():
    """Today's date should be accepted (not past)."""
    r = ReservationCreate(**_valid_reservation(check_in_date=date.today()))
    assert r.check_in_date == date.today()


# ==========================================
# CheckInCreate
# ==========================================

def test_checkin_create_doc_normalized():
    c = CheckInCreate(document_number="1.234.567")
    assert c.document_number == "1234567"


def test_checkin_create_doc_uppercase():
    c = CheckInCreate(document_number="abc123")
    assert c.document_number == "ABC123"


def test_checkin_create_future_birth_rejected():
    with pytest.raises(ValidationError, match="no puede ser futura"):
        CheckInCreate(birth_date=date.today() + timedelta(days=1))


def test_checkin_create_ruc_cleaned():
    c = CheckInCreate(billing_ruc="80.012.345-6")
    assert c.billing_ruc == "80012345-6"


def test_checkin_create_defaults():
    """Empty CheckInCreate should work with all defaults."""
    c = CheckInCreate()
    assert c.last_name == ""
    assert c.document_number == ""
    assert c.room_id is None


# ==========================================
# PriceCalculationRequest
# ==========================================

def test_price_calc_request_valid():
    r = PriceCalculationRequest(
        category_id="los-monges-estandar",
        check_in=date.today() + timedelta(days=7),
        stay_days=3,
    )
    assert r.stay_days == 3


def test_price_calc_request_missing_category():
    with pytest.raises(ValidationError):
        PriceCalculationRequest(
            check_in=date.today() + timedelta(days=7),
            stay_days=3,
        )


# ==========================================
# SHARED VALIDATORS
# ==========================================

def test_validate_phone_format():
    assert validate_phone_format("(0981) 123-456") == "0981123456"
    assert validate_phone_format("+595 981 123456") == "+595981123456"
    assert validate_phone_format("") == ""


def test_validate_document_format():
    assert validate_document_format("1.234.567") == "1234567"
    assert validate_document_format("abc 123") == "ABC123"
    assert validate_document_format("") == ""
