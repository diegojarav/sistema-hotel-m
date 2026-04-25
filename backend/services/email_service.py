"""
EmailService — Reservation confirmation email sending (v1.8.0 — Phase 5)
========================================================================

Sends the reservation confirmation PDF to the guest's email, with:
  - Configurable SMTP (host/port/username/password/from_name/from_email) stored encrypted
  - Configurable body template with {nombre_huesped} / {nombre_hotel} placeholders
  - Per-reservation rate limit: max 3 ENVIADO/hour (counts only successful sends)
  - PDF always regenerated before send via DocumentService
  - Full audit trail in email_log table
  - Async send via FastAPI BackgroundTasks (non-blocking response)
  - Discord alert on infra failures (via logger.error)
"""

from __future__ import annotations

import os
import smtplib
import socket
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class EmailError(Exception):
    """Raised for email-related business rule violations and infrastructure failures."""
    pass


# Rate limit window: 3 successful sends per hour per reservation.
RATE_LIMIT_COUNT = 3
RATE_LIMIT_WINDOW = timedelta(hours=1)


def _humanize_smtp_error(exc: BaseException) -> str:
    """Map low-level SMTP / socket exceptions to a clean Spanish message + recovery path.

    The verbatim exception (with stack frames + raw bytes from the SMTP server)
    is logged separately by the caller. Only this user-facing message reaches
    the UI / email_log.error_message.

    Follows ui-ux-pro-max rule `error-clarity`: every message states the cause
    AND how to fix it. Receptionists are not expected to read SMTP RFC codes.
    """
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            "Error de autenticación con el servidor de correo. "
            "Revisá usuario y contraseña en Configuración → Configuración de Correo."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return (
            "El servidor rechazó la dirección del destinatario. "
            "Verificá que el email del huésped sea correcto."
        )
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            "El servidor rechazó la dirección del remitente. "
            "Revisá el email del remitente en Configuración → Configuración de Correo."
        )
    if isinstance(exc, smtplib.SMTPConnectError):
        return (
            "No se pudo conectar al servidor de correo. "
            "Verificá host y puerto en Configuración → Configuración de Correo."
        )
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "El servidor de correo cortó la conexión. "
            "Probá nuevamente en unos minutos."
        )
    if isinstance(exc, smtplib.SMTPDataError):
        return (
            "El servidor rechazó el mensaje. "
            "Es posible que el adjunto sea demasiado grande o el contenido no sea aceptado."
        )
    if isinstance(exc, ssl.SSLError):
        return (
            "Error TLS/SSL al conectar con el servidor de correo. "
            "Probá con otro puerto (587 con STARTTLS o 465 con SSL)."
        )
    if isinstance(exc, socket.gaierror):
        return (
            "No se pudo resolver el servidor de correo. "
            "Verificá el host SMTP en Configuración → Configuración de Correo."
        )
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (
            "El servidor de correo tardó demasiado en responder. "
            "Probá nuevamente o verificá la conexión a internet del servidor."
        )
    if isinstance(exc, smtplib.SMTPException):
        return (
            "No se pudo enviar el correo. "
            "Verificá la configuración SMTP del hotel."
        )
    return (
        "Error inesperado al enviar el correo. "
        "Si persiste, contactá al administrador."
    )


