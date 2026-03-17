"""
Hotel PMS API - Document Endpoints
======================================
Download and list auto-generated PDF documents (reservations, clients).
"""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List

from api.deps import get_db, get_current_user
from logging_config import get_logger

logger = get_logger(__name__)

from services import DocumentService

router = APIRouter()


@router.get(
    "/reservations/{reservation_id}",
    summary="Download Reservation PDF",
    description="Download or generate a reservation confirmation PDF. Requires authentication."
)
def download_reservation_pdf(
    reservation_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Download reservation PDF. Generates on-demand if not found."""
    # Try existing file first
    path = DocumentService.get_reservation_pdf_path(reservation_id)

    if not path or not os.path.exists(path):
        # Generate on-demand
        path = DocumentService.generate_reservation_pdf(db, reservation_id)

    if not path or not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se pudo generar el PDF para la reserva {reservation_id}"
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(path),
    )


@router.get(
    "/clients/{checkin_id}",
    summary="Download Client PDF",
    description="Download or generate a client registration PDF. Requires authentication."
)
def download_client_pdf(
    checkin_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Download client PDF. Generates on-demand if not found."""
    path = DocumentService.generate_client_pdf(db, checkin_id)

    if not path or not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se pudo generar el PDF para el check-in {checkin_id}"
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(path),
    )


@router.get(
    "/download/{folder}/{filename}",
    summary="Download Document by Filename",
    description="Download a PDF by folder and filename. Requires authentication."
)
def download_by_filename(
    folder: str,
    filename: str,
    current_user=Depends(get_current_user)
):
    """Download a PDF directly by folder and filename."""
    if folder not in ("Reservas", "Clientes"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Carpeta debe ser 'Reservas' o 'Clientes'"
        )

    import services.document_service as _ds
    target_dir = _ds.RESERVAS_DIR if folder == "Reservas" else _ds.CLIENTES_DIR
    filepath = os.path.join(target_dir, filename)

    # Security: prevent path traversal
    if not os.path.abspath(filepath).startswith(os.path.abspath(target_dir)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ruta invalida")

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento no encontrado: {filename}"
        )

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )


@router.get(
    "/list/{folder}",
    response_model=List[dict],
    summary="List Documents",
    description="List all PDF documents in a folder (Reservas or Clientes). Requires authentication."
)
def list_documents(
    folder: str = "Reservas",
    current_user=Depends(get_current_user)
):
    """List available documents in a folder."""
    if folder not in ("Reservas", "Clientes"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Carpeta debe ser 'Reservas' o 'Clientes'"
        )
    return DocumentService.list_documents(folder)
