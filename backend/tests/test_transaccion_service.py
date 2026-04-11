"""
Tests for TransaccionService — Payment transactions
=====================================================
"""

import pytest
from datetime import datetime

from services import TransaccionService, TransaccionError, CajaService
from database import Transaccion, Reservation


class TestRegistrarPago:
    """Tests for registering payments."""

    def test_registrar_transferencia_sin_caja(self, db_session, seed_full, make_reservation):
        """TRANSFERENCIA/POS do NOT require an open caja session."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=100000.0,
            payment_method="TRANSFERENCIA",
            reference_number="REF123",
            created_by="admin",
        )
        assert trans.id is not None
        assert trans.amount == 100000.0
        assert trans.payment_method == "TRANSFERENCIA"
        assert trans.caja_sesion_id is None
        assert trans.voided is False

    def test_registrar_pos_sin_caja(self, db_session, seed_full, make_reservation):
        """POS transactions don't require a caja session."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=50000.0,
            payment_method="POS",
            reference_number="POS-001",
            created_by="recepcion",
        )
        assert trans.payment_method == "POS"
        assert trans.caja_sesion_id is None

    def test_registrar_efectivo_requiere_caja_abierta(
        self, db_session, seed_full, make_reservation
    ):
        """EFECTIVO payment without an open caja session must fail with TransaccionError."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        with pytest.raises(TransaccionError) as exc:
            TransaccionService.registrar_pago(
                db_session,
                reserva_id=res.id,
                amount=50000.0,
                payment_method="EFECTIVO",
                created_by="admin",
                user_id=seed_full["admin"].id,  # user has no open session yet
            )
        assert "caja" in str(exc.value).lower()

    def test_registrar_efectivo_con_caja_abierta_ok(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """With an open session, EFECTIVO is linked to the session_id."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=50000.0,
            payment_method="EFECTIVO",
            created_by="admin",
            user_id=seed_full["admin"].id,
        )
        assert trans.caja_sesion_id == open_caja_session.id

    def test_registrar_monto_cero_falla(self, db_session, seed_full, make_reservation):
        """Amount must be > 0."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session,
                reserva_id=res.id,
                amount=0.0,
                payment_method="TRANSFERENCIA",
            )

    def test_registrar_monto_negativo_falla(self, db_session, seed_full, make_reservation):
        """Negative amounts must be rejected."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session,
                reserva_id=res.id,
                amount=-100.0,
                payment_method="TRANSFERENCIA",
            )

    def test_registrar_metodo_invalido_falla(self, db_session, seed_full, make_reservation):
        """Invalid payment method must be rejected."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session,
                reserva_id=res.id,
                amount=100.0,
                payment_method="BITCOIN",
            )

    def test_registrar_en_reserva_inexistente_falla(self, db_session, seed_full):
        """Reservation must exist."""
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session,
                reserva_id="NOEXISTE",
                amount=100.0,
                payment_method="TRANSFERENCIA",
            )

    def test_registrar_en_reserva_cancelada_falla(
        self, db_session, seed_full, make_reservation
    ):
        """Cannot register a payment on a CANCELADA reservation."""
        res = make_reservation(price=100000.0, status="CANCELADA")
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session,
                reserva_id=res.id,
                amount=50000.0,
                payment_method="TRANSFERENCIA",
            )


class TestStatusRecalculation:
    """Tests for automatic status recalculation after payments."""

    def test_primer_pago_parcial_a_senada(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """First partial payment: RESERVADA → SEÑADA."""
        res = make_reservation(price=200000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=50000.0,
            payment_method="EFECTIVO",
            user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "SEÑADA"

    def test_pago_total_a_confirmada(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Paying the full amount: RESERVADA → CONFIRMADA."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=100000.0,
            payment_method="EFECTIVO",
            user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"

    def test_pago_excedente_a_confirmada(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Paying MORE than total: still CONFIRMADA (tip/over)."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=120000.0,
            payment_method="EFECTIVO",
            user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"

    def test_segundo_pago_completa_confirmada(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Two partial payments summing to total: SEÑADA → CONFIRMADA."""
        res = make_reservation(price=200000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=80000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "SEÑADA"

        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=120000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"

    def test_cancelada_no_cambia_tras_pago(
        self, db_session, seed_full, make_reservation
    ):
        """CANCELADA is terminal — cannot register payments (test via protection)."""
        res = make_reservation(price=100000.0, status="CANCELADA")
        with pytest.raises(TransaccionError):
            TransaccionService.registrar_pago(
                db_session, reserva_id=res.id,
                amount=100000.0, payment_method="TRANSFERENCIA",
            )
        db_session.refresh(res)
        assert res.status == "CANCELADA"

    def test_completada_no_cambia_tras_pago(
        self, db_session, seed_full, make_reservation
    ):
        """COMPLETADA reservations are terminal — status stays COMPLETADA even if a payment is registered."""
        res = make_reservation(price=100000.0, status="COMPLETADA")
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="TRANSFERENCIA", reference_number="late",
        )
        db_session.refresh(res)
        assert res.status == "COMPLETADA"  # unchanged


