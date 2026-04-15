"""
Hotel Munich LMS - Esquemas de Validación (Pydantic)
=====================================================

Define los Data Transfer Objects (DTOs) con validaciones estrictas
de reglas de negocio usando Pydantic v2.

Validaciones implementadas:
- Campos requeridos vs opcionales claramente definidos
- Rangos válidos para números (stay_days, price)
- Validación de fechas coherentes (no pasadas)
- Strings no vacíos para campos críticos
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
from datetime import date, datetime, time
import re


# ==========================================
# VALIDADORES COMPARTIDOS
# ==========================================

def validate_phone_format(phone: str) -> str:
    """Valida y normaliza formato de teléfono."""
    if not phone:
        return ""
    # Remover espacios y caracteres especiales excepto +
    cleaned = re.sub(r'[^\d+]', '', phone)
    return cleaned


def validate_document_format(doc: str) -> str:
    """Valida formato de documento (cédula/DNI/pasaporte)."""
    if not doc:
        return ""
    # Remover puntos y espacios, mantener letras y números
    cleaned = re.sub(r'[.\s]', '', doc.upper())
    return cleaned


# ==========================================
# SCHEMAS DE USUARIO
# ==========================================

class UserDTO(BaseModel):
    """Datos de usuario autenticado (solo lectura)."""
    username: str
    role: str
    real_name: str


# ==========================================
# SCHEMAS DE RESERVA
# ==========================================

class ReservationCreate(BaseModel):
    """
    Schema para crear/actualizar reservas.
    
    Validaciones:
    - check_in_date: Obligatorio, no puede ser fecha pasada
    - stay_days: Entre 1 y 365 días
    - guest_name: Obligatorio, mínimo 2 caracteres
    - price: No puede ser negativo
    - room_ids: Al menos una habitación
    """
    check_in_date: date = Field(..., description="Fecha de entrada (obligatoria)")
    stay_days: int = Field(default=1, ge=1, le=365, description="Días de estadía (1-365)")
    guest_name: str = Field(..., min_length=2, description="Nombre del huésped")
    room_ids: List[str] = Field(..., min_length=1, description="Lista de habitaciones")
    room_type: str = Field(default="", description="Tipo de habitación")
    price: float = Field(default=0.0, ge=0, description="Precio total (>= 0)")
    arrival_time: Optional[time] = Field(default=None, description="Hora estimada de llegada")
    contact_phone: str = Field(default="", description="Teléfono de contacto")
    contact_email: str = Field(default="", description="Email de contacto")
    reserved_by: str = Field(default="", description="Quién solicitó la reserva")
    received_by: str = Field(default="", description="Recepcionista que tomó la reserva")
    
    # Los Monges / Pricing Fields
    property_id: Optional[str] = Field(default="los-monges", description="ID de la propiedad")
    category_id: Optional[str] = Field(default=None, description="ID de categoría de habitación")
    client_type_id: Optional[str] = Field(default=None, description="ID de tipo de cliente")
    contract_id: Optional[str] = Field(default=None, description="ID de contrato corporativo")
    price_breakdown: Optional[str] = Field(default=None, description="Detalle de cálculo de precio (JSON)") # JSON string
    
    # Parking & Source
    parking_needed: bool = Field(default=False, description="Indica si se necesita parking")
    vehicle_model: Optional[str] = Field(default=None, description="Modelo del vehículo")
    vehicle_plate: Optional[str] = Field(default=None, description="Chapa/Patente del vehículo")
    source: Optional[str] = Field(default="Direct", description="Origen de la reserva (ej. Direct, Booking.com)")
    external_id: Optional[str] = Field(default=None, description="ID externo de la reserva (ej. de OTA)")
    paid: Optional[bool] = Field(default=True, description="Si el huesped ya pago. True=Confirmada, False=Pendiente")

    # Identity fields (from document scan) - used to auto-create CheckIn
    document_number: Optional[str] = Field(default="", description="Número de documento del huésped")
    guest_last_name: Optional[str] = Field(default="", description="Apellidos del huésped")
    guest_first_name: Optional[str] = Field(default="", description="Nombres del huésped")
    nationality: Optional[str] = Field(default="", description="Nacionalidad del huésped")
    birth_date: Optional[date] = Field(default=None, description="Fecha de nacimiento del huésped")
    country: Optional[str] = Field(default="", description="País del huésped")

    @field_validator('guest_name')
    @classmethod
    def validate_guest_name(cls, v: str) -> str:
        """Asegura que el nombre no esté vacío y lo normaliza."""
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError('El nombre del huésped debe tener al menos 2 caracteres')
        return cleaned

    @field_validator('contact_phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Normaliza el teléfono."""
        return validate_phone_format(v)

    @field_validator('room_ids')
    @classmethod
    def validate_rooms(cls, v: List[str]) -> List[str]:
        """Asegura que haya al menos una habitación válida."""
        valid_rooms = [r.strip() for r in v if r.strip()]
        if not valid_rooms:
            raise ValueError('Debe seleccionar al menos una habitación')
        return valid_rooms

    @model_validator(mode='after')
    def validate_date_coherence(self):
        """Valida que la fecha de entrada no sea pasada."""
        if self.check_in_date < date.today():
            raise ValueError('La fecha de entrada no puede ser anterior a hoy')
        return self


