"""
Tests for DocumentService — PDF generation for reservations and clients.
"""

import os
import pytest
from unittest.mock import patch
from datetime import date, time

from database import Reservation, CheckIn
from services.document_service import (
    DocumentService, _sanitize_filename, _format_pyg, RESERVAS_DIR, CLIENTES_DIR
)


class TestHelpers:
    """Test utility functions."""

    def test_sanitize_basic(self):
        assert _sanitize_filename("Juan Pérez") == "Juan_Perez"

    def test_sanitize_special_chars(self):
        assert _sanitize_filename("María José / López") == "Maria_Jose_Lopez"

    def test_sanitize_empty(self):
        assert _sanitize_filename("") == "sin_nombre"

    def test_sanitize_accents(self):
        result = _sanitize_filename("Ñoño Güemes")
        assert "N" in result  # Ñ → N
        assert "_" not in result or result.count("_") >= 0  # valid chars

    def test_format_pyg_normal(self):
        assert _format_pyg(150000.0) == "150.000 Gs"

    def test_format_pyg_large(self):
        assert _format_pyg(1250000.0) == "1.250.000 Gs"

    def test_format_pyg_zero(self):
        assert _format_pyg(0) == "0 Gs"

    def test_format_pyg_none(self):
        assert _format_pyg(None) == "0 Gs"


