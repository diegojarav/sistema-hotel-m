"""
Multi-currency MVP (v1.10.0 — Phase 2d).

Covers:
- CurrencyService config: get accepted, add, update rate, remove, base lookup
- Conversion: base→base passthrough, USD→PYG, BRL→PYG, unknown rejection
- Payment with currency_code: snapshot fields populated, amount in base
- Back-compat: legacy payment without currency_code → all currency fields NULL
- Caja session summary: currency_breakdown groups by code, sums correctly
- Formatting: PYG vs USD vs BRL decimal/separator conventions
- Endpoint integration: /currencies CRUD + payment with currency
"""
from datetime import date, timedelta

import pytest
from fastapi import status

from database import (
    AcceptedCurrency,
    CajaSesion,
    Property,
    Reservation,
    Transaccion,
)
from services import (
    CajaService,
    CurrencyError,
    CurrencyService,
    TransaccionService,
)


# ----------------------------------------------------------------------
# Test fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def seeded_currencies(db_session, seed_property):
    """Seed PYG (base) + USD + BRL for los-monges, mirroring migration 017."""
    # Ensure no leftover rows from other tests (shared in-memory DB)
    db_session.query(AcceptedCurrency).filter(
        AcceptedCurrency.property_id == "los-monges"
    ).delete()
    db_session.commit()

    pyg = AcceptedCurrency(
        property_id="los-monges", currency_code="PYG",
        currency_name="Guaraní paraguayo", currency_symbol="₲",
        decimal_places=0, exchange_rate=1.0, sort_order=0, is_active=True,
    )
    usd = AcceptedCurrency(
        property_id="los-monges", currency_code="USD",
        currency_name="Dólar estadounidense", currency_symbol="US$",
        decimal_places=2, exchange_rate=7500.0, sort_order=1, is_active=True,
    )
    brl = AcceptedCurrency(
        property_id="los-monges", currency_code="BRL",
        currency_name="Real brasileño", currency_symbol="R$",
        decimal_places=2, exchange_rate=1450.0, sort_order=2, is_active=True,
    )
    db_session.add_all([pyg, usd, brl])
    db_session.commit()
    return {"PYG": pyg, "USD": usd, "BRL": brl}


# ======================================================================
# Configuration
# ======================================================================
class TestConfig:
    def test_base_currency_is_pyg_for_los_monges(self, db_session, seed_property):
        assert CurrencyService.get_base_currency(db=db_session) == "PYG"

    def test_get_accepted_currencies_returns_all_active(self, db_session, seeded_currencies):
        rows = CurrencyService.get_accepted_currencies(db=db_session)
        codes = [r.currency_code for r in rows]
        assert codes == ["PYG", "USD", "BRL"]  # ordered by sort_order

    def test_add_accepted_currency(self, db_session, seeded_currencies):
        row = CurrencyService.add_accepted_currency(
            db=db_session, property_id="los-monges",
            currency_code="ARS", exchange_rate=8.5, sort_order=10,
        )
        assert row.currency_code == "ARS"
        assert row.exchange_rate == 8.5
        assert row.currency_name == "Peso argentino"  # snapshot from catalogue

    def test_add_with_unknown_currency_code_rejected(self, db_session, seed_property):
        with pytest.raises(CurrencyError) as exc:
            CurrencyService.add_accepted_currency(
                db=db_session, property_id="los-monges",
                currency_code="XYZ", exchange_rate=10.0,
            )
        assert "catálogo" in str(exc.value).lower()

    def test_add_existing_currency_updates_rate(self, db_session, seeded_currencies):
        row = CurrencyService.add_accepted_currency(
            db=db_session, property_id="los-monges",
            currency_code="USD", exchange_rate=7800.0,
        )
        assert row.exchange_rate == 7800.0
        # Same row reused (idempotent)
        all_usd = db_session.query(AcceptedCurrency).filter(
            AcceptedCurrency.property_id == "los-monges",
            AcceptedCurrency.currency_code == "USD",
        ).all()
        assert len(all_usd) == 1

    def test_update_exchange_rate(self, db_session, seeded_currencies):
        row = CurrencyService.update_exchange_rate(
            db=db_session, property_id="los-monges",
            currency_code="USD", new_rate=7800.0,
        )
        assert row.exchange_rate == 7800.0
        assert row.rate_updated_at is not None

    def test_cannot_update_base_currency_rate(self, db_session, seeded_currencies):
        with pytest.raises(CurrencyError) as exc:
            CurrencyService.update_exchange_rate(
                db=db_session, property_id="los-monges",
                currency_code="PYG", new_rate=2.0,
            )
        assert "base" in str(exc.value).lower()

    def test_cannot_remove_base_currency(self, db_session, seeded_currencies):
        with pytest.raises(CurrencyError) as exc:
            CurrencyService.remove_accepted_currency(
                db=db_session, property_id="los-monges", currency_code="PYG",
            )
        assert "base" in str(exc.value).lower()

    def test_remove_currency_soft_deactivates(self, db_session, seeded_currencies):
        CurrencyService.remove_accepted_currency(
            db=db_session, property_id="los-monges", currency_code="BRL",
        )
        # Default get_accepted_currencies filters out inactive
        active = CurrencyService.get_accepted_currencies(db=db_session)
        assert "BRL" not in [r.currency_code for r in active]
        # But the row still exists (soft delete)
        all_rows = CurrencyService.get_accepted_currencies(
            db=db_session, active_only=False,
        )
        assert "BRL" in [r.currency_code for r in all_rows]