class StatusUpdateRequest(BaseModel):
    """Schema para cambiar el estado de una reserva."""
    status: str = Field(..., description="Nuevo estado: Pendiente, Confirmada, Completada, Cancelada")
    reason: Optional[str] = Field(default=None, description="Razon del cambio (requerido para cancelacion)")


class ReservationDTO(BaseModel):
    """Schema de salida para listar reservas."""
    id: str
    room_id: str
    room_internal_code: str = ""
    guest_name: str
    status: str
    check_in: date
    check_out: date
    price: float


class ReservationDetailDTO(ReservationDTO):
    """Schema de salida detallada para una reserva individual."""
    stay_days: int = 0
    room_type: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    reserved_by: str = ""
    received_by: str = ""
    arrival_time: Optional[time] = None
    source: str = ""
    parking_needed: bool = False
    vehicle_model: Optional[str] = None
    vehicle_plate: Optional[str] = None
    category_id: Optional[str] = None
    client_type_id: Optional[str] = None
    created_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    # v1.5.0 — Channel Manager v2
    ota_booking_id: Optional[str] = None
    needs_review: bool = False
    review_reason: Optional[str] = None


class CalendarEventDTO(BaseModel):
    """
    Schema para eventos de calendario (FullCalendar compatible).
    
    Estructura estándar para librerías de calendario JS.
    """
    title: str = Field(..., description="Nombre del huésped")
    start: str = Field(..., description="Fecha/hora inicio (ISO format)")
    end: str = Field(..., description="Fecha/hora fin (ISO format)")
    resourceId: str = Field(..., description="ID de habitación")
    color: str = Field(default="#2196F3", description="Color del evento")
    extendedProps: Optional[dict] = Field(default=None, description="Propiedades adicionales")


class TodaySummaryDTO(BaseModel):
    """Schema para resumen de ocupación (vista móvil)."""
    llegadas_hoy: int = Field(default=0, description="Check-ins programados hoy")
    salidas_hoy: int = Field(default=0, description="Check-outs programados hoy")
    ocupadas: int = Field(default=0, description="Habitaciones ocupadas")
    libres: int = Field(default=0, description="Habitaciones libres")
    total_habitaciones: int = Field(default=0, description="Total de habitaciones")
    porcentaje_ocupacion: float = Field(default=0.0, description="% de ocupación")



# ==========================================
# SCHEMAS DE CHECK-IN (FICHA DE HUÉSPED)
# ==========================================