class EmailService:
    """Service layer for reservation email sending + historial queries."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    @with_db
    def get_email_log(db: Session, reserva_id: str, limit: int = 100) -> list:
        """Return email_log rows for a reserva, newest first."""
        from database import EmailLog
        rows = (
            db.query(EmailLog)
              .filter(EmailLog.reserva_id == reserva_id)
              .order_by(desc(EmailLog.created_at))
              .limit(limit)
              .all()
        )
        return rows

    @staticmethod
    @with_db
    def prepare_send(
        db: Session,
        reserva_id: str,
        override_email: Optional[str],
        sent_by_user_id: Optional[int],   # v1.10.0 Phase 1 Fix #2: was Optional[str]
        now: Optional[datetime] = None,
    ) -> int:
        """
        Synchronous part of the send pipeline. Validates config+rate limit, resolves
        recipient, persists override to reservation if guest had none, and inserts the
        PENDIENTE email_log row. Returns the inserted email_log.id so the caller can
        schedule a BackgroundTask with _send_async(log_id).

        Raises EmailError on any validation failure — endpoint maps to 4xx.
        """
        from database import EmailLog, Reservation
        from services.settings_service import SettingsService

        now = now or datetime.now()

        # 1) SMTP must be enabled with all required fields
        cfg = SettingsService.get_smtp_config(db=db, include_password=True)
        if not cfg["smtp_enabled"]:
            raise EmailError(
                "Configure el correo del hotel en Configuración antes de enviar emails."
            )
        EmailService._require_complete_config(cfg)

        # 2) Resolve reservation
        reservation = db.query(Reservation).filter(Reservation.id == reserva_id).first()
        if not reservation:
            raise EmailError(f"Reserva no encontrada: {reserva_id}")

        # 3) Resolve recipient
        recipient = (override_email or "").strip() or None
        if recipient is None:
            recipient = (reservation.contact_email or "").strip() or None
        if recipient is None:
            raise EmailError(
                "El huésped no tiene email registrado. Ingrese un email para continuar."
            )

        # Persist override to reservation ONLY if guest previously had none.
        # If guest already had a different email, we respect it (override is one-shot).
        if override_email and not (reservation.contact_email or "").strip():
            reservation.contact_email = override_email.strip()

        # 4) Rate limit: count ENVIADO in the last hour
        if EmailService._check_rate_limit(db, reserva_id, now=now) >= RATE_LIMIT_COUNT:
            raise EmailError(
                f"Límite de reenvíos alcanzado: máximo {RATE_LIMIT_COUNT} por hora por reserva. "
                "Intentá de nuevo más tarde."
            )

        # 5) Insert PENDIENTE log row
        subject = EmailService._build_subject(reservation, cfg)
        log_row = EmailLog(
            reserva_id=reserva_id,
            recipient_email=recipient,
            subject=subject,
            status="PENDIENTE",
            sent_by=sent_by_user_id,
            created_at=now,
        )
        db.add(log_row)
        db.commit()
        db.refresh(log_row)
        return log_row.id

    @staticmethod
    def send_async(log_id: int) -> None:
        """
        Background-task entrypoint. Opens a fresh DB session (do NOT reuse the endpoint's
        session — it is already closed by the time BackgroundTasks runs). Guarantees the
        PENDIENTE row transitions to either ENVIADO or FALLIDO even on crash.
        """
        from database import EmailLog, Reservation
        from services._base import SessionLocal
        from services.settings_service import SettingsService
        from services.document_service import DocumentService

        db = SessionLocal()
        try:
            log_row = db.query(EmailLog).filter(EmailLog.id == log_id).first()
            if not log_row:
                logger.error(f"EmailLog id={log_id} not found in send_async")
                return

            try:
                cfg = SettingsService.get_smtp_config(db=db, include_password=True)
                EmailService._require_complete_config(cfg)

                reservation = db.query(Reservation).filter(
                    Reservation.id == log_row.reserva_id
                ).first()
                if not reservation:
                    raise EmailError(f"Reserva desapareció: {log_row.reserva_id}")

                # Always regenerate PDF before sending (avoids stale data).
                pdf_path = DocumentService.generate_reservation_pdf(
                    db=db, reservation_id=reservation.id
                )
                if not pdf_path or not os.path.exists(pdf_path):
                    raise EmailError(
                        f"No se pudo generar el PDF de la reserva {reservation.id}"
                    )

                # Build and send MIME
                msg = EmailService._build_mime(
                    cfg=cfg,
                    recipient=log_row.recipient_email,
                    subject=log_row.subject,
                    reservation=reservation,
                    pdf_path=pdf_path,
                )
                EmailService._send_smtp(cfg, msg, log_row.recipient_email)

                log_row.status = "ENVIADO"
                log_row.sent_at = datetime.now()
                log_row.error_message = None
                db.commit()
                logger.info(
                    f"Email sent: reserva={log_row.reserva_id} to={log_row.recipient_email}"
                )

            except Exception as e:
                # Humanize the SMTP/socket exception for the operator. The raw
                # exception is logged below for diagnostics, but never reaches
                # the UI (no leaking of "(534, b'5.7.9 ...')" strings).
                user_msg = _humanize_smtp_error(e)
                log_row.status = "FALLIDO"
                log_row.error_message = user_msg
                log_row.sent_at = datetime.now()
                db.commit()
                logger.error(
                    f"Email send FAILED: reserva={log_row.reserva_id} "
                    f"raw={str(e)[:300]} user_msg={user_msg}"
                )
        except BaseException as e:
            # Last-resort safety net: never leave a PENDIENTE row without status
            logger.error(f"EmailService.send_async top-level crash: {e}")
            try:
                row = db.query(EmailLog).filter(EmailLog.id == log_id).first()
                if row and row.status == "PENDIENTE":
                    row.status = "FALLIDO"
                    row.error_message = f"Proceso abortado: {str(e)[:400]}"
                    row.sent_at = datetime.now()
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    @staticmethod
    def send_test_email(to_email: str) -> dict:
        """
        Synchronously send a short test email using current SMTP config.
        Returns {"success": bool, "message": str}. Does NOT write to email_log.
        """
        from services.settings_service import SettingsService
        try:
            cfg = SettingsService.get_smtp_config(include_password=True)
            if not cfg["smtp_enabled"]:
                return {"success": False, "message": "SMTP está deshabilitado. Activalo y guardá antes de probar."}
            EmailService._require_complete_config(cfg)

            msg = EmailMessage()
            msg["From"] = EmailService._format_from(cfg)
            msg["To"] = to_email
            msg["Subject"] = f"Prueba de configuración SMTP — {cfg.get('smtp_from_name') or 'Hotel'}"
            msg.set_content(
                "Este es un email de prueba enviado desde el PMS del hotel.\n"
                "Si lo recibiste, la configuración SMTP está correcta.\n",
                charset="utf-8",
            )
            EmailService._send_smtp(cfg, msg, to_email)
            return {"success": True, "message": f"Email de prueba enviado a {to_email}."}
        except EmailError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            user_msg = _humanize_smtp_error(e)
            logger.error(f"SMTP test failed: raw={str(e)[:300]} user_msg={user_msg}")
            return {"success": False, "message": user_msg}

    # ------------------------------------------------------------------
    # Internal helpers (exposed for testability)
    # ------------------------------------------------------------------
    @staticmethod
    def _check_rate_limit(db: Session, reserva_id: str, now: Optional[datetime] = None) -> int:
        """Return count of ENVIADO rows for this reserva within the rate-limit window."""
        from database import EmailLog
        now = now or datetime.now()
        cutoff = now - RATE_LIMIT_WINDOW
        count = (
            db.query(EmailLog)
              .filter(
                  EmailLog.reserva_id == reserva_id,
                  EmailLog.status == "ENVIADO",
                  EmailLog.sent_at.isnot(None),
                  EmailLog.sent_at > cutoff,
              )
              .count()
        )
        return count

    @staticmethod
    def _render_body(template: str, nombre_huesped: str, nombre_hotel: str) -> str:
        """Simple placeholder substitution. Unknown placeholders are kept as-is (no crash)."""
        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"
        values = _SafeDict(
            nombre_huesped=nombre_huesped or "",
            nombre_hotel=nombre_hotel or "",
        )
        try:
            return template.format_map(values)
        except Exception:
            # Malformed template (e.g. unbalanced braces) — return as-is so send doesn't block.
            return template

    @staticmethod
    def _build_subject(reservation, cfg: dict) -> str:
        hotel_name = cfg.get("smtp_from_name") or "Hotel"
        fecha = reservation.check_in_date.strftime("%d/%m/%Y") if reservation.check_in_date else ""
        return f"Confirmación de Reserva — {hotel_name} — Check-in: {fecha}"

    @staticmethod
    def _build_mime(cfg: dict, recipient: str, subject: str, reservation, pdf_path: str) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = EmailService._format_from(cfg)
        msg["To"] = recipient
        msg["Subject"] = subject

        template = cfg.get("email_body_template") or ""
        from services.settings_service import SettingsService
        if not template:
            template = SettingsService.DEFAULT_EMAIL_BODY_TEMPLATE

        body = EmailService._render_body(
            template=template,
            nombre_huesped=reservation.guest_name or "",
            nombre_hotel=cfg.get("smtp_from_name") or "Hotel",
        )
        msg.set_content(body, charset="utf-8")

        # Attach PDF
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        filename = os.path.basename(pdf_path)
        msg.add_attachment(
            pdf_bytes, maintype="application", subtype="pdf", filename=filename
        )
        return msg

    @staticmethod
    def _send_smtp(cfg: dict, msg: EmailMessage, recipient: str) -> None:
        """Open an SMTP connection and send. Chooses SSL vs STARTTLS based on port."""
        host = cfg["smtp_host"]
        port = int(cfg["smtp_port"])
        username = cfg["smtp_username"]
        password = cfg.get("smtp_password") or ""

        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as s:
                if username and password:
                    s.login(username, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                try:
                    s.starttls(context=context)
                    s.ehlo()
                except smtplib.SMTPNotSupportedError:
                    # Plain SMTP — acceptable for dev/internal servers without TLS
                    pass
                if username and password:
                    s.login(username, password)
                s.send_message(msg)

    @staticmethod
    def _format_from(cfg: dict) -> str:
        name = (cfg.get("smtp_from_name") or "").strip()
        email = (cfg.get("smtp_from_email") or "").strip()
        if name:
            return f"{name} <{email}>"
        return email

    @staticmethod
    def _require_complete_config(cfg: dict) -> None:
        required = ["smtp_host", "smtp_port", "smtp_username", "smtp_from_email"]
        missing = [k for k in required if not cfg.get(k)]
        if missing:
            raise EmailError(
                "Configuración SMTP incompleta. Faltan: " + ", ".join(missing)
            )
        # Password must be set (stored encrypted + decrypted on read)
        if not cfg.get("smtp_password"):
            raise EmailError(
                "Configuración SMTP incompleta. Falta la contraseña del servidor."
            )