# ======================================================================
# Conversion
# ======================================================================
class TestConversion:
    def test_convert_base_to_base(self, db_session, seeded_currencies):
        conv = CurrencyService.convert_to_base(
            db=db_session, amount_original=150000.0,
            currency_code="PYG", property_id="los-monges",
        )
        assert conv["amount_base"] == 150000.0
        assert conv["exchange_rate"] == 1.0
        assert conv["currency_code"] == "PYG"
        assert conv["amount_original"] == 150000.0

    def test_convert_usd_to_pyg(self, db_session, seeded_currencies):
        conv = CurrencyService.convert_to_base(
            db=db_session, amount_original=100.0,
            currency_code="USD", property_id="los-monges",
        )
        # 100 USD × 7500 = 750,000 PYG
        assert conv["amount_base"] == 750000.0
        assert conv["exchange_rate"] == 7500.0
        assert conv["amount_original"] == 100.0

    def test_convert_brl_to_pyg(self, db_session, seeded_currencies):
        conv = CurrencyService.convert_to_base(
            db=db_session, amount_original=200.0,
            currency_code="BRL", property_id="los-monges",
        )
        # 200 BRL × 1450 = 290,000 PYG
        assert conv["amount_base"] == 290000.0
        assert conv["exchange_rate"] == 1450.0

    def test_convert_unknown_currency_rejected(self, db_session, seeded_currencies):
        with pytest.raises(CurrencyError):
            CurrencyService.convert_to_base(
                db=db_session, amount_original=100.0,
                currency_code="JPY", property_id="los-monges",
            )

    def test_convert_inactive_currency_rejected(self, db_session, seeded_currencies):
        # Deactivate USD
        CurrencyService.remove_accepted_currency(
            db=db_session, property_id="los-monges", currency_code="USD",
        )
        with pytest.raises(CurrencyError):
            CurrencyService.convert_to_base(
                db=db_session, amount_original=100.0,
                currency_code="USD", property_id="los-monges",
            )

    def test_convert_zero_or_negative_rejected(self, db_session, seeded_currencies):
        with pytest.raises(CurrencyError):
            CurrencyService.convert_to_base(
                db=db_session, amount_original=0,
                currency_code="USD", property_id="los-monges",
            )


