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
from typing import Any, Dict, List, Literal, Optional
from datetime import date, datetime, time
import re

from api.core.config import DEFAULT_PROPERTY_ID


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

class VehicleInput(BaseModel):
    """Single vehicle on a multi-vehicle reservation (v1.10.0 — Phase 2c).

    Two modes:

    - **linked** — `guest_vehicle_id` points at the booker's master
      `guest_vehicles` row. The receptionist picked it from the dropdown
      of the primary guest's registered vehicles. plate/model/color are
      ignored on input (the service copies them from the master).

    - **quick** — `guest_vehicle_id` is None; plate/model/color are the
      source of truth. Used for companion vehicles whose driver is NOT a
      registered guest (e.g. a second car arriving at 2 AM — no time to
      create a Guest record).

    `is_primary` marks the vehicle that ALSO populates the legacy
    `reservations.vehicle_plate` / `vehicle_model` snapshot columns
    (back-compat for older readers). Exactly one vehicle per reservation
    should be primary — the service enforces this (defaults the first
    one if none is marked, rejects multiple).
    """
    mode: Literal["linked", "quick"] = Field(..., description="'linked' = pick from guest catalogue; 'quick' = ad-hoc plate")
    guest_vehicle_id: Optional[int] = Field(default=None, description="ID en guest_vehicles (modo linked)")
    plate_number: Optional[str] = Field(default=None, description="Chapa/patente (modo quick)")
    model: Optional[str] = Field(default=None, description="Modelo del vehículo (modo quick)")
    color: Optional[str] = Field(default=None, description="Color del vehículo (modo quick)")
    is_primary: bool = Field(default=False, description="Marca el vehículo que también se snapshot-ea en reservations.vehicle_plate")
    notes: Optional[str] = Field(default=None, description="Notas opcionales (ej. 'auto del acompañante')")

    @model_validator(mode='after')
    def validate_mode_fields(self):
        if self.mode == "linked":
            if self.guest_vehicle_id is None:
                raise ValueError("modo 'linked' requiere guest_vehicle_id")
        elif self.mode == "quick":
            if not (self.plate_number or "").strip():
                raise ValueError("modo 'quick' requiere plate_number")
        return self

    @field_validator('plate_number')
    @classmethod
    def normalise_plate(cls, v: Optional[str]) -> Optional[str]:
        """Normalize plate: uppercase + trim. Mirrors GuestVehicleService._norm_plate."""
        if v is None:
            return None
        cleaned = v.strip().upper()
        return cleaned or None


