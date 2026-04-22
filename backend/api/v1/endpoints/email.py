"""
Hotel PMS API - Email Endpoints (v1.8.0 — Phase 5)
======================================================

POST /email/reserva/{reserva_id}/enviar    — queue a reservation confirmation email
GET  /email/reserva/{reserva_id}/historial — list past send attempts (DESC by created_at)
"""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_role
from database import User
from logging_config import get_logger
from schemas import EmailLogDTO, SendEmailRequest
from services import EmailError, EmailService

logger = get_logger(__name__)

router = APIRouter()


# Both the spec and the repo use both role aliases (recepcion + recepcionista)
# simultaneously — the seed/test user has role="recepcionista" while some
# prod users have role="recepcion". Include both so we don't break existing data.
EMAIL_ALLOWED_ROLES = ("admin", "recepcion", "recepcionista", "supervisor", "gerencia")


@router.post(
    "/reserva/{reserva_id}/enviar",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a reservation confirmation email",
    description=(
        "Validates SMTP config, guest email (or body override), and the "
        "3/hour rate limit, then schedules the send in the background and "
        "returns 202 immediately. The email_log row starts in PENDIENTE "
        "and transitions to ENVIADO or FALLIDO when the background job "
        "finishes."
    ),
)
def enviar_email_reserva(
    reserva_id: str,
    request: SendEmailRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EMAIL_ALLOWED_ROLES)),
):
    try:
        log_id = EmailService.prepare_send(
            db=db,
            reserva_id=reserva_id,
            override_email=request.email,
            sent_by_user_id=current_user.id,
        )
    except EmailError as e:
        msg = str(e)
        if "Límite de reenvíos" in msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=msg
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=msg
        )
    except Exception as e:
        logger.error(f"prepare_send crashed for reserva={reserva_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al encolar el envío del correo.",
        )

    background_tasks.add_task(EmailService.send_async, log_id)
    return {"email_log_id": log_id, "status": "PENDIENTE"}


@router.get(
    "/reserva/{reserva_id}/historial",
    response_model=List[EmailLogDTO],
    summary="List email history for a reservation",
    description="Returns rows from email_log for the given reservation, newest first.",
)
def historial_email_reserva(
    reserva_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EMAIL_ALLOWED_ROLES)),
):
    rows = EmailService.get_email_log(db=db, reserva_id=reserva_id)
    return [
        EmailLogDTO(
            id=r.id,
            reserva_id=r.reserva_id,
            recipient_email=r.recipient_email,
            subject=r.subject,
            status=r.status,
            error_message=r.error_message,
            sent_at=r.sent_at,
            sent_by=r.sent_by,
            created_at=r.created_at,
        )
        for r in rows
    ]