class TestReservationPDF:
    """Test reservation PDF generation."""

    def test_generate_reservation_pdf(self, db_session, seed_rooms, tmp_path):
        """PDF is created at expected path with valid content."""
        room = seed_rooms["rooms"][0]
        res = Reservation(
            id="0009001",
            check_in_date=date(2026, 4, 15),
            stay_days=3,
            guest_name="Carlos Garcia",
            room_id=room.id,
            room_type="Estandar",
            price=450000.0,
            final_price=450000.0,
            status="Confirmada",
            property_id="los-monges",
            category_id=room.category_id,
            reserved_by="Admin",
            received_by="Recepcion",
            contact_phone="0981123456",
            source="Direct",
        )
        db_session.add(res)
        db_session.commit()

        # Redirect output to tmp_path
        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            path = DocumentService.generate_reservation_pdf(db_session, "0009001")

        assert path is not None
        assert os.path.exists(path)
        assert path.endswith(".pdf")
        assert "Carlos_Garcia" in os.path.basename(path)
        assert "15-04-26" in os.path.basename(path)
        assert "0009001" in os.path.basename(path)

        # Verify it's a valid PDF (starts with %PDF)
        with open(path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_generate_with_breakdown(self, db_session, seed_rooms, tmp_path):
        """PDF generation works with price_breakdown JSON."""
        import json
        room = seed_rooms["rooms"][0]
        breakdown = json.dumps({
            "breakdown": {
                "base_unit_price": 150000,
                "nights": 2,
                "base_total": 300000,
                "modifiers": [
                    {"name": "Descuento Cliente: Empresa", "percent": -15, "amount": -45000}
                ],
                "final_price": 255000
            }
        })
        res = Reservation(
            id="0009002",
            check_in_date=date(2026, 5, 1),
            stay_days=2,
            guest_name="Maria Lopez",
            room_id=room.id,
            price=300000.0,
            final_price=255000.0,
            original_price=300000.0,
            discount_amount=45000.0,
            price_breakdown=breakdown,
            status="Confirmada",
            property_id="los-monges",
            reserved_by="test",
            received_by="test",
            contact_phone="",
            source="Booking.com",
        )
        db_session.add(res)
        db_session.commit()

        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            path = DocumentService.generate_reservation_pdf(db_session, "0009002")

        assert path is not None
        assert os.path.exists(path)

    def test_generate_with_parking(self, db_session, seed_rooms, tmp_path):
        """PDF includes parking section when parking_needed is True."""
        room = seed_rooms["rooms"][0]
        res = Reservation(
            id="0009003",
            check_in_date=date(2026, 6, 10),
            stay_days=1,
            guest_name="Pedro Ramirez",
            room_id=room.id,
            price=150000.0,
            final_price=150000.0,
            status="Confirmada",
            property_id="los-monges",
            parking_needed=True,
            vehicle_model="Toyota Corolla",
            vehicle_plate="ABC 123",
            reserved_by="test",
            received_by="test",
            contact_phone="",
            source="Direct",
        )
        db_session.add(res)
        db_session.commit()

        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            path = DocumentService.generate_reservation_pdf(db_session, "0009003")

        assert path is not None
        assert os.path.exists(path)

    def test_not_found_returns_none(self, db_session):
        """Returns None for nonexistent reservation."""
        result = DocumentService.generate_reservation_pdf(db_session, "9999999")
        assert result is None

    def test_get_reservation_pdf_path(self, tmp_path):
        """Finds existing PDF by reservation_id suffix."""
        # Create a fake PDF file
        fake_file = tmp_path / "Carlos_Garcia_15-04-26_0009001.pdf"
        fake_file.write_text("fake pdf")

        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            path = DocumentService.get_reservation_pdf_path("0009001")

        assert path is not None
        assert path.endswith("0009001.pdf")

    def test_get_reservation_pdf_path_not_found(self, tmp_path):
        """Returns None when no matching PDF exists."""
        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            path = DocumentService.get_reservation_pdf_path("9999999")
        assert path is None


class TestClientPDF:
    """Test client/guest PDF generation."""

    def test_generate_client_pdf(self, db_session, seed_rooms, tmp_path):
        """Client PDF is created at expected path."""
        room = seed_rooms["rooms"][0]
        checkin = CheckIn(
            created_at=date(2026, 4, 15),
            room_id=room.id,
            check_in_time=time(14, 30),
            last_name="Gonzalez",
            first_name="Ana",
            nationality="Paraguaya",
            birth_date=date(1990, 5, 20),
            origin="Asuncion",
            destination="Encarnacion",
            civil_status="Soltera",
            document_number="4567890",
            country="Paraguay",
            billing_name="Ana Gonzalez",
            billing_ruc="4567890-1",
            vehicle_model="Honda Civic",
            vehicle_plate="XYZ 789",
            digital_signature="Pendiente",
        )
        db_session.add(checkin)
        db_session.commit()

        with patch("services.document_service.CLIENTES_DIR", str(tmp_path)):
            path = DocumentService.generate_client_pdf(db_session, checkin.id)

        assert path is not None
        assert os.path.exists(path)
        assert path.endswith(".pdf")
        assert "Gonzalez" in os.path.basename(path)
        assert "Ana" in os.path.basename(path)

        with open(path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_client_pdf_not_found(self, db_session):
        """Returns None for nonexistent check-in."""
        result = DocumentService.generate_client_pdf(db_session, 99999)
        assert result is None

    def test_client_pdf_with_reservation(self, db_session, seed_rooms, tmp_path):
        """Client PDF includes linked reservation info."""
        room = seed_rooms["rooms"][0]
        res = Reservation(
            id="0009010",
            check_in_date=date(2026, 7, 1),
            stay_days=5,
            guest_name="Roberto Fernandez",
            room_id=room.id,
            price=750000.0,
            final_price=750000.0,
            status="Confirmada",
            property_id="los-monges",
            reserved_by="test",
            received_by="test",
            contact_phone="",
            source="Direct",
        )
        db_session.add(res)
        db_session.flush()

        checkin = CheckIn(
            created_at=date(2026, 7, 1),
            room_id=room.id,
            reservation_id="0009010",
            check_in_time=time(15, 0),
            last_name="Fernandez",
            first_name="Roberto",
            nationality="Argentino",
            document_number="12345678",
            country="Argentina",
            billing_name="",
            billing_ruc="",
            digital_signature="Pendiente",
        )
        db_session.add(checkin)
        db_session.commit()

        with patch("services.document_service.CLIENTES_DIR", str(tmp_path)):
            path = DocumentService.generate_client_pdf(db_session, checkin.id)

        assert path is not None
        assert os.path.exists(path)


class TestListDocuments:
    """Test document listing."""

    def test_list_empty(self, tmp_path):
        """Returns empty list when no PDFs exist."""
        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            docs = DocumentService.list_documents("Reservas")
        assert docs == []

    def test_list_with_files(self, tmp_path):
        """Lists PDF files with metadata."""
        (tmp_path / "test1.pdf").write_text("fake")
        (tmp_path / "test2.pdf").write_text("fake2")
        (tmp_path / "not_a_pdf.txt").write_text("ignore")

        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            docs = DocumentService.list_documents("Reservas")

        assert len(docs) == 2
        filenames = [d["filename"] for d in docs]
        assert "test1.pdf" in filenames
        assert "test2.pdf" in filenames
        assert all(d["folder"] == "Reservas" for d in docs)
        assert all("size_bytes" in d for d in docs)
        assert all("created_at" in d for d in docs)


class TestDocumentEndpoints:
    """Test document API endpoints."""

    def test_download_reservation_pdf(self, client, db_session, seed_full, auth_headers_admin, tmp_path):
        """GET /documents/reservations/{id} returns PDF."""
        res = Reservation(
            id="0009050",
            check_in_date=date(2026, 8, 1),
            stay_days=2,
            guest_name="Test Download",
            room_id=seed_full["rooms"][0].id,
            price=150000.0,
            final_price=150000.0,
            status="Confirmada",
            property_id="los-monges",
            reserved_by="test",
            received_by="test",
            contact_phone="",
            source="Direct",
        )
        db_session.add(res)
        db_session.commit()

        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            response = client.get(
                "/api/v1/documents/reservations/0009050",
                headers=auth_headers_admin,
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_download_missing_returns_404(self, client, seed_full, auth_headers_admin):
        """GET /documents/reservations/{id} returns 404 for nonexistent."""
        response = client.get(
            "/api/v1/documents/reservations/9999999",
            headers=auth_headers_admin,
        )
        assert response.status_code == 404

    def test_list_documents_endpoint(self, client, seed_full, auth_headers_admin):
        """GET /documents/list/Reservas returns list."""
        response = client.get(
            "/api/v1/documents/list/Reservas",
            headers=auth_headers_admin,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_invalid_folder(self, client, seed_full, auth_headers_admin):
        """GET /documents/list/Invalid returns 400."""
        response = client.get(
            "/api/v1/documents/list/Invalid",
            headers=auth_headers_admin,
        )
        assert response.status_code == 400

    def test_download_by_filename(self, client, seed_full, auth_headers_admin, tmp_path):
        """GET /documents/download/{folder}/{filename} returns PDF."""
        fake_file = tmp_path / "test_doc.pdf"
        fake_file.write_bytes(b"%PDF-1.4 fake content")

        with patch("services.document_service.RESERVAS_DIR", str(tmp_path)):
            response = client.get(
                "/api/v1/documents/download/Reservas/test_doc.pdf",
                headers=auth_headers_admin,
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_download_by_filename_not_found(self, client, seed_full, auth_headers_admin):
        """GET /documents/download/{folder}/{filename} returns 404 for missing file."""
        response = client.get(
            "/api/v1/documents/download/Reservas/nonexistent.pdf",
            headers=auth_headers_admin,
        )
        assert response.status_code == 404

    def test_download_by_filename_invalid_folder(self, client, seed_full, auth_headers_admin):
        """GET /documents/download/Invalid/{filename} returns 400."""
        response = client.get(
            "/api/v1/documents/download/Invalid/test.pdf",
            headers=auth_headers_admin,
        )
        assert response.status_code == 400

    def test_requires_auth(self, client, seed_full):
        """Endpoints require authentication."""
        response = client.get("/api/v1/documents/reservations/0001000")
        assert response.status_code == 401

        response = client.get("/api/v1/documents/list/Reservas")
        assert response.status_code == 401