class ReservationVehicleDTO(BaseModel):
    """Vehicle row attached to a reservation (response shape).

    Mirrors ReservationVehicle SQLAlchemy model. Always includes the
    snapshot fields (plate/model/color) — even for linked rows — so
    the UI can render the list without an extra JOIN to guest_vehicles.
    """
    id: int
    guest_vehicle_id: Optional[int] = None
    plate_number: str
    model: Optional[str] = None
    color: Optional[str] = None
    is_primary: bool = False
    notes: Optional[str] = None

    class Config:
        from_attributes = True


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
    property_id: Optional[str] = Field(default=DEFAULT_PROPERTY_ID, description="ID de la propiedad")
    category_id: Optional[str] = Field(default=None, description="ID de categoría de habitación")
    client_type_id: Optional[str] = Field(default=None, description="ID de tipo de cliente")
    contract_id: Optional[str] = Field(default=None, description="ID de contrato corporativo")
    # v1.10.0 Phase 2b: was Optional[str] of JSON-encoded text. Now accepts
    # a dict (or JSON-encoded string for back-compat with older callers —
    # the JSON column stores whatever it gets via its `value_processor`).
    price_breakdown: Optional[Any] = Field(default=None, description="Detalle de cálculo de precio (dict)")
    
    # Parking & Source
    parking_needed: bool = Field(default=False, description="Indica si se necesita parking")
    vehicle_model: Optional[str] = Field(default=None, description="Modelo del vehículo (legacy single-vehicle compat)")
    vehicle_plate: Optional[str] = Field(default=None, description="Chapa/Patente del vehículo (legacy single-vehicle compat)")
    # v1.10.0 Phase 2a-ext: color passthrough — propagates to master GuestVehicle.
    # Not stored on the Reservation row (avoids a column add); the auxiliary
    # metadata lives only on the master vehicle, which is the canonical place
    # to ask "¿de quién es el auto blanco?".
    vehicle_color: Optional[str] = Field(default=None, description="Color del vehículo (legacy single-vehicle compat)")
    # v1.10.0 Phase 2c — Multi-vehicle support.
    # When provided, takes precedence over the single vehicle_plate/model/color
    # fields above. The service writes one reservation_vehicles row per entry,
    # AND copies the is_primary row's plate/model into the legacy snapshot
    # columns so old readers keep working. When empty, the legacy single-
    # vehicle path is unchanged.
    vehicles: List[VehicleInput] = Field(default_factory=list, description="Lista de vehículos para la reserva (multi-vehículo)")
    # v1.10.0 Phase 2e — Early check-in / late check-out flags (MVP).
    # The receptionist can mark these on the form; surcharge (if any) is
    # applied at folio generation. Availability blocking from late_checkout
    # is deferred to Phase 6.5.
    early_checkin: bool = Field(default=False, description="Llegada antes del check_in_start del hotel")
    late_checkout: bool = Field(default=False, description="Salida después del check_out_time del hotel")
    late_checkout_time: Optional[str] = Field(default=None, description="Hora acordada de late check-out (HH:MM); ignorada si late_checkout=False")
    source: Optional[str] = Field(default="Direct", description="Origen de la reserva (ej. Direct, Booking.com)")
    external_id: Optional[str] = Field(default=None, description="ID externo de la reserva (ej. de OTA)")
    paid: Optional[bool] = Field(default=True, description="Si el huesped ya pago. True=Confirmada, False=Pendiente")

    # v1.7.0 — Meal Plan (Phase 4)
    meal_plan_id: Optional[str] = Field(default=None, description="ID del plan de comidas seleccionado")
    breakfast_guests: Optional[int] = Field(default=None, ge=0, description="Cantidad de huéspedes con desayuno (OPCIONAL_PERSONA)")

    # Identity fields (from document scan) - used to auto-create CheckIn
    document_number: Optional[str] = Field(default="", description="Número de documento del huésped")
    guest_last_name: Optional[str] = Field(default="", description="Apellidos del huésped")
    guest_first_name: Optional[str] = Field(default="", description="Nombres del huésped")
    nationality: Optional[str] = Field(default="", description="Nacionalidad del huésped")
    birth_date: Optional[date] = Field(default=None, description="Fecha de nacimiento del huésped")
    country: Optional[str] = Field(default="", description="País del huésped")

    # v1.10.0 Phase 2a Bug #2 Fix A — explicit Guest link
    # When the front-end has the user pick from a Guest dropdown (PC + mobile),
    # send the picked id here. The service uses it directly and skips the
    # find_or_create_guest fuzzy match. If absent (legacy callers, manual name
    # entry, OTA imports), fallback resolution by name+doc kicks in.
    guest_id: Optional[int] = Field(default=None, description="ID del huésped maestro (si fue seleccionado del dropdown)")

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
        """Valida que la fecha de entrada esté dentro del hotel-day vigente
        o en el futuro.

        v1.10.0 Phase 2e: el "día del hotel" no termina a la medianoche,
        sino al check-out del día siguiente. Un receptionist a las 02:00
        de D+1 sigue trabajando "la noche de D" — debe poder crear una
        reserva con check_in_date=D hasta que pase el check-out del hotel.

        El cutoff exacto depende del check_out_time de la propiedad, que
        este validator NO conoce (no puede leer la DB en Pydantic). Por
        eso usa el default conservador 10:00 — propiedades con check-out
        más tarde permiten ventana más amplia, validada server-side por
        `ReservationService.create_reservations` antes de persistir.
        """
        # Lazy import to avoid a heavy services package load at schema-import time
        from services.hotel_day import can_create_reservation_for_date
        if not can_create_reservation_for_date(self.check_in_date):
            raise ValueError(
                'La fecha de entrada ya pasó (el horario de check-out del '
                'día siguiente ya terminó).'
            )
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
    # v1.7.0 — Meal Plan (Phase 4)
    meal_plan_id: Optional[str] = None
    meal_plan_code: Optional[str] = None
    meal_plan_name: Optional[str] = None
    breakfast_guests: Optional[int] = None
    # v1.10.0 — Phase 2a — Master Guest entity link
    guest_id: Optional[int] = None
    # v1.10.0 — Phase 2c — Multi-vehicle list. Empty for legacy single-
    # vehicle reservations (their vehicle still appears in the
    # vehicle_plate / vehicle_model fields above).
    vehicles: List[ReservationVehicleDTO] = Field(default_factory=list)
    # v1.10.0 — Phase 2e — Early/late check-in/out flags exposed so the
    # frontend can render the toggles in edit mode and the agreed-upon
    # HH:MM. Stored in the DB since Phase 2e but previously omitted from
    # the detail response (frontend could never round-trip the value).
    early_checkin: bool = False
    late_checkout: bool = False
    late_checkout_time: Optional[str] = None


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
    # v1.10.0 Phase 2a-ext: color passthrough (propagates to GuestVehicle, not stored on CheckIn row)
    vehicle_color: Optional[str] = Field(default=None, description="Color del vehículo")

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
    property_id: str = Field(default=DEFAULT_PROPERTY_ID, description="ID de la propiedad")
    category_id: str = Field(..., description="ID de la categoría de habitación")
    check_in: date = Field(..., description="Fecha de entrada")
    stay_days: int = Field(..., ge=1, le=365, description="Días de estadía")
    client_type_id: str = Field(default="los-monges-particular", description="ID del tipo de cliente")
    room_id: Optional[str] = Field(default=None, description="ID de habitación (opcional)")
    season_id: Optional[str] = Field(default=None, description="Override de temporada (selección manual)")
    # v1.7.0 — Meal Plan (Phase 4)
    meal_plan_id: Optional[str] = Field(default=None, description="ID del plan de comidas (opcional)")
    breakfast_guests: Optional[int] = Field(default=None, ge=0, description="Cantidad de huéspedes con desayuno (OPCIONAL_PERSONA)")

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
    """Request para registrar un pago.

    Multi-currency (v1.10.0 Phase 2d): el campo `amount` representa el monto
    en la moneda con la que pagó el huésped. Si `currency_code` se provee y
    NO es la moneda base de la propiedad, el backend convierte y guarda
    AMBOS (original + base) en la transacción con snapshot del tipo de cambio.
    Si `currency_code` se omite, asume moneda base (back-compat con clientes
    pre-Phase-2d).
    """
    reserva_id: str = Field(..., description="ID de la reserva")
    amount: float = Field(..., gt=0, description="Monto del pago en la moneda elegida (mayor a 0)")
    payment_method: str = Field(..., description="EFECTIVO | TRANSFERENCIA | POS")
    reference_number: Optional[str] = Field(default=None, description="Numero de referencia (transfer/POS)")
    description: Optional[str] = Field(default=None, description="Descripcion opcional")
    # v1.10.0 Phase 2d — moneda en la que el huésped pagó. None = moneda base.
    currency_code: Optional[str] = Field(default=None, description="Código ISO 4217 (PYG, USD, BRL, ...)")

    @field_validator('payment_method')
    @classmethod
    def validate_method(cls, v: str) -> str:
        v = v.upper()
        if v not in ("EFECTIVO", "TRANSFERENCIA", "POS"):
            raise ValueError("payment_method debe ser EFECTIVO, TRANSFERENCIA o POS")
        return v

    @field_validator('currency_code')
    @classmethod
    def normalize_currency_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        return cleaned or None


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
    # v1.10.0 Phase 2d — multi-currency snapshot fields. NULL = legacy (= base ccy).
    currency_code: Optional[str] = None
    exchange_rate: Optional[float] = None
    amount_original: Optional[float] = None