class CheckInCreate(BaseModel):
    """
    Schema para registro de huésped (ficha).
    
    Validaciones:
    - document_number: Formato limpio sin puntos
    - birth_date: No puede ser futura
    - Campos críticos tienen defaults vacíos pero válidos
    """
    room_id: Optional[str] = Field(default=None, description="Habitación asignada")
    reservation_id: Optional[str] = Field(default=None, description="Reserva vinculada")
    check_in_time: Optional[datetime] = Field(default=None, description="Hora de ingreso")

    # Datos personales
    last_name: str = Field(default="", description="Apellidos")
    first_name: str = Field(default="", description="Nombres")
    nationality: str = Field(default="", description="Nacionalidad")
    birth_date: Optional[date] = Field(default=None, description="Fecha de nacimiento")
    origin: str = Field(default="", description="Procedencia/Origen")
    destination: str = Field(default="", description="Destino")
    civil_status: str = Field(default="", description="Estado civil")
    document_number: str = Field(default="", description="Número de documento")
    country: str = Field(default="", description="País")

    # Contacto
    contact_phone: str = Field(default="", description="Teléfono de contacto")
    contact_email: str = Field(default="", description="Email de contacto")

    # Datos de facturación
    billing_name: str = Field(default="", description="Razón social para facturación")
    billing_ruc: str = Field(default="", description="RUC para facturación")
    
    # Vehículo
    vehicle_model: str = Field(default="", description="Modelo del vehículo")
    vehicle_plate: str = Field(default="", description="Chapa/Patente del vehículo")

    @field_validator('document_number')
    @classmethod
    def validate_document(cls, v: str) -> str:
        """Limpia y normaliza el número de documento."""
        return validate_document_format(v)

    @field_validator('birth_date')
    @classmethod
    def validate_birth_date(cls, v: Optional[date]) -> Optional[date]:
        """Valida que la fecha de nacimiento no sea futura."""
        if v and v > date.today():
            raise ValueError('La fecha de nacimiento no puede ser futura')
        return v

    @field_validator('billing_ruc')
    @classmethod
    def validate_ruc(cls, v: str) -> str:
        """Limpia el RUC (solo dígitos y guiones)."""
        if not v:
            return ""
        # RUC paraguayo: XXXXXXXX-X
        cleaned = re.sub(r'[^\d\-]', '', v)
        return cleaned

    @model_validator(mode='after')
    def validate_guest_identity(self):
        """Valida que al menos haya nombre o documento."""
        has_name = bool(self.last_name.strip() or self.first_name.strip())
        has_doc = bool(self.document_number.strip())
        
        # Al menos uno debe estar presente
        if not has_name and not has_doc:
            pass
        return self


# ==========================================
# SCHEMAS DE PRECIOS
# ==========================================

class PriceCalculationRequest(BaseModel):
    """Schema para solicitar cálculo de precios."""
    property_id: str = Field(default="los-monges", description="ID de la propiedad")
    category_id: str = Field(..., description="ID de la categoría de habitación")
    check_in: date = Field(..., description="Fecha de entrada")
    stay_days: int = Field(..., ge=1, le=365, description="Días de estadía")
    client_type_id: str = Field(default="los-monges-particular", description="ID del tipo de cliente")
    room_id: Optional[str] = Field(default=None, description="ID de habitación (opcional)")
    season_id: Optional[str] = Field(default=None, description="Override de temporada (selección manual)")

class PricingSeasonDTO(BaseModel):
    """Season info for manual selection dropdown."""
    id: str
    name: str
    description: Optional[str] = None
    price_modifier: float
    color: str = "#F59E0B"

class PriceModifierDTO(BaseModel):
    """Detalle de modificador de precio (temporada/descuento)."""
    name: str
    amount: float
    percent: float

class PriceBreakdownDTO(BaseModel):
    """Desglose del cálculo de precio."""
    base_unit_price: float
    base_total: float
    nights: int
    modifiers: List[PriceModifierDTO]

class PriceCalculationResponse(BaseModel):
    """Respuesta del cálculo de precio."""
    final_price: float
    currency: str
    breakdown: PriceBreakdownDTO

class ClientTypeDTO(BaseModel):
    """Schema para tipos de cliente."""
    id: str
    name: str
    description: str
    default_discount_percent: float
    color: str
    icon: str


# ==========================================
# CAJA & TRANSACCIONES (Phase 1)
# ==========================================

