"""
Document Generation Service
===============================
Generates printable PDF documents for reservations and clients.
Files are saved to backend/hotel/Reservas/ and backend/hotel/Clientes/.
"""

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from typing import List, Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy.orm import Session

from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)

# Directories
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOTEL_DIR = os.path.join(_BACKEND_DIR, "hotel")
RESERVAS_DIR = os.path.join(HOTEL_DIR, "Reservas")
CLIENTES_DIR = os.path.join(HOTEL_DIR, "Clientes")
CUENTAS_DIR = os.path.join(HOTEL_DIR, "Cuentas")  # v1.6.0 — Phase 3 folios


def _ensure_dirs():
    """Create hotel/Reservas/, hotel/Clientes/, hotel/Cuentas/ if missing."""
    os.makedirs(RESERVAS_DIR, exist_ok=True)
    os.makedirs(CLIENTES_DIR, exist_ok=True)
    os.makedirs(CUENTAS_DIR, exist_ok=True)


def _sanitize_filename(name: str) -> str:
    """Remove accents and special chars from a string for safe filenames."""
    # Normalize unicode → decompose accented chars → strip combining marks
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Replace spaces/special chars with underscores
    safe = re.sub(r"[^\w\-]", "_", ascii_str)
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "sin_nombre"


def _format_pyg(amount: Optional[float]) -> str:
    """Format a number as PYG currency: '1.250.000 Gs'."""
    if amount is None:
        return "0 Gs"
    formatted = f"{amount:,.0f}".replace(",", ".")
    return f"{formatted} Gs"