# ----------------------------------------------------------------------
# v1.10.0 Phase 2d — Multi-currency schemas
# ----------------------------------------------------------------------
class CurrencyCatalogEntry(BaseModel):
    """Read-only catalogue entry (one of the 20 currencies the system knows)."""
    code: str
    name: str
    symbol: str
    decimals: int
    country: str


class AcceptedCurrencyDTO(BaseModel):
    """A currency configured for a property (with rate + activation flag)."""
    id: int
    property_id: str
    currency_code: str
    currency_name: str
    currency_symbol: str
    decimal_places: int
    exchange_rate: float
    rate_updated_at: Optional[datetime] = None
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class AcceptedCurrencyCreate(BaseModel):
    """Add a currency to a property's accepted list."""
    currency_code: str = Field(..., description="Código ISO 4217 del catálogo")
    exchange_rate: float = Field(..., gt=0, description="Tasa al base (1 unidad = N base)")
    sort_order: int = Field(default=100, ge=0)


class AcceptedCurrencyRateUpdate(BaseModel):
    """Update the rate for an existing accepted currency."""
    exchange_rate: float = Field(..., gt=0)


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


# ==========================================
# v1.6.0 Phase 3 — Room Charges & Product Inventory
# ==========================================

class ProductoCreate(BaseModel):
    """Request to create a product or service."""
    id: str = Field(..., min_length=3, description="Slug id, e.g. 'los-monges-agua-500'")
    name: str = Field(..., min_length=2)
    category: str = Field(..., description="BEBIDA | SNACK | SERVICIO | MINIBAR | OTRO")
    price: float = Field(..., ge=0)
    stock_current: Optional[int] = Field(default=None, ge=0)
    stock_minimum: Optional[int] = Field(default=None, ge=0)
    is_stocked: bool = True

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in ("BEBIDA", "SNACK", "SERVICIO", "MINIBAR", "OTRO"):
            raise ValueError("Categoria invalida")
        return v