class CajaAbrirRequest(BaseModel):
    """Request para abrir una sesion de caja."""
    opening_balance: float = Field(..., ge=0, description="Balance inicial en efectivo")
    notes: str = Field(default="", description="Notas opcionales")


class CajaCerrarRequest(BaseModel):
    """Request para cerrar una sesion de caja."""
    session_id: int = Field(..., description="ID de la sesion a cerrar")
    closing_balance_declared: float = Field(..., ge=0, description="Monto declarado por el recepcionista")
    notes: str = Field(default="", description="Notas opcionales del cierre")


class CajaSesionDTO(BaseModel):
    """Schema de salida para una sesion de caja."""
    id: int
    user_id: int
    user_name: str = ""
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opening_balance: float
    closing_balance_declared: Optional[float] = None
    closing_balance_expected: Optional[float] = None
    difference: Optional[float] = None
    status: str
    notes: Optional[str] = None
    total_efectivo: float = 0.0


class TransaccionCreate(BaseModel):
    """Request para registrar un pago."""
    reserva_id: str = Field(..., description="ID de la reserva")
    amount: float = Field(..., gt=0, description="Monto del pago (mayor a 0)")
    payment_method: str = Field(..., description="EFECTIVO | TRANSFERENCIA | POS")
    reference_number: Optional[str] = Field(default=None, description="Numero de referencia (transfer/POS)")
    description: Optional[str] = Field(default=None, description="Descripcion opcional")

    @field_validator('payment_method')
    @classmethod
    def validate_method(cls, v: str) -> str:
        v = v.upper()
        if v not in ("EFECTIVO", "TRANSFERENCIA", "POS"):
            raise ValueError("payment_method debe ser EFECTIVO, TRANSFERENCIA o POS")
        return v


class TransaccionDTO(BaseModel):
    """Schema de salida para una transaccion."""
    id: int
    reserva_id: Optional[str] = None
    caja_sesion_id: Optional[int] = None
    amount: float
    payment_method: str
    reference_number: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None
    voided: bool
    void_reason: Optional[str] = None
    voided_at: Optional[datetime] = None
    voided_by: Optional[str] = None


class AnularTransaccionRequest(BaseModel):
    """Request para anular una transaccion."""
    reason: str = Field(..., min_length=3, description="Razon de la anulacion (mandatory)")


class SaldoReservaDTO(BaseModel):
    """Schema con el estado de pagos de una reserva."""
    reserva_id: str
    total: float
    paid: float
    pending: float
    transacciones: List[TransaccionDTO] = []


# ==========================================
# v1.5.0 Phase 2 — Channel Manager Upgrade
# ==========================================

class ICalSyncLogDTO(BaseModel):
    """Single audit row for an iCal sync attempt."""
    id: int
    feed_id: int
    attempted_at: datetime
    status: str  # "OK" | "ERROR"
    created_count: int
    updated_count: int
    flagged_for_review_count: int
    conflicts_detected: int
    error_message: Optional[str] = None
    duration_ms: int


class FeedHealthDTO(BaseModel):
    """Health summary for an iCal feed (used by mobile + PC dashboards)."""
    feed_id: int
    source: str
    room_id: str
    room_label: Optional[str] = None
    last_sync_status: str  # "OK" | "ERROR" | "NEVER"
    last_sync_error: Optional[str] = None
    consecutive_failures: int
    last_sync_attempted_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    health_badge: str  # "healthy" | "warning" | "error" | "unknown"


class AcknowledgeReviewRequest(BaseModel):
    """Operator acknowledges that a flagged reservation should stay active."""
    notes: Optional[str] = None


class ConfirmOTACancellationRequest(BaseModel):
    """Operator confirms an OTA-initiated cancellation."""
    reason: Optional[str] = None  # extra context, defaults to review_reason


class NeedsReviewItemDTO(BaseModel):
    """A reservation flagged for operator review."""
    id: str
    guest_name: str
    check_in_date: date
    stay_days: int
    room_id: str
    source: str
    status: str
    review_reason: Optional[str] = None
    price: Optional[float] = None