class TestVoid:
    """Tests for voiding transactions."""

    def test_anular_transaccion_basica(
        self, db_session, seed_full, reserva_con_pago_parcial
    ):
        """Voiding a transaction sets voided=True with reason/user/timestamp."""
        trans = db_session.query(Transaccion).filter(
            Transaccion.reserva_id == reserva_con_pago_parcial.id,
            Transaccion.voided == False
        ).first()
        assert trans is not None

        voided = TransaccionService.anular_transaccion(
            db_session,
            transaccion_id=trans.id,
            reason="Error de monto ingresado por recepcion",
            user="admin",
        )
        assert voided.voided is True
        assert voided.void_reason == "Error de monto ingresado por recepcion"
        assert voided.voided_by == "admin"
        assert voided.voided_at is not None

    def test_anular_razon_corta_falla(
        self, db_session, seed_full, reserva_con_pago_parcial
    ):
        """Reason must be at least 3 characters."""
        trans = db_session.query(Transaccion).filter(
            Transaccion.reserva_id == reserva_con_pago_parcial.id
        ).first()
        with pytest.raises(TransaccionError):
            TransaccionService.anular_transaccion(
                db_session, transaccion_id=trans.id, reason="ab", user="admin"
            )

    def test_anular_razon_vacia_falla(
        self, db_session, seed_full, reserva_con_pago_parcial
    ):
        """Empty reason is rejected."""
        trans = db_session.query(Transaccion).filter(
            Transaccion.reserva_id == reserva_con_pago_parcial.id
        ).first()
        with pytest.raises(TransaccionError):
            TransaccionService.anular_transaccion(
                db_session, transaccion_id=trans.id, reason="", user="admin"
            )

    def test_anular_dos_veces_falla(
        self, db_session, seed_full, reserva_con_pago_parcial
    ):
        """Cannot void an already-voided transaction."""
        trans = db_session.query(Transaccion).filter(
            Transaccion.reserva_id == reserva_con_pago_parcial.id
        ).first()
        TransaccionService.anular_transaccion(
            db_session, transaccion_id=trans.id, reason="primera", user="admin"
        )
        with pytest.raises(TransaccionError):
            TransaccionService.anular_transaccion(
                db_session, transaccion_id=trans.id, reason="segunda", user="admin"
            )

    def test_anular_recalcula_status(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Voiding the only payment should downgrade CONFIRMADA → RESERVADA."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"

        TransaccionService.anular_transaccion(
            db_session, transaccion_id=trans.id,
            reason="Reversal test", user="admin",
        )
        db_session.refresh(res)
        assert res.status == "RESERVADA"

    def test_anular_parcial_deja_senada(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Voiding one of two partial payments: CONFIRMADA → SEÑADA."""
        res = make_reservation(price=200000.0, status="RESERVADA")
        t1 = TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        t2 = TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        db_session.refresh(res)
        assert res.status == "CONFIRMADA"

        TransaccionService.anular_transaccion(
            db_session, transaccion_id=t1.id,
            reason="Error test", user="admin",
        )
        db_session.refresh(res)
        assert res.status == "SEÑADA"


class TestSaldoQueries:
    """Tests for saldo computations and queries."""

    def test_saldo_sin_pagos(self, db_session, seed_full, make_reservation):
        """A reservation with no payments shows paid=0, pending=total."""
        res = make_reservation(price=150000.0, status="RESERVADA")
        saldo = TransaccionService.get_saldo(db_session, res.id)
        assert saldo["total"] == 150000.0
        assert saldo["paid"] == 0.0
        assert saldo["pending"] == 150000.0
        assert saldo["transacciones"] == []

    def test_saldo_pago_parcial(
        self, db_session, seed_full, reserva_con_pago_parcial
    ):
        """After a 100k partial on a 200k reservation: paid=100k, pending=100k."""
        saldo = TransaccionService.get_saldo(db_session, reserva_con_pago_parcial.id)
        assert saldo["total"] == 200000.0
        assert saldo["paid"] == 100000.0
        assert saldo["pending"] == 100000.0
        assert len(saldo["transacciones"]) == 1

    def test_saldo_reserva_inexistente(self, db_session, seed_full):
        """Non-existent reservation returns None."""
        assert TransaccionService.get_saldo(db_session, "NOEXISTE") is None

    def test_saldo_excluye_anuladas(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Voided transactions don't count towards paid."""
        res = make_reservation(price=100000.0, status="RESERVADA")
        trans = TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        TransaccionService.anular_transaccion(
            db_session, transaccion_id=trans.id,
            reason="test void", user="admin",
        )
        saldo = TransaccionService.get_saldo(db_session, res.id)
        assert saldo["paid"] == 0.0
        assert saldo["pending"] == 100000.0


class TestListTransactions:
    """Tests for listing/filtering transactions."""

    def test_list_filter_by_method(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Filtering by payment_method returns only matching transactions."""
        res = make_reservation(price=500000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=100000.0,
            payment_method="EFECTIVO", user_id=seed_full["admin"].id,
        )
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=200000.0,
            payment_method="TRANSFERENCIA", reference_number="ref1",
        )
        TransaccionService.registrar_pago(
            db_session, reserva_id=res.id, amount=150000.0,
            payment_method="POS", reference_number="pos1",
        )

        efectivo = TransaccionService.list_transactions(db_session, payment_method="EFECTIVO")
        transfer = TransaccionService.list_transactions(db_session, payment_method="TRANSFERENCIA")
        pos = TransaccionService.list_transactions(db_session, payment_method="POS")

        assert len(efectivo) == 1
        assert len(transfer) == 1
        assert len(pos) == 1
        assert efectivo[0].amount == 100000.0
        assert transfer[0].amount == 200000.0
        assert pos[0].amount == 150000.0

    def test_list_excludes_voided_by_default(
        self, db_session, seed_full, reserva_con_pago_parcial
    ):
        """list_transactions excludes voided unless include_voided=True."""
        trans = db_session.query(Transaccion).filter(
            Transaccion.reserva_id == reserva_con_pago_parcial.id
        ).first()
        TransaccionService.anular_transaccion(
            db_session, transaccion_id=trans.id,
            reason="test void", user="admin",
        )

        active = TransaccionService.list_transactions(db_session)
        all_trans = TransaccionService.list_transactions(db_session, include_voided=True)

        assert len(active) == 0
        assert len(all_trans) == 1