# ======================================================================
# Payment with currency
# ======================================================================
class TestPaymentWithCurrency:
    def test_register_payment_in_usd(
        self, db_session, seeded_currencies, make_reservation, open_caja_session,
    ):
        res = make_reservation(price=750000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=100.0,                # 100 USD
            payment_method="TRANSFERENCIA",
            currency_code="USD",
            reference_number="TR-001",
        )
        # amount column = base currency total
        assert trans.amount == 750000.0
        # Snapshot fields preserve the original tender
        assert trans.amount_original == 100.0
        assert trans.currency_code == "USD"
        assert trans.exchange_rate == 7500.0

    def test_register_payment_in_brl(
        self, db_session, seeded_currencies, make_reservation, open_caja_session,
    ):
        res = make_reservation(price=290000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=200.0,
            payment_method="POS",
            currency_code="BRL",
            reference_number="POS-001",
        )
        assert trans.amount == 290000.0
        assert trans.amount_original == 200.0
        assert trans.currency_code == "BRL"
        assert trans.exchange_rate == 1450.0

    def test_register_payment_explicit_base_currency(
        self, db_session, seeded_currencies, make_reservation, open_caja_session,
    ):
        """Explicit currency_code=PYG should populate the snapshot fields
        too (rate=1, original=amount) so the reports stay consistent."""
        res = make_reservation(price=150000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=150000.0,
            payment_method="TRANSFERENCIA",
            currency_code="PYG",
            reference_number="REF-001",
        )
        assert trans.amount == 150000.0
        assert trans.currency_code == "PYG"
        assert trans.exchange_rate == 1.0
        assert trans.amount_original == 150000.0

    def test_register_payment_legacy_no_currency(
        self, db_session, seeded_currencies, make_reservation, open_caja_session,
    ):
        """Back-compat: no currency_code → currency fields stay NULL."""
        res = make_reservation(price=150000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=150000.0,
            payment_method="TRANSFERENCIA",
            reference_number="REF-001",
        )
        assert trans.amount == 150000.0
        assert trans.currency_code is None
        assert trans.exchange_rate is None
        assert trans.amount_original is None

    def test_register_payment_unknown_currency_rejected(
        self, db_session, seeded_currencies, make_reservation,
    ):
        from services import TransaccionError
        res = make_reservation(price=100000.0, status="RESERVADA")
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session,
                reserva_id=res.id,
                amount=100.0,
                payment_method="TRANSFERENCIA",
                currency_code="JPY",
            )


# ======================================================================
# Caja session breakdown by currency
# ======================================================================
class TestCajaCurrencyBreakdown:
    def test_caja_summary_groups_by_currency(
        self, db_session, seeded_currencies, make_reservation, open_caja_session,
    ):
        """Mixed currencies should appear as separate rows in the breakdown."""
        res = make_reservation(price=2_000_000.0, status="RESERVADA")
        # 750k PYG cash + 100 USD transfer + 500 BRL transfer
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=750000.0,
            payment_method="EFECTIVO",
            currency_code="PYG",
            user_id=open_caja_session.user_id,
        )
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100.0,
            payment_method="TRANSFERENCIA",
            currency_code="USD",
            reference_number="T1",
        )
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=500.0,
            payment_method="TRANSFERENCIA",
            currency_code="BRL",
            reference_number="T2",
        )

        summary = CajaService.get_session_summary(db_session, open_caja_session.id)
        breakdown = {b["currency_code"]: b for b in summary["currency_breakdown"]}
        assert set(breakdown.keys()) == {"PYG", "USD", "BRL"}
        # PYG total in original = total in base (rate 1)
        assert breakdown["PYG"]["total_original"] == 750000.0
        assert breakdown["PYG"]["total_base"] == 750000.0
        # USD: 100 original × 7500 = 750_000 base
        assert breakdown["USD"]["total_original"] == 100.0
        assert breakdown["USD"]["total_base"] == 750000.0
        # BRL: 500 × 1450 = 725_000 base
        assert breakdown["BRL"]["total_original"] == 500.0
        assert breakdown["BRL"]["total_base"] == 725000.0

    def test_caja_summary_treats_legacy_null_as_base(
        self, db_session, seeded_currencies, make_reservation, open_caja_session,
    ):
        """Legacy transaction (currency_code=NULL) should appear under base ccy."""
        res = make_reservation(price=200000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=200000.0,
            payment_method="TRANSFERENCIA",
            reference_number="LEGACY-1",
            # NO currency_code → legacy path
        )
        summary = CajaService.get_session_summary(db_session, open_caja_session.id)
        codes = [b["currency_code"] for b in summary["currency_breakdown"]]
        assert codes == ["PYG"]
        assert summary["currency_breakdown"][0]["total_base"] == 200000.0