class ProductoUpdate(BaseModel):
    """Partial update of a product. Stock_current is managed via stock adjustments."""
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    stock_minimum: Optional[int] = Field(default=None, ge=0)
    is_stocked: Optional[bool] = None
    is_active: Optional[bool] = None


class ProductoDTO(BaseModel):
    """Schema de salida para un producto."""
    id: str
    property_id: Optional[str] = None
    name: str
    category: str
    price: float
    stock_current: Optional[int] = None
    stock_minimum: Optional[int] = None
    is_stocked: bool
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AjusteStockRequest(BaseModel):
    """Request to apply a stock adjustment."""
    quantity_change: int = Field(..., description="Signed change: +N compra, -N merma")
    reason: str = Field(..., description="COMPRA | MERMA | AJUSTE")
    notes: Optional[str] = None


class AjusteInventarioDTO(BaseModel):
    """Schema de salida para un ajuste de inventario."""
    id: int
    producto_id: str
    quantity_change: int
    reason: str
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class ConsumoCreate(BaseModel):
    """Request to register a consumo against a reservation."""
    reserva_id: str
    producto_id: str
    quantity: int = Field(default=1, ge=1)
    description: Optional[str] = None


class AnularConsumoRequest(BaseModel):
    """Request to void a consumo. Reason is mandatory."""
    reason: str = Field(..., min_length=3)


class ConsumoDTO(BaseModel):
    """Schema de salida para un consumo."""
    id: int
    reserva_id: str
    producto_id: str
    producto_name: str
    quantity: int
    unit_price: float
    total: float
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    voided: bool = False
    void_reason: Optional[str] = None
    voided_at: Optional[datetime] = None
    voided_by: Optional[str] = None


class ProductoStockBajoDTO(BaseModel):
    """Product with low stock flag (stock_current <= stock_minimum)."""
    id: str
    name: str
    category: str
    stock_current: int
    stock_minimum: int


class ProductoMasVendidoDTO(BaseModel):
    """Top-selling product aggregate row."""
    producto_id: str
    producto_name: str
    units_sold: int
    revenue: float
    consumo_count: int


# ==========================================
# EMAIL (v1.8.0 — Phase 5)
# ==========================================

class SMTPConfigIn(BaseModel):
    """Request body for PUT /settings/email. Password optional: if None or empty, keep existing."""
    smtp_host: str = Field(..., min_length=1)
    smtp_port: int = Field(..., ge=1, le=65535)
    smtp_username: str = Field(..., min_length=1)
    smtp_password: Optional[str] = Field(default=None, description="Plaintext; encrypted on save. Empty string or None keeps current.")
    smtp_from_name: str = Field(..., min_length=1)
    smtp_from_email: str = Field(..., min_length=3)
    smtp_enabled: bool = False
    email_body_template: Optional[str] = None

    @field_validator("smtp_from_email")
    @classmethod
    def _validate_from_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("smtp_from_email debe ser un email válido")
        return v.strip()


class SMTPConfigOut(BaseModel):
    """Response for GET /settings/email. Password is never exposed."""
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password_set: bool = False
    smtp_from_name: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_enabled: bool = False
    email_body_template: Optional[str] = None


class SMTPTestResult(BaseModel):
    success: bool
    message: str


class SendEmailRequest(BaseModel):
    """Optional body for POST /email/reserva/{id}/enviar."""
    email: Optional[str] = Field(default=None, description="Override recipient email; persisted to reservation if guest had none")

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if "@" not in v:
            raise ValueError("El email ingresado no es válido")
        return v.strip()


class EmailLogDTO(BaseModel):
    """Single email_log row for historial responses."""
    id: int
    reserva_id: str
    recipient_email: str
    subject: str
    status: str  # ENVIADO | FALLIDO | PENDIENTE
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    sent_by: Optional[int] = None  # v1.10.0 Phase 1 Fix #2: int (was str, mismatch with users.id)
    created_at: Optional[datetime] = None