class HotelPDF(FPDF):
    """PDF with hotel header/footer."""

    def __init__(self, hotel_name: str = "Mi Hotel", hotel_address: str = "",
                 hotel_phone: str = "", hotel_email: str = ""):
        super().__init__()
        self.hotel_name = hotel_name
        self.hotel_address = hotel_address
        self.hotel_phone = hotel_phone
        self.hotel_email = hotel_email
        # Use built-in Helvetica (supports basic Latin chars well enough)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        # Hotel name
        self.set_font("Helvetica", "B", 18)
        self.cell(0, 10, self.hotel_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        # Contact info line
        parts = []
        if self.hotel_address:
            parts.append(self.hotel_address)
        if self.hotel_phone:
            parts.append(f"Tel: {self.hotel_phone}")
        if self.hotel_email:
            parts.append(self.hotel_email)
        if parts:
            self.set_font("Helvetica", "", 9)
            self.cell(0, 5, " | ".join(parts), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(245, 245, 245)
        self.cell(0, 8, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.ln(2)

    def field_row(self, label: str, value: str, col_width: int = 50):
        self.set_font("Helvetica", "B", 10)
        self.cell(col_width, 7, label + ":", align="L")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


class DocumentService:
    """Service for generating and managing hotel PDF documents."""

    @staticmethod
    def _get_hotel_info(db: Session) -> dict:
        """Get hotel name, address, phone, email from DB."""
        from database import SystemSetting, Property
        hotel_name = "Mi Hotel"
        setting = db.query(SystemSetting).filter(
            SystemSetting.setting_key == "hotel_name"
        ).first()
        if setting and setting.setting_value:
            hotel_name = setting.setting_value

        # Try to get property details
        prop = db.query(Property).filter(Property.id == "los-monges").first()
        address = prop.address if prop and prop.address else ""
        phone = prop.phone if prop and prop.phone else ""
        email = prop.email if prop and prop.email else ""

        return {
            "name": hotel_name,
            "address": address,
            "phone": phone,
            "email": email,
        }

    @staticmethod
    @with_db
    def generate_reservation_pdf(db: Session, reservation_id: str) -> Optional[str]:
        """
        Generate a reservation confirmation PDF.

        Args:
            db: Database session
            reservation_id: Reservation ID (e.g. "0001256")

        Returns:
            File path of generated PDF, or None if reservation not found.
        """
        from database import Reservation, Room, RoomCategory, ClientType

        _ensure_dirs()

        reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if not reservation:
            logger.warning(f"Reservation {reservation_id} not found for PDF generation")
            return None

        # Get related data
        room = db.query(Room).filter(Room.id == reservation.room_id).first()
        category = None
        if room and room.category_id:
            category = db.query(RoomCategory).filter(RoomCategory.id == room.category_id).first()

        client_type = None
        if reservation.client_type_id:
            client_type = db.query(ClientType).filter(
                ClientType.id == reservation.client_type_id
            ).first()

        hotel_info = DocumentService._get_hotel_info(db)

        # Build PDF
        pdf = HotelPDF(
            hotel_name=hotel_info["name"],
            hotel_address=hotel_info["address"],
            hotel_phone=hotel_info["phone"],
            hotel_email=hotel_info["email"],
        )
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Confirmacion de Reserva", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"N. {reservation_id}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(4)

        # --- Guest Info ---
        pdf.section_title("Datos del Huesped")
        pdf.field_row("Nombre", reservation.guest_name or "")
        pdf.field_row("Telefono", reservation.contact_phone or "")
        if getattr(reservation, 'contact_email', None):
            pdf.field_row("Email", reservation.contact_email)
        pdf.field_row("Reservado por", reservation.reserved_by or "")
        pdf.ln(3)

        # --- Stay Info ---
        pdf.section_title("Datos de Estadia")
        check_in_str = reservation.check_in_date.strftime("%d/%m/%Y") if reservation.check_in_date else ""
        check_out_date = None
        if reservation.check_in_date and reservation.stay_days:
            check_out_date = reservation.check_in_date + timedelta(days=reservation.stay_days)
        check_out_str = check_out_date.strftime("%d/%m/%Y") if check_out_date else ""

        pdf.field_row("Entrada", check_in_str)
        pdf.field_row("Salida", check_out_str)
        pdf.field_row("Noches", str(reservation.stay_days or 0))
        if reservation.arrival_time:
            pdf.field_row("Hora llegada", reservation.arrival_time.strftime("%H:%M"))
        pdf.field_row("Estado", reservation.status or "Confirmada")
        pdf.ln(3)

        # --- Room Info ---
        pdf.section_title("Habitacion")
        room_code = room.internal_code if room and room.internal_code else (reservation.room_id or "")
        pdf.field_row("Habitacion", room_code)
        if category:
            pdf.field_row("Categoria", category.name or "")
        if room and room.floor is not None:
            pdf.field_row("Piso", str(room.floor))
        pdf.ln(3)

        # --- Pricing ---
        pdf.section_title("Detalle de Precio")
        if client_type:
            pdf.field_row("Tipo de cliente", client_type.name)

        # Price per night from breakdown or calculated
        price_per_night = None
        if reservation.price_breakdown:
            try:
                breakdown = json.loads(reservation.price_breakdown)
                bd = breakdown.get("breakdown", breakdown)
                price_per_night = bd.get("base_unit_price")
            except (json.JSONDecodeError, TypeError):
                pass

        if price_per_night is None and reservation.price and reservation.stay_days:
            price_per_night = reservation.price / reservation.stay_days

        if price_per_night is not None:
            pdf.field_row("Precio por noche", _format_pyg(price_per_night))
        pdf.field_row("Noches", str(reservation.stay_days or 0))

        # Final price (bold)
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        final = reservation.final_price if reservation.final_price is not None else reservation.price
        pdf.cell(50, 8, "TOTAL:", align="L")
        pdf.cell(0, 8, _format_pyg(final), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(3)

        # --- Parking ---
        if reservation.parking_needed:
            pdf.section_title("Estacionamiento")
            pdf.field_row("Vehiculo", reservation.vehicle_model or "")
            pdf.field_row("Placa", reservation.vehicle_plate or "")
            pdf.ln(3)

        # --- Source ---
        if reservation.source and reservation.source != "Direct":
            pdf.field_row("Origen", reservation.source)

        # Save file
        guest_safe = _sanitize_filename(reservation.guest_name or "sin_nombre")
        date_str = reservation.check_in_date.strftime("%d-%m-%y") if reservation.check_in_date else "00-00-00"
        filename = f"{guest_safe}_{date_str}_{reservation_id}.pdf"
        filepath = os.path.join(RESERVAS_DIR, filename)

        pdf.output(filepath)
        logger.info(f"Reservation PDF generated: {filepath}")
        return filepath

    @staticmethod
    @with_db
    def generate_folio_pdf(db: Session, reservation_id: str) -> Optional[str]:
        """
        Generate a Guest Folio ('Cuenta del Huésped') PDF (v1.6.0 — Phase 3).

        Shows the full account: room charges, consumos (itemized), payments,
        and final balance. Saved to backend/hotel/Cuentas/.

        Args:
            db: Database session
            reservation_id: Reservation ID

        Returns:
            File path of generated PDF, or None if reservation not found.
        """
        from database import Reservation, Room, RoomCategory, Consumo, Transaccion

        _ensure_dirs()

        reservation = db.query(Reservation).filter(
            Reservation.id == reservation_id
        ).first()
        if not reservation:
            logger.warning(f"Reservation {reservation_id} not found for folio PDF generation")
            return None

        room = db.query(Room).filter(Room.id == reservation.room_id).first()
        category = None
        if room and room.category_id:
            category = db.query(RoomCategory).filter(
                RoomCategory.id == room.category_id
            ).first()

        hotel_info = DocumentService._get_hotel_info(db)

        # --- Query consumos + payments ---
        consumos = db.query(Consumo).filter(
            Consumo.reserva_id == reservation_id,
            Consumo.voided == False,
        ).order_by(Consumo.created_at.asc()).all()

        payments = db.query(Transaccion).filter(
            Transaccion.reserva_id == reservation_id,
            Transaccion.voided == False,
        ).order_by(Transaccion.created_at.asc()).all()

        room_total = float(reservation.price or 0.0)
        consumo_total = sum(float(c.total or 0.0) for c in consumos)
        total = room_total + consumo_total
        paid = sum(float(t.amount or 0.0) for t in payments)
        balance_due = max(total - paid, 0.0)

        # --- Build PDF ---
        pdf = HotelPDF(
            hotel_name=hotel_info["name"],
            hotel_address=hotel_info["address"],
            hotel_phone=hotel_info["phone"],
            hotel_email=hotel_info["email"],
        )
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "CUENTA DEL HUESPED",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Reserva #{reservation.id}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(4)

        # --- Section 1: Datos del huesped ---
        pdf.section_title("Datos del Huesped")
        pdf.ln(2)
        pdf.field_row("Huesped", reservation.guest_name or "-")
        if reservation.contact_phone:
            pdf.field_row("Telefono", reservation.contact_phone)
        if reservation.contact_email:
            pdf.field_row("Email", reservation.contact_email)
        room_label = room.internal_code if room else reservation.room_id or "-"
        pdf.field_row("Habitacion", room_label)
        if category:
            pdf.field_row("Categoria", category.name)
        if reservation.check_in_date:
            pdf.field_row("Check-in", reservation.check_in_date.strftime("%d/%m/%Y"))
        if reservation.check_in_date and reservation.stay_days:
            check_out = reservation.check_in_date + timedelta(days=reservation.stay_days)
            pdf.field_row("Check-out", check_out.strftime("%d/%m/%Y"))
        pdf.field_row("Noches", str(reservation.stay_days or 0))
        pdf.ln(4)

        # --- Section 2: Cargos de habitacion ---
        pdf.section_title("Cargos de Habitacion")
        pdf.ln(2)
        nights = reservation.stay_days or 0
        rate_per_night = room_total / nights if nights else room_total
        pdf.field_row(
            f"{nights} noche(s) x {_format_pyg(rate_per_night)}",
            _format_pyg(room_total),
        )

        # Show applied modifiers if present (price breakdown may be JSON)
        if reservation.price_breakdown:
            try:
                breakdown = json.loads(reservation.price_breakdown)
                if isinstance(breakdown, dict):
                    if breakdown.get("season"):
                        pdf.field_row("Temporada", str(breakdown["season"]))
                    if breakdown.get("discount"):
                        pdf.field_row(
                            "Descuento cliente",
                            _format_pyg(-float(breakdown["discount"])),
                        )
            except Exception:
                pass

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(140, 7, "Subtotal habitacion:", align="R")
        pdf.cell(0, 7, _format_pyg(room_total),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.ln(4)

        # --- Section 3: Consumos ---
        pdf.section_title("Consumos")
        pdf.ln(2)
        if consumos:
            # Table header
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(30, 6, "Fecha")
            pdf.cell(75, 6, "Producto")
            pdf.cell(20, 6, "Cant.", align="C")
            pdf.cell(30, 6, "P. Unit.", align="R")
            pdf.cell(0, 6, "Total", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(1)

            # Rows
            pdf.set_font("Helvetica", "", 9)
            for c in consumos:
                fecha = c.created_at.strftime("%d/%m/%y") if c.created_at else "-"
                pdf.cell(30, 6, fecha)
                name = (c.producto_name or "-")[:35]
                pdf.cell(75, 6, name)
                pdf.cell(20, 6, str(c.quantity), align="C")
                pdf.cell(30, 6, _format_pyg(c.unit_price), align="R")
                pdf.cell(0, 6, _format_pyg(c.total),
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(140, 7, "Subtotal consumos:", align="R")
            pdf.cell(0, 7, _format_pyg(consumo_total),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        else:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 6, "Sin consumos registrados.",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        # --- Section 4: Pagos ---
        pdf.section_title("Pagos")
        pdf.ln(2)
        if payments:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(30, 6, "Fecha")
            pdf.cell(40, 6, "Metodo")
            pdf.cell(65, 6, "Referencia")
            pdf.cell(0, 6, "Monto", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(1)

            pdf.set_font("Helvetica", "", 9)
            for t in payments:
                fecha = t.created_at.strftime("%d/%m/%y") if t.created_at else "-"
                pdf.cell(30, 6, fecha)
                pdf.cell(40, 6, t.payment_method or "-")
                pdf.cell(65, 6, (t.reference_number or "-")[:30])
                pdf.cell(0, 6, _format_pyg(t.amount),
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(140, 7, "Total pagado:", align="R")
            pdf.cell(0, 7, _format_pyg(paid),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        else:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 6, "Sin pagos registrados.",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(6)

        # --- Final totals ---
        pdf.set_draw_color(50, 50, 50)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(140, 8, "TOTAL:", align="R")
        pdf.cell(0, 8, _format_pyg(total),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.cell(140, 8, "Pagado:", align="R")
        pdf.cell(0, 8, _format_pyg(paid),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.set_text_color(180, 60, 60) if balance_due > 0 else pdf.set_text_color(50, 150, 50)
        pdf.cell(140, 8, "SALDO:", align="R")
        pdf.cell(0, 8, _format_pyg(balance_due),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.set_text_color(0, 0, 0)

        # --- Save file ---
        guest_safe = _sanitize_filename(
            (reservation.guest_name or "sin_nombre").split(",")[0].strip()
        )
        if reservation.check_in_date and reservation.stay_days:
            check_out = reservation.check_in_date + timedelta(days=reservation.stay_days)
            date_str = check_out.strftime("%d-%m-%y")
        else:
            date_str = "00-00-00"
        filename = f"folio_{guest_safe}_{date_str}_{reservation_id}.pdf"
        filepath = os.path.join(CUENTAS_DIR, filename)

        pdf.output(filepath)
        logger.info(f"Folio PDF generated: {filepath}")
        return filepath

    @staticmethod
    @with_db
    def generate_client_pdf(db: Session, checkin_id: int) -> Optional[str]:
        """
        Generate a client registration (Ficha de Huesped) PDF.

        Args:
            db: Database session
            checkin_id: CheckIn record ID

        Returns:
            File path of generated PDF, or None if check-in not found.
        """
        from database import CheckIn, Reservation, Room, RoomCategory

        _ensure_dirs()

        checkin = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if not checkin:
            logger.warning(f"CheckIn {checkin_id} not found for PDF generation")
            return None

        # Related data
        reservation = None
        if checkin.reservation_id:
            reservation = db.query(Reservation).filter(
                Reservation.id == checkin.reservation_id
            ).first()

        room = None
        if checkin.room_id:
            room = db.query(Room).filter(Room.id == checkin.room_id).first()

        category = None
        if room and room.category_id:
            category = db.query(RoomCategory).filter(RoomCategory.id == room.category_id).first()

        hotel_info = DocumentService._get_hotel_info(db)

        # Build PDF
        pdf = HotelPDF(
            hotel_name=hotel_info["name"],
            hotel_address=hotel_info["address"],
            hotel_phone=hotel_info["phone"],
            hotel_email=hotel_info["email"],
        )
        pdf.add_page()

        # Title
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Ficha de Huesped", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(4)

        # --- Personal Info ---
        pdf.section_title("Datos Personales")
        pdf.field_row("Apellidos", checkin.last_name or "")
        pdf.field_row("Nombres", checkin.first_name or "")
        pdf.field_row("Documento", checkin.document_number or "")
        pdf.field_row("Nacionalidad", checkin.nationality or "")
        if checkin.birth_date:
            pdf.field_row("Fecha Nac.", checkin.birth_date.strftime("%d/%m/%Y"))
        pdf.field_row("Pais", checkin.country or "")
        if checkin.civil_status:
            pdf.field_row("Estado Civil", checkin.civil_status)
        pdf.ln(3)

        # --- Stay Info ---
        pdf.section_title("Datos de Estadia")
        if checkin.created_at:
            date_val = checkin.created_at
            if hasattr(date_val, 'strftime'):
                pdf.field_row("Fecha Ingreso", date_val.strftime("%d/%m/%Y"))
        if checkin.check_in_time:
            pdf.field_row("Hora", checkin.check_in_time.strftime("%H:%M"))

        room_code = room.internal_code if room and room.internal_code else (checkin.room_id or "")
        pdf.field_row("Habitacion", room_code)
        if category:
            pdf.field_row("Categoria", category.name or "")

        if reservation:
            pdf.field_row("Reserva N.", reservation.id)
            if reservation.stay_days:
                pdf.field_row("Noches", str(reservation.stay_days))

        if checkin.origin:
            pdf.field_row("Procedencia", checkin.origin)
        if checkin.destination:
            pdf.field_row("Destino", checkin.destination)
        pdf.ln(3)

        # --- Vehicle ---
        if checkin.vehicle_model or checkin.vehicle_plate:
            pdf.section_title("Vehiculo")
            pdf.field_row("Modelo", checkin.vehicle_model or "")
            pdf.field_row("Placa", checkin.vehicle_plate or "")
            pdf.ln(3)

        # --- Billing ---
        if checkin.billing_name or checkin.billing_ruc:
            pdf.section_title("Facturacion")
            pdf.field_row("Nombre/Razon Social", checkin.billing_name or "")
            pdf.field_row("RUC", checkin.billing_ruc or "")
            pdf.ln(3)

        # --- Signature ---
        pdf.ln(15)
        pdf.line(30, pdf.get_y(), 100, pdf.get_y())
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, "Firma del Huesped", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")

        # Save file
        last = _sanitize_filename(checkin.last_name or "sin_apellido")
        first = _sanitize_filename(checkin.first_name or "")
        date_str = "00-00-00"
        if checkin.created_at and hasattr(checkin.created_at, 'strftime'):
            date_str = checkin.created_at.strftime("%d-%m-%y")
        name_part = f"{last}_{first}" if first else last
        filename = f"{name_part}_{date_str}.pdf"
        filepath = os.path.join(CLIENTES_DIR, filename)

        pdf.output(filepath)
        logger.info(f"Client PDF generated: {filepath}")
        return filepath

    @staticmethod
    def get_reservation_pdf_path(reservation_id: str) -> Optional[str]:
        """Find existing PDF for a reservation by scanning Reservas dir."""
        _ensure_dirs()
        suffix = f"_{reservation_id}.pdf"
        for fname in os.listdir(RESERVAS_DIR):
            if fname.endswith(suffix):
                return os.path.join(RESERVAS_DIR, fname)
        return None

    @staticmethod
    def get_folio_pdf_path(reservation_id: str) -> Optional[str]:
        """Find existing folio PDF for a reservation by scanning Cuentas dir."""
        _ensure_dirs()
        suffix = f"_{reservation_id}.pdf"
        if not os.path.isdir(CUENTAS_DIR):
            return None
        for fname in os.listdir(CUENTAS_DIR):
            if fname.endswith(suffix) and fname.startswith("folio_"):
                return os.path.join(CUENTAS_DIR, fname)
        return None

    @staticmethod
    def get_client_pdf_path(checkin_id: int) -> Optional[str]:
        """Find existing PDF for a client check-in. Returns first match or None."""
        # Client PDFs don't include checkin_id in name, so we can't do suffix lookup.
        # This method is a fallback; the download endpoint generates on-demand if not found.
        return None

    @staticmethod
    def list_documents(folder: str = "Reservas") -> List[dict]:
        """List all PDFs in the specified folder with metadata."""
        _ensure_dirs()
        if folder == "Reservas":
            target_dir = RESERVAS_DIR
        elif folder == "Clientes":
            target_dir = CLIENTES_DIR
        elif folder == "Cuentas":
            target_dir = CUENTAS_DIR
        else:
            target_dir = RESERVAS_DIR  # fallback, preserves old behavior
        documents = []
        if not os.path.isdir(target_dir):
            return documents

        for fname in sorted(os.listdir(target_dir), reverse=True):
            if not fname.lower().endswith(".pdf"):
                continue
            fpath = os.path.join(target_dir, fname)
            stat = os.stat(fpath)
            documents.append({
                "filename": fname,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "folder": folder,
            })

        return documents
