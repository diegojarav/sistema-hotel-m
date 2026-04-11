"""
Tests for CajaService — Cash register sessions
================================================
"""

import pytest
from datetime import datetime

from services import CajaService, CajaSessionError, TransaccionService
from database import CajaSesion, Transaccion


class TestCajaServiceOpen:
    """Tests for opening cash sessions."""

    def test_abrir_sesion_basica(self, db_session, seed_full):
        """Opening a session succeeds for a user without any previous session."""
        admin = seed_full["admin"]
        sesion = CajaService.abrir_sesion(
            db_session,
            user_id=admin.id,
            opening_balance=100000.0,
            notes="Apertura test",
        )
        assert sesion.id is not None
        assert sesion.user_id == admin.id
        assert sesion.opening_balance == 100000.0
        assert sesion.status == "ABIERTA"
        assert sesion.notes == "Apertura test"
        assert sesion.closed_at is None

    def test_abrir_dos_sesiones_mismo_usuario_falla(self, db_session, seed_full):
        """Cannot open a second session while one is already open for the same user."""
        admin = seed_full["admin"]
        CajaService.abrir_sesion(db_session, user_id=admin.id, opening_balance=50000.0)

        with pytest.raises(CajaSessionError) as exc:
            CajaService.abrir_sesion(db_session, user_id=admin.id, opening_balance=50000.0)
        assert "abierta" in str(exc.value).lower()

    def test_abrir_sesion_balance_cero_ok(self, db_session, seed_full):
        """Opening with 0 balance is allowed (no change in till)."""
        admin = seed_full["admin"]
        sesion = CajaService.abrir_sesion(
            db_session, user_id=admin.id, opening_balance=0.0
        )
        assert sesion.opening_balance == 0.0
        assert sesion.status == "ABIERTA"

    def test_dos_usuarios_pueden_tener_sesion_abierta(self, db_session, seed_full):
        """Different users can have open sessions at the same time."""
        admin = seed_full["admin"]
        recep = seed_full["recepcionista"]
        s1 = CajaService.abrir_sesion(db_session, user_id=admin.id, opening_balance=10000)
        s2 = CajaService.abrir_sesion(db_session, user_id=recep.id, opening_balance=20000)
        assert s1.id != s2.id
        assert s1.status == "ABIERTA"
        assert s2.status == "ABIERTA"