# ======================================================================
# Formatting
# ======================================================================
class TestFormatting:
    def test_format_pyg(self):
        # 750_000 PYG → "₲ 750.000" (no decimals)
        assert CurrencyService.format_amount(750000, "PYG") == "₲ 750.000"

    def test_format_usd(self):
        # 100 USD → "US$ 100,00"
        assert CurrencyService.format_amount(100, "USD") == "US$ 100,00"

    def test_format_brl(self):
        # 1234.50 BRL → "R$ 1.234,50"
        assert CurrencyService.format_amount(1234.50, "BRL") == "R$ 1.234,50"

    def test_format_without_symbol(self):
        assert CurrencyService.format_amount(750000, "PYG", with_symbol=False) == "750.000"

    def test_format_unknown_code_graceful(self):
        # Should not crash on unknown — graceful fallback
        result = CurrencyService.format_amount(100, "JPY")
        assert "JPY" in result and "100" in result


# ======================================================================
# Endpoint integration
# ======================================================================
class TestEndpoints:
    def test_get_catalog(self, client, seeded_currencies, auth_headers_admin):
        r = client.get("/api/v1/currencies/catalog", headers=auth_headers_admin)
        assert r.status_code == status.HTTP_200_OK
        body = r.json()
        codes = {entry["code"] for entry in body}
        assert {"PYG", "USD", "BRL", "ARS", "EUR"}.issubset(codes)

    def test_get_base_currency(self, client, seeded_currencies, auth_headers_admin):
        r = client.get("/api/v1/currencies/base", headers=auth_headers_admin)
        assert r.status_code == status.HTTP_200_OK
        assert r.json() == {"base_currency": "PYG"}

    def test_list_accepted(self, client, seeded_currencies, auth_headers_admin):
        r = client.get("/api/v1/currencies", headers=auth_headers_admin)
        assert r.status_code == status.HTTP_200_OK
        codes = [c["currency_code"] for c in r.json()]
        assert codes == ["PYG", "USD", "BRL"]

    def test_add_currency_via_api(self, client, seeded_currencies, auth_headers_admin):
        r = client.post(
            "/api/v1/currencies",
            json={"currency_code": "ARS", "exchange_rate": 8.5, "sort_order": 5},
            headers=auth_headers_admin,
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["currency_code"] == "ARS"
        assert r.json()["exchange_rate"] == 8.5

    def test_update_rate_via_api(self, client, seeded_currencies, auth_headers_admin):
        r = client.put(
            "/api/v1/currencies/USD/rate",
            json={"exchange_rate": 7800.0},
            headers=auth_headers_admin,
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["exchange_rate"] == 7800.0

    def test_payment_endpoint_accepts_currency_code(
        self, client, seeded_currencies, make_reservation, auth_headers_admin,
    ):
        """POST /transacciones with currency_code=USD: stored amount = base,
        original snapshot preserved."""
        res = make_reservation(price=750000.0, status="RESERVADA")
        r = client.post(
            "/api/v1/transacciones/",
            json={
                "reserva_id": res.id,
                "amount": 100.0,
                "payment_method": "TRANSFERENCIA",
                "currency_code": "USD",
                "reference_number": "T-USD-1",
            },
            headers=auth_headers_admin,
        )
        assert r.status_code == status.HTTP_200_OK
        body = r.json()
        assert body["amount"] == 750000.0
        assert body["amount_original"] == 100.0
        assert body["currency_code"] == "USD"
        assert body["exchange_rate"] == 7500.0
