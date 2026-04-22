"""
Tests for EmailService + email endpoints (v1.8.0 — Phase 5)
=============================================================

Covers:
  - Encryption roundtrip (encrypt_secret/decrypt_secret)
  - _render_body placeholder logic
  - _check_rate_limit window and status filter
  - SMTP config upsert/retrieval (password never returned in SMTPConfigOut)
  - prepare_send validation errors (disabled, missing recipient, missing reservation)
  - Background send success/failure flows (SMTP mocked)
  - Endpoints: PUT /settings/email, POST /settings/email/test,
    POST /email/reserva/{id}/enviar, GET /email/reserva/{id}/historial
  - Rate limit 429 after 3 successful sends within an hour
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from services import EmailService, EmailError
from services.settings_service import SettingsService
from database import EmailLog, Reservation


# ==========================================
# UNIT: encryption helpers
# ==========================================

class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        from api.core.security import encrypt_secret, decrypt_secret
        enc = encrypt_secret("mi-password-secreto-con-ñ-y-tildes")
        assert enc != "mi-password-secreto-con-ñ-y-tildes"
        assert len(enc) > 20
        dec = decrypt_secret(enc)
        assert dec == "mi-password-secreto-con-ñ-y-tildes"

    def test_decrypt_garbage_raises(self):
        from api.core.security import decrypt_secret
        with pytest.raises(ValueError):
            decrypt_secret("not-a-real-token")


# ==========================================
# UNIT: _render_body + _check_rate_limit
# ==========================================

class TestRenderBody:
    def test_replaces_known_placeholders(self):
        tpl = "Hola {nombre_huesped}, gracias por reservar en {nombre_hotel}."
        out = EmailService._render_body(tpl, "Juan Pérez", "Hotel Los Monges")
        assert out == "Hola Juan Pérez, gracias por reservar en Hotel Los Monges."

    def test_unknown_placeholder_left_as_is(self):
        tpl = "Hola {nombre_huesped}, tu código es {codigo_desconocido}."
        out = EmailService._render_body(tpl, "Juan", "Hotel")
        assert out == "Hola Juan, tu código es {codigo_desconocido}."

    def test_missing_both_values(self):
        tpl = "Hola {nombre_huesped}, {nombre_hotel}"
        out = EmailService._render_body(tpl, "", "")
        assert out == "Hola , "


class TestRateLimit:
    def test_counts_only_enviado_status(self, db_session, seed_full, make_reservation):
        res = make_reservation()
        now = datetime.now()

        # 2 ENVIADO + 2 FALLIDO + 1 PENDIENTE — only 2 count
        for status in ["ENVIADO", "ENVIADO", "FALLIDO", "FALLIDO", "PENDIENTE"]:
            db_session.add(EmailLog(
                reserva_id=res.id,
                recipient_email="a@b.com",
                subject="test",
                status=status,
                sent_at=now - timedelta(minutes=10) if status != "PENDIENTE" else None,
                created_at=now - timedelta(minutes=10),
            ))
        db_session.commit()

        count = EmailService._check_rate_limit(db_session, res.id, now=now)
        assert count == 2

    def test_excludes_older_than_one_hour(self, db_session, seed_full, make_reservation):
        res = make_reservation()
        now = datetime.now()

        db_session.add(EmailLog(
            reserva_id=res.id, recipient_email="a@b.com", subject="test",
            status="ENVIADO", sent_at=now - timedelta(hours=2),
        ))
        db_session.add(EmailLog(
            reserva_id=res.id, recipient_email="a@b.com", subject="test",
            status="ENVIADO", sent_at=now - timedelta(minutes=30),
        ))
        db_session.commit()

        assert EmailService._check_rate_limit(db_session, res.id, now=now) == 1


# ==========================================
# UNIT: SettingsService SMTP getters/setters
# ==========================================

class TestSMTPConfig:
    def test_defaults_when_unset(self, db_session, seed_property):
        cfg = SettingsService.get_smtp_config(db=db_session, include_password=False)
        assert cfg["smtp_enabled"] is False
        assert cfg["smtp_host"] is None
        assert cfg["smtp_password_set"] is False
        assert cfg["email_body_template"] == SettingsService.DEFAULT_EMAIL_BODY_TEMPLATE

    def test_save_and_retrieve(self, db_session, seed_property):
        SettingsService.set_smtp_config(
            db=db_session,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="hotel@example.com",
            smtp_password="super-secret",
            smtp_from_name="Hotel Munich",
            smtp_from_email="hotel@example.com",
            smtp_enabled=True,
            email_body_template="Hola {nombre_huesped}",
        )
        # Public GET never exposes the password
        cfg = SettingsService.get_smtp_config(db=db_session)
        assert cfg["smtp_host"] == "smtp.gmail.com"
        assert cfg["smtp_port"] == 587
        assert cfg["smtp_enabled"] is True
        assert cfg["smtp_password_set"] is True
        assert "smtp_password" not in cfg

        # Internal getter (include_password=True) decrypts
        cfg_full = SettingsService.get_smtp_config(db=db_session, include_password=True)
        assert cfg_full["smtp_password"] == "super-secret"

    def test_empty_password_keeps_existing(self, db_session, seed_property):
        SettingsService.set_smtp_config(
            db=db_session,
            smtp_host="smtp.a.com", smtp_port=587, smtp_username="u",
            smtp_password="first-password", smtp_from_name="Hotel",
            smtp_from_email="a@b.com", smtp_enabled=True,
        )
        SettingsService.set_smtp_config(
            db=db_session,
            smtp_host="smtp.a.com", smtp_port=587, smtp_username="u",
            smtp_password=None,  # don't rotate
            smtp_from_name="Hotel", smtp_from_email="a@b.com", smtp_enabled=True,
        )
        cfg_full = SettingsService.get_smtp_config(db=db_session, include_password=True)
        assert cfg_full["smtp_password"] == "first-password"


# ==========================================
# UNIT: prepare_send validations
# ==========================================

def _enable_smtp(db):
    SettingsService.set_smtp_config(
        db=db,
        smtp_host="smtp.test.com", smtp_port=587, smtp_username="u",
        smtp_password="p", smtp_from_name="Hotel Test",
        smtp_from_email="hotel@test.com", smtp_enabled=True,
    )


class TestPrepareSend:
    def test_smtp_disabled_raises(self, db_session, seed_full, make_reservation):
        res = make_reservation(contact_email="guest@ex.com")
        with pytest.raises(EmailError) as exc:
            EmailService.prepare_send(
                db=db_session, reserva_id=res.id,
                override_email=None, sent_by_user_id=None,
            )
        assert "Configure el correo" in str(exc.value)

    def test_reservation_not_found(self, db_session, seed_full):
        _enable_smtp(db_session)
        with pytest.raises(EmailError) as exc:
            EmailService.prepare_send(
                db=db_session, reserva_id="9999999",
                override_email=None, sent_by_user_id=None,
            )
        assert "no encontrada" in str(exc.value).lower()

    def test_no_email_no_override_raises(self, db_session, seed_full, make_reservation):
        _enable_smtp(db_session)
        res = make_reservation()  # no contact_email
        with pytest.raises(EmailError) as exc:
            EmailService.prepare_send(
                db=db_session, reserva_id=res.id,
                override_email=None, sent_by_user_id=None,
            )
        assert "no tiene email" in str(exc.value).lower()

    def test_override_persists_when_guest_had_none(self, db_session, seed_full, make_reservation):
        _enable_smtp(db_session)
        res = make_reservation()
        log_id = EmailService.prepare_send(
            db=db_session, reserva_id=res.id,
            override_email="new@email.com", sent_by_user_id=None,
        )
        assert log_id > 0
        db_session.refresh(res)
        assert res.contact_email == "new@email.com"
        log = db_session.query(EmailLog).filter(EmailLog.id == log_id).first()
        assert log.status == "PENDIENTE"
        assert log.recipient_email == "new@email.com"

    def test_override_does_not_overwrite_existing_email(self, db_session, seed_full, make_reservation):
        _enable_smtp(db_session)
        res = make_reservation(contact_email="original@ex.com")
        log_id = EmailService.prepare_send(
            db=db_session, reserva_id=res.id,
            override_email="temp@ex.com", sent_by_user_id=None,
        )
        db_session.refresh(res)
        # Guest email stays; log goes to override for this send only
        assert res.contact_email == "original@ex.com"
        log = db_session.query(EmailLog).filter(EmailLog.id == log_id).first()
        assert log.recipient_email == "temp@ex.com"

    def test_rate_limit_blocks_fourth(self, db_session, seed_full, make_reservation):
        _enable_smtp(db_session)
        res = make_reservation(contact_email="g@ex.com")
        now = datetime.now()
        # Seed 3 ENVIADO within the hour
        for _ in range(3):
            db_session.add(EmailLog(
                reserva_id=res.id, recipient_email="g@ex.com", subject="s",
                status="ENVIADO", sent_at=now - timedelta(minutes=10),
            ))
        db_session.commit()

        with pytest.raises(EmailError) as exc:
            EmailService.prepare_send(
                db=db_session, reserva_id=res.id,
                override_email=None, sent_by_user_id=None,
                now=now,
            )
        assert "Límite de reenvíos" in str(exc.value)


# ==========================================
# INTEGRATION: send_async with mocked SMTP
# ==========================================

def _seed_min_pdf_source(db, make_reservation, email="g@ex.com"):
    _enable_smtp(db)
    return make_reservation(contact_email=email, guest_name="Test Guest")


class TestSendAsync:
    @patch("services.email_service.smtplib.SMTP")
    @patch("services.document_service.DocumentService.generate_reservation_pdf")
    def test_success_marks_enviado(self, mock_pdf, mock_smtp_cls, db_session, seed_full, make_reservation, tmp_path):
        res = _seed_min_pdf_source(db_session, make_reservation)

        # PDF path points at an existing (tiny) temp file
        fake_pdf = tmp_path / "reserva.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n%fake")
        mock_pdf.return_value = str(fake_pdf)

        smtp_instance = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = smtp_instance

        log_id = EmailService.prepare_send(
            db=db_session, reserva_id=res.id,
            override_email=None, sent_by_user_id=None,
        )
        EmailService.send_async(log_id)

        db_session.expire_all()
        log = db_session.query(EmailLog).filter(EmailLog.id == log_id).first()
        assert log.status == "ENVIADO"
        assert log.error_message is None
        assert log.sent_at is not None
        # SMTP was called: starttls + login + send_message
        assert smtp_instance.send_message.called
        # PDF was regenerated (always-regen policy)
        assert mock_pdf.called

    @patch("services.email_service.smtplib.SMTP")
    @patch("services.document_service.DocumentService.generate_reservation_pdf")
    def test_smtp_failure_marks_fallido(self, mock_pdf, mock_smtp_cls, db_session, seed_full, make_reservation, tmp_path):
        import smtplib as _smtp
        res = _seed_min_pdf_source(db_session, make_reservation)
        fake_pdf = tmp_path / "r.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n%fake")
        mock_pdf.return_value = str(fake_pdf)

        smtp_instance = MagicMock()
        smtp_instance.send_message.side_effect = _smtp.SMTPAuthenticationError(535, b"auth rejected")
        mock_smtp_cls.return_value.__enter__.return_value = smtp_instance

        log_id = EmailService.prepare_send(
            db=db_session, reserva_id=res.id,
            override_email=None, sent_by_user_id=None,
        )
        EmailService.send_async(log_id)

        db_session.expire_all()
        log = db_session.query(EmailLog).filter(EmailLog.id == log_id).first()
        assert log.status == "FALLIDO"
        assert log.error_message
        assert "auth" in log.error_message.lower() or "535" in log.error_message


# ==========================================
# INTEGRATION: /email endpoints
# ==========================================

class TestEmailEndpoints:
    def test_send_without_smtp_config_returns_400(
        self, client, seed_full, make_reservation, auth_headers_admin
    ):
        res = make_reservation(contact_email="g@ex.com")
        r = client.post(
            f"/api/v1/email/reserva/{res.id}/enviar",
            json={}, headers=auth_headers_admin,
        )
        assert r.status_code == 400
        assert "Configure el correo" in r.json().get("detail", "")

    def test_send_without_guest_email_without_body_returns_400(
        self, client, seed_full, db_session, make_reservation, auth_headers_admin
    ):
        _enable_smtp(db_session)
        res = make_reservation()  # no contact_email
        r = client.post(
            f"/api/v1/email/reserva/{res.id}/enviar",
            json={}, headers=auth_headers_admin,
        )
        assert r.status_code == 400
        assert "no tiene email" in r.json().get("detail", "").lower()

    def test_send_with_override_202_and_persists_email(
        self, client, seed_full, db_session, make_reservation, auth_headers_admin
    ):
        _enable_smtp(db_session)
        res = make_reservation()

        with patch("services.email_service.EmailService.send_async"):
            r = client.post(
                f"/api/v1/email/reserva/{res.id}/enviar",
                json={"email": "new@ex.com"}, headers=auth_headers_admin,
            )
        assert r.status_code == 202, r.text
        db_session.expire_all()
        res_fresh = db_session.query(Reservation).filter(Reservation.id == res.id).first()
        assert res_fresh.contact_email == "new@ex.com"

    def test_historial_returns_desc_order(
        self, client, seed_full, db_session, make_reservation, auth_headers_recep
    ):
        res = make_reservation()
        # Seed 3 logs with different timestamps
        base = datetime.now()
        for i in range(3):
            db_session.add(EmailLog(
                reserva_id=res.id, recipient_email=f"x{i}@ex.com",
                subject=f"s{i}", status="ENVIADO",
                sent_at=base - timedelta(minutes=i * 5),
                created_at=base - timedelta(minutes=i * 5),
            ))
        db_session.commit()

        r = client.get(
            f"/api/v1/email/reserva/{res.id}/historial",
            headers=auth_headers_recep,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 3
        assert data[0]["recipient_email"] == "x0@ex.com"  # most recent

    def test_historial_requires_auth(
        self, client, seed_full, make_reservation
    ):
        res = make_reservation()
        r = client.get(f"/api/v1/email/reserva/{res.id}/historial")
        assert r.status_code == 401

    def test_rate_limit_429_on_fourth_send(
        self, client, seed_full, db_session, make_reservation, auth_headers_admin
    ):
        _enable_smtp(db_session)
        res = make_reservation(contact_email="g@ex.com")
        now = datetime.now()
        for _ in range(3):
            db_session.add(EmailLog(
                reserva_id=res.id, recipient_email="g@ex.com", subject="s",
                status="ENVIADO", sent_at=now - timedelta(minutes=10),
            ))
        db_session.commit()

        with patch("services.email_service.EmailService.send_async"):
            r = client.post(
                f"/api/v1/email/reserva/{res.id}/enviar",
                json={}, headers=auth_headers_admin,
            )
        assert r.status_code == 429
        assert "Límite" in r.json().get("detail", "")


# ==========================================
# INTEGRATION: /settings/email endpoints
# ==========================================

class TestSettingsEmailEndpoints:
    def test_get_defaults(self, client, seed_full, auth_headers_admin):
        r = client.get("/api/v1/settings/email", headers=auth_headers_admin)
        assert r.status_code == 200
        data = r.json()
        assert data["smtp_enabled"] is False
        assert data["smtp_password_set"] is False
        # Public GET never returns the password
        assert "smtp_password" not in data

    def test_put_requires_admin(self, client, seed_full, auth_headers_recep):
        r = client.put(
            "/api/v1/settings/email",
            json={
                "smtp_host": "smtp.a.com", "smtp_port": 587, "smtp_username": "u",
                "smtp_password": "p", "smtp_from_name": "H", "smtp_from_email": "a@b.com",
                "smtp_enabled": True,
            },
            headers=auth_headers_recep,
        )
        assert r.status_code == 403

    def test_put_save_and_get(self, client, seed_full, auth_headers_admin):
        r = client.put(
            "/api/v1/settings/email",
            json={
                "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_username": "hotel@ex.com",
                "smtp_password": "supersecret",
                "smtp_from_name": "Hotel Munich", "smtp_from_email": "hotel@ex.com",
                "smtp_enabled": True,
            },
            headers=auth_headers_admin,
        )
        assert r.status_code == 200, r.text
        r2 = client.get("/api/v1/settings/email", headers=auth_headers_admin)
        assert r2.status_code == 200
        data = r2.json()
        assert data["smtp_host"] == "smtp.gmail.com"
        assert data["smtp_port"] == 587
        assert data["smtp_enabled"] is True
        assert data["smtp_password_set"] is True

    def test_test_endpoint_requires_admin(self, client, seed_full, auth_headers_recep):
        r = client.post(
            "/api/v1/settings/email/test",
            json={"email": "me@ex.com"},
            headers=auth_headers_recep,
        )
        assert r.status_code == 403

    def test_test_endpoint_returns_false_if_disabled(self, client, seed_full, auth_headers_admin):
        r = client.post(
            "/api/v1/settings/email/test",
            json={"email": "me@ex.com"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        assert r.json()["success"] is False