class TestCajaServiceClose:
    """Tests for closing cash sessions."""

    def test_cerrar_sin_movimientos(self, db_session, seed_full):
        """Closing a session with no transactions: expected = opening."""
        admin = seed_full["admin"]
        sesion = CajaService.abrir_sesion(
            db_session, user_id=admin.id, opening_balance=100000.0
        )

        closed = CajaService.cerrar_sesion(
            db_session,
            session_id=sesion.id,
            closing_balance_declared=100000.0,
            notes="cierre test",
        )

        assert closed.status == "CERRADA"
        assert closed.closing_balance_declared == 100000.0
        assert closed.closing_balance_expected == 100000.0
        assert closed.difference == 0.0
        assert closed.closed_at is not None

    def test_cerrar_con_movimientos_efectivo(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Closing a session with cash movements: expected = opening + sum(EFECTIVO)."""
        res = make_reservation(price=200000.0, status="RESERVADA")

        # Register 2 cash payments
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=50000.0,
            payment_method="EFECTIVO",
            created_by="admin",
            user_id=seed_full["admin"].id,
        )
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=75000.0,
            payment_method="EFECTIVO",
            created_by="admin",
            user_id=seed_full["admin"].id,
        )

        closed = CajaService.cerrar_sesion(
            db_session,
            session_id=open_caja_session.id,
            closing_balance_declared=225000.0,  # 100k opening + 50k + 75k
        )

        # Expected = 100k opening + 125k cash movements
        assert closed.closing_balance_expected == 225000.0
        assert closed.closing_balance_declared == 225000.0
        assert closed.difference == 0.0

    def test_cerrar_con_diferencia_faltante(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """Declaring less than expected shows negative difference (faltante)."""
        res = make_reservation(price=200000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=50000.0,
            payment_method="EFECTIVO",
            created_by="admin",
            user_id=seed_full["admin"].id,
        )

        closed = CajaService.cerrar_sesion(
            db_session,
            session_id=open_caja_session.id,
            closing_balance_declared=140000.0,  # Expected 150k
        )

        assert closed.closing_balance_expected == 150000.0
        assert closed.difference == -10000.0  # Faltante

    def test_cerrar_ignora_transferencias(
        self, db_session, seed_full, make_reservation, open_caja_session
    ):
        """TRANSFERENCIA and POS transactions do NOT affect cash expected balance."""
        res = make_reservation(price=300000.0, status="RESERVADA")
        TransaccionService.registrar_pago(
            db_session,
            reserva_id=res.id,
            amount=200000.0,
            payment_method="TRANSFERENCIA",
            reference_number="12345",
            created_by="admin",
        )

        closed = CajaService.cerrar_sesion(
            db_session,
            session_id=open_caja_session.id,
            closing_balance_declared=100000.0,
        )

        # Expected = just opening balance, no cash movements
        assert closed.closing_balance_expected == 100000.0
        assert closed.difference == 0.0

    def test_cerrar_sesion_ya_cerrada_falla(self, db_session, seed_full):
        """Trying to close an already-closed session raises an error."""
        admin = seed_full["admin"]
        sesion = CajaService.abrir_sesion(
            db_session, user_id=admin.id, opening_balance=10000.0
        )
        CajaService.cerrar_sesion(
            db_session, session_id=sesion.id, closing_balance_declared=10000.0
        )

        with pytest.raises(CajaSessionError):
            CajaService.cerrar_sesion(
                db_session, session_id=sesion.id, closing_balance_declared=10000.0
            )

    def test_cerrar_sesion_inexistente_falla(self, db_session, seed_full):
        """Closing a non-existent session raises an error."""
        with pytest.raises(CajaSessionError):
            CajaService.cerrar_sesion(
                db_session, session_id=999999, closing_balance_declared=0.0
            )


class TestCajaServiceQueries:
    """Tests for read queries."""

    def test_get_current_session_existente(self, db_session, seed_full, open_caja_session):
        """get_current_session returns the open session for the user."""
        admin = seed_full["admin"]
        sesion = CajaService.get_current_session(db_session, user_id=admin.id)
        assert sesion is not None
        assert sesion.id == open_caja_session.id
        assert sesion.status == "ABIERTA"

    def test_get_current_session_ninguna(self, db_session, seed_full):
        """get_current_session returns None when no open session exists."""
        admin = seed_full["admin"]
        sesion = CajaService.get_current_session(db_session, user_id=admin.id)
        assert sesion is None

    def test_list_sessions_por_usuario(self, db_session, seed_full):
        """list_sessions filters by user_id."""
        admin = seed_full["admin"]
        recep = seed_full["recepcionista"]
        # Admin opens and closes 2 sessions
        s1 = CajaService.abrir_sesion(db_session, user_id=admin.id, opening_balance=10000)
        CajaService.cerrar_sesion(db_session, session_id=s1.id, closing_balance_declared=10000)
        s2 = CajaService.abrir_sesion(db_session, user_id=admin.id, opening_balance=20000)
        CajaService.cerrar_sesion(db_session, session_id=s2.id, closing_balance_declared=20000)
        # Recep opens one
        CajaService.abrir_sesion(db_session, user_id=recep.id, opening_balance=5000)

        admin_sessions = CajaService.list_sessions(db_session, user_id=admin.id)
        recep_sessions = CajaService.list_sessions(db_session, user_id=recep.id)
        assert len(admin_sessions) == 2
        assert len(recep_sessions) == 1