# ==========================================
# AIAgentPermission DTOs (Feature 1 — v1.9.0)
# ==========================================

class AIAgentPermissionDTO(BaseModel):
    """Per-role permissions for the AI agent's 18 tools."""
    role: str
    can_view_reservations: bool
    can_create_reservations: bool
    can_modify_reservations: bool
    can_cancel_reservations: bool
    can_view_guests: bool
    can_modify_guests: bool
    can_view_rooms: bool
    can_modify_rooms: bool
    can_modify_room_status: bool
    can_view_prices: bool
    can_modify_prices: bool
    can_view_reports: bool
    can_export_data: bool
    can_modify_settings: bool


class AIAgentPermissionUpdate(BaseModel):
    """Partial update for a role's AI permissions. All fields optional."""
    can_view_reservations: Optional[bool] = None
    can_create_reservations: Optional[bool] = None
    can_modify_reservations: Optional[bool] = None
    can_cancel_reservations: Optional[bool] = None
    can_view_guests: Optional[bool] = None
    can_modify_guests: Optional[bool] = None
    can_view_rooms: Optional[bool] = None
    can_modify_rooms: Optional[bool] = None
    can_modify_room_status: Optional[bool] = None
    can_view_prices: Optional[bool] = None
    can_modify_prices: Optional[bool] = None
    can_view_reports: Optional[bool] = None
    can_export_data: Optional[bool] = None
    can_modify_settings: Optional[bool] = None


# ==========================================
# GUEST MASTER (v1.10.0 — Phase 2a)
# ==========================================
# IMPORTANT: these schemas are for the *master* Guest entity (one row per
# person, persists across stays). The legacy CheckInCreate above represents
# the per-stay registration record (ficha) — different concept, kept as-is
# for backward compatibility with /api/v1/guests/* endpoints + PC tab_checkin.

class GuestCreate(BaseModel):
    """Request to create a new master Guest record."""
    first_name: str = Field(..., min_length=1, description="Nombres del huésped")
    last_name: str = Field(..., min_length=1, description="Apellidos del huésped")
    document_type: Optional[str] = Field(default=None, description="CI | Pasaporte | DNI | RUC | Otro")
    document_number: Optional[str] = Field(default=None, description="Número de documento")
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    nationality: Optional[str] = Field(default=None)
    country: Optional[str] = Field(default=None)
    city: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default="Direct")
    # v1.10.0 Phase 2a-ext — birthday automation hook
    birth_date: Optional[date] = Field(default=None, description="Fecha de nacimiento")
    property_id: Optional[str] = Field(default=DEFAULT_PROPERTY_ID)

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("El nombre no puede estar vacío")
        return cleaned

    @field_validator("document_number")
    @classmethod
    def _norm_doc(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return validate_document_format(v)

    @field_validator("phone")
    @classmethod
    def _norm_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return validate_phone_format(v)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if "@" not in v:
            raise ValueError("El email ingresado no es válido")
        return v


class GuestUpdate(BaseModel):
    """Partial update of a Guest. All fields optional."""
    first_name: Optional[str] = Field(default=None, min_length=1)
    last_name: Optional[str] = Field(default=None, min_length=1)
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    nationality: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    birth_date: Optional[date] = None  # v1.10.0 Phase 2a-ext
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if "@" not in v:
            raise ValueError("El email ingresado no es válido")
        return v


class GuestDTO(BaseModel):
    """Full Guest record for detail views."""
    id: int
    property_id: str
    first_name: str
    last_name: str
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    nationality: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    birth_date: Optional[date] = None  # v1.10.0 Phase 2a-ext
    is_active: bool
    total_stays: int = 0
    total_spent: float = 0.0
    last_visit_at: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GuestSearchResult(BaseModel):
    """Lightweight guest result for autocomplete / dropdowns."""
    id: int
    first_name: str
    last_name: str
    document_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    total_stays: int = 0
    label: str  # Pre-formatted "Lastname, Firstname (CI)" for display


class GuestReservationItemDTO(BaseModel):
    """Single reservation row in a guest's history view."""
    id: str
    check_in_date: date
    check_out_date: date
    stay_days: int
    room_id: str
    room_internal_code: Optional[str] = None
    status: str
    price: float
    source: Optional[str] = None


class GuestHistoryDTO(BaseModel):
    """Guest history aggregate: reservations list + totals."""
    guest: GuestDTO
    reservations: List[GuestReservationItemDTO]
    total_stays: int
    total_spent: float
    last_visit_at: Optional[date] = None
    avg_stay_length: float = 0.0


# ==========================================
# BUILDING (v1.10.0 — Phase 2a)
# ==========================================

class BuildingCreate(BaseModel):
    """Request to create a new building."""
    id: str = Field(..., min_length=3, description="Slug id, e.g. 'los-monges-anexo'")
    name: str = Field(..., min_length=2)
    description: Optional[str] = None
    floors: Optional[int] = Field(default=None, ge=1, le=200)
    sort_order: int = 0
    property_id: Optional[str] = Field(default=DEFAULT_PROPERTY_ID)


class BuildingUpdate(BaseModel):
    """Partial update of a building."""
    name: Optional[str] = Field(default=None, min_length=2)
    description: Optional[str] = None
    floors: Optional[int] = Field(default=None, ge=1, le=200)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class BuildingDTO(BaseModel):
    """Full building record."""
    id: str
    property_id: str
    name: str
    description: Optional[str] = None
    floors: Optional[int] = None
    sort_order: int = 0
    is_active: bool
    room_count: int = 0  # populated by service when listing
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ==========================================
# BILLING PROFILES (v1.10.0 — Phase 2a-ext)
# ==========================================

class BillingProfileCreate(BaseModel):
    """Request body for POST /huespedes/{guest_id}/billing."""
    label: Optional[str] = Field(default=None, description="Etiqueta legible (Personal, Empresa XYZ, etc.)")
    is_default: bool = Field(default=False)
    tax_id_type: Optional[str] = Field(default=None, description="RUC | CI | CUIT | CPF | CNPJ | NIT | Otro")
    tax_id_number: Optional[str] = Field(default=None)
    business_name: Optional[str] = Field(default=None, description="Razón Social")
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None


class BillingProfileUpdate(BaseModel):
    """Partial update — all fields optional."""
    label: Optional[str] = None
    is_default: Optional[bool] = None
    tax_id_type: Optional[str] = None
    tax_id_number: Optional[str] = None
    business_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    is_active: Optional[bool] = None


class BillingProfileDTO(BaseModel):
    """Full billing profile record."""
    id: int
    guest_id: int
    property_id: str
    label: Optional[str] = None
    is_default: bool = False
    tax_id_type: Optional[str] = None
    tax_id_number: Optional[str] = None
    business_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ==========================================
# GUEST VEHICLES (v1.10.0 — Phase 2a-ext)
# ==========================================

class GuestVehicleCreate(BaseModel):
    """Request body for POST /huespedes/{guest_id}/vehicles."""
    plate_number: str = Field(..., min_length=1, description="Chapa / patente")
    model: Optional[str] = Field(default=None, description="Modelo y año")
    color: Optional[str] = None

    @field_validator("plate_number")
    @classmethod
    def _norm_plate(cls, v: str) -> str:
        cleaned = (v or "").strip().upper()
        if not cleaned:
            raise ValueError("La chapa no puede estar vacía")
        return cleaned


class GuestVehicleUpdate(BaseModel):
    """Partial update — all fields optional."""
    plate_number: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("plate_number")
    @classmethod
    def _norm_plate(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        return cleaned or None


class GuestVehicleDTO(BaseModel):
    """Full vehicle record."""
    id: int
    guest_id: int
    property_id: str
    plate_number: str
    model: Optional[str] = None
    color: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VehicleSearchResultDTO(BaseModel):
    """Result of /vehicles/search?plate=... — vehicle + guest + active reservation if any.

    Powers the "whose car is this?" lookup AND the future OCR pipeline.
    Compact shape because the OCR webhook will likely turn this into a push
    notification on the receptionist's phone.
    """
    vehicle: GuestVehicleDTO
    guest: GuestDTO
    active_reservation: Optional[Dict[str, Any]] = None  # {id, room_id, room_internal_code, check_in_date, check_out_date}


class CheckinVehicleLink(BaseModel):
    """Body for linking a vehicle to a checkin (parking spot, key deposit)."""
    parking_spot: Optional[str] = None
    key_deposited: bool = False


class CheckinVehicleDTO(BaseModel):
    """A vehicle currently associated with a specific check-in (per-stay link)."""
    id: int
    checkin_id: int
    vehicle_id: int
    parking_spot: Optional[str] = None
    key_deposited: bool = False
    created_at: Optional[datetime] = None
    # Convenience-flattened vehicle fields for table renders
    plate_number: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
