import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Date, Float, ForeignKey, DateTime,
    Time, event, Boolean, UniqueConstraint, CheckConstraint, Index, JSON,
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from datetime import datetime
import re

# Logging centralizado
from logging_config import get_logger
logger = get_logger(__name__)

# Base de datos - Use absolute path relative to this file's location
# This ensures it works regardless of working directory
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(DB_DIR, "hotel.db")

# ========================================
# CONFIGURACIÓN SEGURA PARA CONCURRENCIA
# ========================================

# 1. Crear engine con timeout y check_same_thread deshabilitado
engine = create_engine(
    f"sqlite:///{DB_NAME}",
    echo=False,
    connect_args={
        "check_same_thread": False,  # Permitir uso multi-hilo
        "timeout": 30  # Esperar hasta 30s si hay bloqueo
    },
    pool_pre_ping=True  # Verificar conexiones antes de usar
)

# 2. Habilitar WAL Mode + foreign keys al conectar
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")  # Balance rendimiento/seguridad
    cursor.execute("PRAGMA busy_timeout=30000")  # 30s timeout en nivel SQLite
    # SQLite ships with foreign-key enforcement OFF by default. Enable it so the
    # ondelete= cascades declared on every ForeignKey actually fire (Phase 1
    # Fix #16). When the engine is later swapped for PostgreSQL, this whole
    # block is replaced and the pragma becomes a no-op via the listener target
    # — Postgres always enforces FKs.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

Base = declarative_base()

# 3. Usar scoped_session para aislamiento por hilo
session_factory = sessionmaker(bind=engine)
SessionLocal = scoped_session(session_factory)

# ==========================================
# MODELOS (Tablas)
# ==========================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)  # bcrypt hash ($2b$...). Verified by api/core/security.py:verify_password which rejects anything not starting with '$2'.
    role = Column(String)
    real_name = Column(String)


class SessionLog(Base):
    """Tracks user login/logout sessions for audit purposes."""
    __tablename__ = "session_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False, index=True)  # Unique session identifier
    username = Column(String, nullable=False, index=True)
    login_time = Column(DateTime, nullable=False, default=datetime.now)
    logout_time = Column(DateTime, nullable=True)  # Null if still active
    ip_address = Column(String, nullable=True)  # Track IP
    user_agent = Column(String, nullable=True)  # Track browser/device
    device_type = Column(String, nullable=False, default="PC")  # 'PC' or 'Mobile'
    status = Column(String, nullable=False, default="active")  # 'active' or 'closed'
    closed_reason = Column(String, nullable=True)  # 'manual_logout', 'tab_closed', 'server_restart'


class RoomCategory(Base):
    """Room categories with base pricing (Los Monges MVP)."""
    __tablename__ = "room_categories"
    id = Column(String, primary_key=True)
    # Phase 2b #FK: promoted to real ForeignKey. SQLite enforcement lands on
    # fresh init_db() / Postgres cutover (Option A — see Phase 1 cascade notes).
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    base_price = Column(Float, nullable=False)
    max_capacity = Column(Integer, nullable=False)
    # Phase 2b #JSON: was String holding JSON. SQLAlchemy JSON type handles
    # encode/decode automatically; on Postgres it becomes JSONB.
    bed_configuration = Column(JSON, nullable=True)
    amenities = Column(JSON, nullable=True)
    image_url = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    # Phase 2b #Bool: was Integer(0/1) — promoted to real Boolean. Existing
    # 0/1 ints round-trip transparently via SQLAlchemy.
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Room(Base):
    """Rooms with new schema supporting categories and multi-tenant."""
    __tablename__ = "rooms"
    id = Column(String, primary_key=True)
    # PERF-006: Added indexes for frequently filtered columns
    # Phase 2b #FK: promoted to real ForeignKey (Option A — model-only).
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    # Phase 2a #2: promoted to FK; SET NULL because the building can be retired
    # without the room disappearing (the room just becomes "unassigned").
    # Migration 012 creates the buildings table and backfills a default building
    # per property so no existing room is left orphaned.
    building_id = Column(String, ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True, index=True)
    # Phase 1 #1: SET NULL — a room can sit "uncategorized" if its category is removed.
    category_id = Column(String, ForeignKey("room_categories.id", ondelete="SET NULL"), nullable=True)
    floor = Column(Integer, nullable=True)
    room_number = Column(String, nullable=True)
    internal_code = Column(String, nullable=True)
    custom_price = Column(Float, nullable=True)
    custom_capacity = Column(Integer, nullable=True)
    custom_beds = Column(String, nullable=True)
    status = Column(String, default="available", index=True)
    status_reason = Column(String, nullable=True)
    status_changed_at = Column(DateTime, nullable=True)
    status_changed_by = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    active = Column(Boolean, default=True)
    # Phase 1 #15: enum CHECK — enforced on fresh init_db() and on Postgres migration.
    # Existing SQLite data is unaffected (no rebuild). All current values are within the set.
    __table_args__ = (
        CheckConstraint(
            "status IN ('available','occupied','maintenance','cleaning','out_of_service')",
            name="ck_rooms_status",
        ),
    )

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(String, primary_key=True) # "0001255"
    created_at = Column(DateTime, default=datetime.now)

    # PERF-006: Added indexes for frequently filtered columns
    check_in_date = Column(Date, index=True) # Fecha_Entrada
    stay_days = Column(Integer)
    guest_name = Column(String) # A_Nombre_De

    # Phase 1 #2: RESTRICT — never delete a room that has reservations.
    room_id = Column(String, ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    room_type = Column(String)

    price = Column(Float)
    arrival_time = Column(Time, nullable=True) # Hora_Llegada

    reserved_by = Column(String) # Reservado_Por
    contact_phone = Column(String) # Telefono
    contact_email = Column(String, nullable=True) # Email
    received_by = Column(String) # Recibido_Por

    status = Column(String, index=True) # Confirmada, Cancelada
    cancellation_reason = Column(String, nullable=True)
    cancelled_by = Column(String, nullable=True)

    # New fields for Los Monges / Pricing System
    # Phase 2b #FK: promoted to real ForeignKey (Option A — model-only). Audit
    # confirmed 0 orphans before promotion. SQLite enforcement lands on table
    # rebuild or Postgres cutover.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=True)
    # Phase 2a Bonus #3.1: promote logical FKs that were String-only. SET NULL
    # because the catalog row can be retired without losing the reservation
    # (the price_breakdown snapshot already captures the historical context).
    # Model-only — see Phase 1 cascade note: SQLite won't enforce until a fresh
    # init_db() or the Postgres cutover. Audit confirmed zero orphan rows
    # before promoting (see Phase 2a sign-off in CHANGELOG).
    category_id = Column(String, ForeignKey("room_categories.id", ondelete="SET NULL"), nullable=True)
    client_type_id = Column(String, ForeignKey("client_types.id", ondelete="SET NULL"), nullable=True)
    contract_id = Column(String, ForeignKey("client_contracts.id", ondelete="SET NULL"), nullable=True)
    # Phase 2b #JSON: was String holding JSON. Auto-encodes/decodes via ORM.
    price_breakdown = Column(JSON, nullable=True)
    season_applied = Column(String, nullable=True)
    original_price = Column(Float, nullable=True)
    discount_amount = Column(Float, nullable=True)
    final_price = Column(Float, nullable=True)

    # Parking & Source
    parking_needed = Column(Boolean, default=False)
    vehicle_model = Column(String, nullable=True)
    vehicle_plate = Column(String, nullable=True)
    source = Column(String, default="Direct")
    external_id = Column(String, nullable=True)

    # v1.5.0 — Channel Manager v2 (Phase 2)
    ota_booking_id = Column(String, nullable=True)  # OTA-specific reference (Booking.com booking #, etc.)
    needs_review = Column(Boolean, default=False, index=True)  # set when UID disappears from OTA feed
    review_reason = Column(String, nullable=True)

    # v1.7.0 — Meal Plan (Phase 4)
    # Phase 1 #3: SET NULL — meal plan can be retired; reservation keeps its price snapshot.
    meal_plan_id = Column(String, ForeignKey("meal_plans.id", ondelete="SET NULL"), nullable=True, index=True)
    breakfast_guests = Column(Integer, nullable=True)  # # of guests eating breakfast (0..guests_count)

    # v1.10.0 — Phase 2a — Guest master entity
    # SET NULL because guest_name + contact_phone + contact_email are kept as
    # frozen-at-booking-time snapshots on this row — the link to the master
    # Guest is a "nice to have" for history queries, not load-bearing data.
    # Backfilled by migration 011 from existing (property_id, guest_name) tuples.
    guest_id = Column(Integer, ForeignKey("guests.id", ondelete="SET NULL"), nullable=True, index=True)


class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 2b #Type: Date → DateTime so we capture hora_ingreso, not only the date.
    # Existing rows store ISO date strings ('YYYY-MM-DD') which SQLAlchemy reads
    # back as datetime at 00:00:00 — no data migration needed.
    created_at = Column(DateTime, default=datetime.now)  # Fecha+Hora_Ingreso

    # Phase 1 #4: RESTRICT — checkins are guest registry data, never lose them on room deletion.
    room_id = Column(String, ForeignKey("rooms.id", ondelete="RESTRICT"))
    # Phase 1 #5: SET NULL — checkins predate FEAT-LINK-01 and can exist without a reservation.
    # Cancelling/deleting a reservation should not erase the guest registration record.
    reservation_id = Column(String, ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True, index=True)
    check_in_time = Column(Time) # Hora
    
    last_name = Column(String)
    first_name = Column(String)
    nationality = Column(String)
    birth_date = Column(Date, nullable=True)
    
    origin = Column(String)
    destination = Column(String)
    civil_status = Column(String)
    document_number = Column(String, index=True)
    country = Column(String)
    
    contact_phone = Column(String, nullable=True) # Telefono
    contact_email = Column(String, nullable=True) # Email

    billing_name = Column(String) # Facturacion_Nombre
    billing_ruc = Column(String) # Facturacion_RUC

    vehicle_model = Column(String)
    vehicle_plate = Column(String)

    digital_signature = Column(String) # Base64 o "Pendiente"

    # v1.10.0 — Phase 2a — Guest master entity
    # SET NULL because the per-stay record (this row) keeps the snapshot of
    # last_name/first_name/document_number/billing — even if the guest record
    # is later merged or deleted, the historical ficha stays intact for audit.
    guest_id = Column(Integer, ForeignKey("guests.id", ondelete="SET NULL"), nullable=True, index=True)

    # v1.10.0 — Phase 2a-ext — link to the BillingProfile selected for this stay.
    # SET NULL: the legacy billing_name/billing_ruc columns above stay as the
    # frozen snapshot, so even if the profile is later deleted the ficha keeps
    # the invoice details that were used at the time of registration.
    billing_profile_id = Column(
        Integer, ForeignKey("billing_profiles.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )


class CajaSesion(Base):
    """Cash register session. Tracks open/close of cash till per user."""
    __tablename__ = "caja_sesion"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #11: RESTRICT — never delete a user with caja sessions (financial audit).
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    opened_at = Column(DateTime, default=datetime.now, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    opening_balance = Column(Float, nullable=False, default=0.0)
    closing_balance_declared = Column(Float, nullable=True)
    closing_balance_expected = Column(Float, nullable=True)
    difference = Column(Float, nullable=True)
    status = Column(String, default="ABIERTA", index=True)  # ABIERTA | CERRADA
    notes = Column(String, nullable=True)
    # Phase 1 #15: enum CHECK on status (Postgres migration will translate to ENUM).
    __table_args__ = (
        CheckConstraint("status IN ('ABIERTA','CERRADA')", name="ck_caja_sesion_status"),
    )


class Transaccion(Base):
    """Immutable payment transaction. Voided=True is the only way to nullify."""
    __tablename__ = "transaccion"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #6: RESTRICT — never delete a reservation with payments (financial audit).
    reserva_id = Column(String, ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=True, index=True)
    # Phase 1 #7: RESTRICT — caja sessions are immutable post-close; never delete one with txns.
    caja_sesion_id = Column(Integer, ForeignKey("caja_sesion.id", ondelete="RESTRICT"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False, index=True)  # EFECTIVO | TRANSFERENCIA | POS
    reference_number = Column(String, nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    created_by = Column(String, nullable=True)
    voided = Column(Boolean, default=False, index=True)
    void_reason = Column(String, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(String, nullable=True)
    # Phase 1 #15: enum CHECK on payment_method.
    # Phase 1 #19: composite index for the saldo() query that filters by reserva + voided.
    __table_args__ = (
        CheckConstraint(
            "payment_method IN ('EFECTIVO','TRANSFERENCIA','POS')",
            name="ck_transaccion_payment_method",
        ),
        Index("idx_transaccion_reserva_voided", "reserva_id", "voided"),
    )


class SystemSetting(Base):
    """System settings per property (Los Monges MVP)."""
    __tablename__ = "system_settings"
    id = Column(String, primary_key=True)
    # Phase 2b #FK: promoted to real ForeignKey (Option A — model-only).
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    setting_key = Column(String, nullable=False)
    setting_value = Column(String, nullable=True)
    setting_type = Column(String, default="string")
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = Column(String, nullable=True)
    # Phase 1 #10: settings must be unique per (property, key) — service was already
    # doing this implicitly via upsert; constraint makes it explicit + indexable.
    __table_args__ = (
        UniqueConstraint("property_id", "setting_key", name="uq_system_settings_property_key"),
    )


class ClientType(Base):
    """Client types for dynamic pricing (Los Monges)."""
    __tablename__ = "client_types"
    id = Column(String, primary_key=True)
    # Phase 2b #FK: promoted to real ForeignKey.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    default_discount_percent = Column(Float, default=0.0)
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    requires_contract = Column(Boolean, default=False)
    min_rooms_per_booking = Column(Integer, default=1)
    color = Column(String, default="#6B7280")
    icon = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class ClientContract(Base):
    """Corporate contracts."""
    __tablename__ = "client_contracts"
    id = Column(String, primary_key=True)
    # Phase 2b #FK: promoted to real ForeignKey.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    # Phase 1 #11-bis: RESTRICT — never delete a client_type that has contracts attached.
    client_type_id = Column(String, ForeignKey("client_types.id", ondelete="RESTRICT"), nullable=False)
    company_name = Column(String, nullable=False)
    ruc = Column(String, nullable=True)
    contact_name = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    billing_address = Column(String, nullable=True)
    negotiated_discount_percent = Column(Float, nullable=False)
    credit_days = Column(Integer, default=0)
    credit_limit = Column(Float, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    active = Column(Boolean, default=True)


class PricingSeason(Base):
    """Seasonal pricing rules."""
    __tablename__ = "pricing_seasons"
    id = Column(String, primary_key=True)
    # Phase 2b #FK: promoted to real ForeignKey.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    price_modifier = Column(Float, nullable=False)
    # Phase 2b #JSON: was String holding JSON. Auto-encodes/decodes via ORM.
    applies_to_categories = Column(JSON, nullable=True)
    priority = Column(Integer, default=0)
    color = Column(String, default="#F59E0B")
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class PriceCalculation(Base):
    """Audit log for price calculations."""
    __tablename__ = "price_calculations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(String, nullable=True)
    # Phase 2b #FK: promoted to real ForeignKey.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    category_id = Column(String, nullable=True)
    category_name = Column(String, nullable=True)
    base_price_per_night = Column(Float, nullable=False)
    nights = Column(Integer, nullable=False)
    base_total = Column(Float, nullable=False)
    client_type_id = Column(String, nullable=True)
    client_type_name = Column(String, nullable=True)
    client_type_modifier = Column(Float, default=1.0)
    client_discount_amount = Column(Float, default=0.0)
    contract_id = Column(String, nullable=True)
    contract_name = Column(String, nullable=True)
    season_id = Column(String, nullable=True)
    season_name = Column(String, nullable=True)
    season_modifier = Column(Float, default=1.0)
    season_adjustment_amount = Column(Float, default=0.0)
    special_discount_percent = Column(Float, default=0.0)
    special_discount_reason = Column(String, nullable=True)
    special_discount_amount = Column(Float, default=0.0)
    final_price = Column(Float, nullable=False)
    # Phase 2b #JSON: was String holding JSON. Auto-encodes/decodes via ORM.
    calculation_details = Column(JSON, nullable=True)
    calculated_at = Column(DateTime, default=datetime.now)
    calculated_by = Column(String, nullable=True)



class Property(Base):
    """Properties (Hotels) with check-in/check-out configuration."""
    __tablename__ = "properties"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    # Phase 2b #slug: backfilled WHERE NULL via migration 014, then promoted to
    # NOT NULL. UNIQUE was already declared in Phase 2a. Canonical URL key for
    # the future SaaS layer (e.g. `app.hotel.com/los-monges/`).
    slug = Column(String, unique=True, nullable=False)
    display_mode = Column(String, default="category")
    theme_background = Column(String, default="#FFFFFF")
    theme_text = Column(String, default="#000000")
    theme_primary = Column(String, default="#1E3A5F")
    check_in_start = Column(String, default="07:00")
    check_in_end = Column(String, default="22:00")
    check_out_time = Column(String, default="10:00")
    # Phase 2b: `breakfast_included` REMOVED (was deprecated v1.7). Migration 014
    # drops the SQLite column via DROP COLUMN (SQLite 3.35+). The whole "should
    # the hotel include breakfast?" question is now answered by `meals_enabled`
    # + `meal_inclusion_mode` below.
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    parking_available = Column(Boolean, default=True)
    # v1.7.0 — Meal Plan Configuration (Phase 4)
    # Phase 2b #Bool: Integer(0/1) → Boolean. Master on/off for meal features.
    meals_enabled = Column(Boolean, default=False)
    meal_inclusion_mode = Column(String, nullable=True)  # INCLUIDO | OPCIONAL_PERSONA | OPCIONAL_HABITACION
    timezone = Column(String, default="America/Asuncion")
    currency = Column(String, default="PYG")
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    facebook_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    active = Column(Boolean, default=True)


class ICalFeed(Base):
    """iCal feed URLs for OTA sync per room (Booking.com, Airbnb, Vrbo, Expedia, Custom)."""
    __tablename__ = "ical_feeds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #12: CASCADE — feeds are room-bound config; if room is gone (after #2/#4 gates),
    # the feed has no anchor.
    room_id = Column(String, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    source = Column(String, nullable=False)  # "Booking.com" | "Airbnb" | "Vrbo" | "Expedia" | "Custom" | <free text>
    ical_url = Column(String, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)  # last successful sync
    # Phase 2b #Bool: Integer(0/1) → Boolean.
    sync_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    # v1.5.0 — health tracking (Phase 2)
    last_sync_status = Column(String, default="NEVER", index=True)  # OK | ERROR | NEVER
    last_sync_error = Column(String, nullable=True)  # truncated to 500 chars
    consecutive_failures = Column(Integer, default=0)
    last_sync_attempted_at = Column(DateTime, nullable=True)  # last attempt (success or fail)
    # Phase 1 #15: enum CHECK on last_sync_status.
    __table_args__ = (
        CheckConstraint(
            "last_sync_status IN ('OK','ERROR','NEVER')",
            name="ck_ical_feeds_last_sync_status",
        ),
    )


class ICalSyncLog(Base):
    """Audit trail for every iCal sync attempt (v1.5.0 — Phase 2).

    Pruned to last 100 entries per feed_id.
    """
    __tablename__ = "ical_sync_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #13: CASCADE — sync logs are pure operational debug, die with their feed.
    feed_id = Column(Integer, ForeignKey("ical_feeds.id", ondelete="CASCADE"), nullable=False, index=True)
    attempted_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    status = Column(String, nullable=False)  # OK | ERROR
    created_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    flagged_for_review_count = Column(Integer, default=0)
    conflicts_detected = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    duration_ms = Column(Integer, default=0)


class Producto(Base):
    """Product catalog (v1.6.0 — Phase 3).

    Represents a sellable product or service: drinks, snacks, minibar items,
    laundry, late-checkout fees, etc. `is_stocked=True` for physical items
    whose inventory is tracked; `False` for services (no stock counter).
    """
    __tablename__ = "producto"
    id = Column(String, primary_key=True)
    # Phase 1 #17: RESTRICT — properties don't get hard-deleted; force explicit cleanup.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)  # BEBIDA|SNACK|SERVICIO|MINIBAR|OTRO
    price = Column(Float, nullable=False, default=0.0)  # Current unit price in Gs
    stock_current = Column(Integer, nullable=True)  # null if is_stocked=False
    stock_minimum = Column(Integer, nullable=True)  # alert threshold
    is_stocked = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Phase 1 #15: enum CHECK on category.
    # Phase 1 #19: composite index for low-stock query (filters by active + property).
    __table_args__ = (
        CheckConstraint(
            "category IN ('BEBIDA','SNACK','SERVICIO','MINIBAR','OTRO')",
            name="ck_producto_category",
        ),
        Index("idx_producto_property_active", "property_id", "is_active"),
    )


class Consumo(Base):
    """Charge line added to a reservation (v1.6.0 — Phase 3).

    Represents a guest consumption or service charged to the room.
    Immutable — only voided, never updated after creation.
    Stock is decremented on registration, restored on void.
    """
    __tablename__ = "consumo"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #8: RESTRICT — never delete a reservation with consumos (folio/billing audit).
    reserva_id = Column(String, ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False, index=True)
    # Phase 1 #9: RESTRICT — soft-delete via Producto.is_active=False; never hard-delete.
    producto_id = Column(String, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=False, index=True)
    producto_name = Column(String, nullable=False)  # snapshot at registration time
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)  # snapshot at registration time
    total = Column(Float, nullable=False)  # quantity * unit_price
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    created_by = Column(String, nullable=True)
    voided = Column(Boolean, default=False, index=True)
    void_reason = Column(String, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(String, nullable=True)
    # Phase 1 #19: composite index for the saldo() folio query that filters by reserva + voided.
    __table_args__ = (
        Index("idx_consumo_reserva_voided", "reserva_id", "voided"),
    )


class AjusteInventario(Base):
    """Stock adjustment log (v1.6.0 — Phase 3).

    Records every change to product stock for audit purposes: purchases,
    losses (merma), corrections. quantity_change can be positive or negative.
    """
    __tablename__ = "ajuste_inventario"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #10: RESTRICT — soft-delete via Producto.is_active=False; never hard-delete.
    producto_id = Column(String, ForeignKey("producto.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity_change = Column(Integer, nullable=False)  # signed
    reason = Column(String, nullable=False)  # COMPRA | MERMA | AJUSTE
    notes = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    # Phase 1 #15: enum CHECK on reason.
    # Phase 1 #19: composite index for stock history (per-product chronological view).
    __table_args__ = (
        CheckConstraint(
            "reason IN ('COMPRA','MERMA','AJUSTE')",
            name="ck_ajuste_inventario_reason",
        ),
        Index("idx_ajuste_producto_created", "producto_id", "created_at"),
    )


class MealPlan(Base):
    """Meal plan catalog (v1.7.0 — Phase 4).

    Plans represent breakfast / half-board / full-board offerings. A plan has
    either a per-person OR per-room per-night surcharge. `SOLO_HABITACION` is
    always seeded with zero surcharge so the reservation form has a fallback.

    `applies_to_mode` filters which plans are valid under the current hotel
    `meal_inclusion_mode`:
      - ANY:                valid always (e.g. SOLO_HABITACION)
      - INCLUIDO:           visible only when mode=INCLUIDO (auto-seeded CON_DESAYUNO)
      - OPCIONAL_PERSONA:   visible when mode=OPCIONAL_PERSONA
      - OPCIONAL_HABITACION: visible when mode=OPCIONAL_HABITACION
    """
    __tablename__ = "meal_plans"
    id = Column(String, primary_key=True)
    # Phase 1 #18: RESTRICT — properties don't get hard-deleted; force explicit cleanup.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String, nullable=False)  # CON_DESAYUNO, MEDIA_PENSION, SOLO_HABITACION, etc.
    name = Column(String, nullable=False)  # Display label
    description = Column(String, nullable=True)
    surcharge_per_person = Column(Float, nullable=False, default=0.0)  # PYG per person per night
    surcharge_per_room = Column(Float, nullable=False, default=0.0)  # PYG per room per night
    applies_to_mode = Column(String, nullable=False, default="ANY")  # ANY | INCLUIDO | OPCIONAL_PERSONA | OPCIONAL_HABITACION
    # Phase 2b #Bool: Integer(0/1) → Boolean. is_system=True for seeded/protected plans.
    is_system = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Phase 1 #9 (audit ID): close model/migration drift — UNIQUE(property_id, code) was
    # declared in migration 005 SQL but missing from the model. Fresh init_db() now
    # picks it up too. Phase 1 #15: enum CHECK on applies_to_mode.
    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_meal_plans_property_code"),
        CheckConstraint(
            "applies_to_mode IN ('ANY','INCLUIDO','OPCIONAL_PERSONA','OPCIONAL_HABITACION')",
            name="ck_meal_plans_applies_to_mode",
        ),
    )


class EmailLog(Base):
    """
    Audit trail for outbound reservation-confirmation emails (v1.8.0 — Phase 5).

    Append-only. Never updated except:
      - PENDIENTE → ENVIADO (background success) sets sent_at
      - PENDIENTE → FALLIDO (background error) sets error_message

    Rate-limit window (3 per reserva per hour) counts only status='ENVIADO'.
    """
    __tablename__ = "email_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #14: RESTRICT — email is communication audit; never delete a reservation that was emailed.
    reserva_id = Column(String, ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False, index=True)
    recipient_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDIENTE", index=True)  # ENVIADO | FALLIDO | PENDIENTE
    error_message = Column(String, nullable=True)
    sent_at = Column(DateTime, nullable=True, index=True)
    # v1.10.0 — Phase 1 Fix #2: was String (mismatched users.id Integer). Existing
    # data was numeric-string only (e.g. '1'), migrated by 009_fix_email_log_sent_by.
    # Phase 1 #15 (cascade): SET NULL — email log survives user deletion (only attribution lost).
    sent_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    # Phase 1 #15 (CHECK): enum on status.
    # Phase 1 #19: composite index for the rate-limit query
    # (filter reserva_id + status='ENVIADO' + sent_at>cutoff).
    __table_args__ = (
        CheckConstraint(
            "status IN ('ENVIADO','FALLIDO','PENDIENTE')",
            name="ck_email_log_status",
        ),
        Index("idx_email_log_reserva_status_sent", "reserva_id", "status", "sent_at"),
    )


class RoomStatusLog(Base):
    """Append-only audit trail of room status changes (v1.9.0 — Feature 3).

    Each PATCH /rooms/{id}/status writes one row capturing the transition
    (previous_status -> new_status), the operator who triggered it
    (changed_by stores username, matching the existing room.status_changed_by
    convention), and an optional reason. Used by the Admin Habitaciones page
    for the per-room change history sub-section.
    """
    __tablename__ = "room_status_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 1 #16: CASCADE — log dies with the room it audits (room deletion already gated by #2/#4).
    room_id = Column(String, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_status = Column(String, nullable=True)  # nullable: very first status set has no prior value
    new_status = Column(String, nullable=False)
    changed_by = Column(String, nullable=True)  # username (matches room.status_changed_by)
    reason = Column(String, nullable=True)
    changed_at = Column(DateTime, default=datetime.now, index=True)
    # Phase 1 #19: composite index for the per-room history endpoint
    # (GET /rooms/{id}/status-log ordered by changed_at DESC).
    __table_args__ = (
        Index("idx_room_status_log_room_changed", "room_id", "changed_at"),
    )


class AIAgentPermission(Base):
    """Permissions for AI Agents."""
    __tablename__ = "ai_agent_permissions"
    id = Column(String, primary_key=True)
    # Phase 1 #19 (cascade): CASCADE — permissions are pure config; meaningless without the property.
    property_id = Column(String, ForeignKey("properties.id", ondelete="CASCADE"), nullable=True)
    role = Column(String, nullable=False)
    # Phase 2b #Bool: all 14 can_* + requires_confirmation flags Integer(0/1) → Boolean.
    # Reads from existing 0/1 data round-trip transparently via the ORM.
    can_view_reservations = Column(Boolean, default=True)
    can_create_reservations = Column(Boolean, default=True)
    can_modify_reservations = Column(Boolean, default=False)
    can_cancel_reservations = Column(Boolean, default=False)
    can_view_guests = Column(Boolean, default=True)
    can_modify_guests = Column(Boolean, default=False)
    can_view_rooms = Column(Boolean, default=True)
    can_modify_rooms = Column(Boolean, default=False)
    can_modify_room_status = Column(Boolean, default=False)
    can_view_prices = Column(Boolean, default=True)
    can_modify_prices = Column(Boolean, default=False)
    can_view_reports = Column(Boolean, default=True)
    can_export_data = Column(Boolean, default=False)
    can_modify_settings = Column(Boolean, default=False)
    requires_confirmation = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # Phase 1 #10 (audit ID): UNIQUE(property_id, role) was assumed by the service but
    # never enforced. Adding it now closes a silent-data-corruption hole.
    __table_args__ = (
        UniqueConstraint("property_id", "role", name="uq_ai_agent_permissions_property_role"),
    )


class MigrationHistory(Base):
    """Tracks applied migrations (managed by scripts/run_migrations.py).

    Modelled here in v1.10.0 (Phase 1 #20) so that init_db() creates this table
    on a fresh install — previously the runner created it implicitly on first
    use, which meant a fresh DB was missing the table until the first migration
    ran. Having the model here also makes the schema completely self-documenting
    and eases the future Alembic migration (`alembic_version` will replace this).
    """
    __tablename__ = "migration_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    applied_at = Column(DateTime, default=datetime.now)
    applied_by = Column(String, default="run_migrations.py")
    # Phase 2b #Bool: Integer(0/1) → Boolean for consistency with the rest of the schema.
    success = Column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("version", "name", name="uq_migration_history_version_name"),
    )


class Guest(Base):
    """Guest master entity (v1.10.0 — Phase 2a).

    Represents the *person* who stays at the hotel — across multiple visits,
    multiple reservations, and multiple check-ins. Distinct from `CheckIn`,
    which is the per-stay registration (ficha) record.

    Identity model
    --------------
    Per Phase 2a Q1 decision: **auto-ID, no business-key UNIQUE**. A future
    de-dup/merge tool will reconcile guests that turn out to be the same person.
    Today, the same physical person who stays twice with slightly different
    name spellings ("Juan Perez" vs "Juan Pérez") will live as two separate
    rows until merged. This is the right tradeoff for v1: avoids forcing
    receptionists to fight UNIQUE-constraint failures during a real check-in.

    Per-tenant isolation
    --------------------
    Per Phase 2a Q1 decision: **scope is per-hotel**. A person who stays at
    Hotel A and Hotel B = two separate Guest rows. The eventual SaaS schema
    is schema-per-tenant, so cross-hotel guest reuse would not work anyway.

    Snapshot pattern preserved
    --------------------------
    `reservations.guest_name` and `reservations.contact_email` (and the
    equivalent fields on `checkins`) stay as **frozen-at-booking-time
    snapshots**. The Guest entity is the *living* version. This mirrors the
    consumo.producto_name + unit_price pattern (skill §2 "Snapshot pattern").
    """
    __tablename__ = "guests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Phase 2a — RESTRICT mirrors the rest of the property_id FKs (skill §2).
    # Properties are never hard-deleted; Guest rows would be lost.
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Identity
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    document_type = Column(String, nullable=True)      # CI | Passport | DNI | RUC | etc.
    document_number = Column(String, nullable=True)    # nullable: OTA guests often arrive without one

    # Contact
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # Origin
    nationality = Column(String, nullable=True)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)

    # Demographic — added in v1.10.0 Phase 2a-ext.
    # FUTURE: Birthday greeting automation
    # When birth_date is set, a scheduled job could:
    #   1. Query guests with birth_date matching today (any year)
    #   2. Check if guest has an active or upcoming reservation
    #   3. Send birthday greeting + special offer via email/WhatsApp
    #   4. Optionally auto-apply a discount or complimentary item (drink, etc.)
    # Tracked in ROADMAP.md "Birthday automation" backlog item.
    birth_date = Column(Date, nullable=True)

    # Metadata
    notes = Column(String, nullable=True)
    source = Column(String, default="Direct")           # Direct | Booking.com | Airbnb | Walk-in | etc.
    is_active = Column(Boolean, default=True)           # soft delete (per skill §2 — real Boolean, not Integer)

    # Aggregates (denormalized for cheap dashboard rendering — refreshed by
    # GuestService.refresh_aggregates whenever a reservation/checkin lands).
    # Initialised to 0 / NULL on creation. NOT load-bearing — exact values
    # live on the related rows; these are convenience.
    total_stays = Column(Integer, default=0)
    total_spent = Column(Float, default=0.0)
    last_visit_at = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Indexes for the search workflow (reception types and finds within 1-2 chars).
    # Per skill §2 "composite indexes": match the actual filter shape — receptionists
    # always include property_id (single-tenant for now, but the future SaaS layer
    # will rely on these indexes scoping the scan to one tenant's row set).
    __table_args__ = (
        Index("idx_guests_property_lastname",  "property_id", "last_name"),
        Index("idx_guests_property_document",  "property_id", "document_number"),
        Index("idx_guests_property_email",     "property_id", "email"),
        Index("idx_guests_property_phone",     "property_id", "phone"),
        Index("idx_guests_property_active",    "property_id", "is_active"),
    )


class Building(Base):
    """Building / wing within a property (v1.10.0 — Phase 2a).

    Hotels with annexes, separate buildings, or distinct wings need to group
    rooms beyond the floor + category dimensions. This is the table for that.

    `rooms.building_id` was a dead column referencing nothing pre-v1.10. Phase 2a
    creates this table, seeds one default building per property ("Edificio
    Principal"), backfills every room to that default, and promotes the FK.
    """
    __tablename__ = "buildings"
    id = Column(String, primary_key=True)  # e.g. "los-monges-principal"
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    floors = Column(Integer, nullable=True)             # number of floors (informational)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("property_id", "name", name="uq_buildings_property_name"),
        Index("idx_buildings_property_active", "property_id", "is_active"),
    )


class BillingProfile(Base):
    """Reusable invoice profile attached to a Guest (v1.10.0 — Phase 2a-ext).

    A guest can carry multiple billing profiles (Personal CI for individual
    invoices, RUC + Razón Social for their company, a different identity for
    cross-border travel). Pre-Phase-2a-ext the legacy `checkins.billing_name`
    + `checkins.billing_ruc` columns held this data — they're kept as the
    frozen-at-registration snapshot, while this table is the *living* version.

    Country-flexible
    ----------------
    `tax_id_type` is free-text (no enum) so each property can use the local
    tax-document name without needing a model change:
      - "RUC"   — Paraguay
      - "CI"    — Paraguay (cédula de identidad, individual factura)
      - "CUIT"  — Argentina
      - "CPF"   — Brasil (individuals)
      - "CNPJ"  — Brasil (companies)
      - "NIT"   — Bolivia / others
      - … plus whatever future hotels need

    `is_default`
    ------------
    Exactly one profile per guest may be the default — the one that
    auto-selects in the checkin form unless the recepcionist picks another.
    Service-level enforced (`set_default` clears the flag on siblings).
    """
    __tablename__ = "billing_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    guest_id = Column(Integer, ForeignKey("guests.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)

    # Profile identification
    label = Column(String, nullable=True)               # "Personal", "Empresa XYZ"
    is_default = Column(Boolean, default=False)

    # Tax identification (flexible per country)
    tax_id_type = Column(String, nullable=True)         # RUC | CI | CUIT | CPF | CNPJ | NIT
    tax_id_number = Column(String, nullable=True)       # the actual digits / format
    business_name = Column(String, nullable=True)       # Razón Social / Razão Social

    # Address (some countries print it on the invoice)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, nullable=True)

    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_billing_guest_active", "guest_id", "is_active"),
        Index("idx_billing_property", "property_id"),
        # Tax-id lookup ("does this RUC already exist for this hotel?") — composite
        # so the same RUC can theoretically appear under two different guests
        # (corporate + personal accounts of the same person are possible).
        Index("idx_billing_property_tax_id", "property_id", "tax_id_number"),
    )


class GuestVehicle(Base):
    """Vehicle registered to a Guest (v1.10.0 — Phase 2a-ext).

    A guest can register up to 5 vehicles (limit enforced at the service
    layer — a familia con 3 autos + 2 motos is a real edge case but more
    than that crosses into "this is a fleet, not a personal vehicle list").

    Why per-guest, not per-checkin
    ------------------------------
    The legacy `checkins.vehicle_model` + `checkins.vehicle_plate` captured
    "the car for THIS visit". That works for one car at a time but loses the
    relationship across stays — the same car shows up as a new entry every
    time the guest returns. With this table, we register the car once and
    just link it to each visit (via `checkin_vehicles`).

    Future
    ------
    The `idx_vehicle_property_plate` index is built for the OCR scenario:
    a camera at the entrance reads a plate, the system queries this table
    by `(property_id, plate_number)`, and identifies the arriving guest
    + their active reservation in O(log n). See ROADMAP.md "OCR vehicle
    recognition" backlog item.
    """
    __tablename__ = "guest_vehicles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    guest_id = Column(Integer, ForeignKey("guests.id", ondelete="CASCADE"), nullable=False)
    property_id = Column(String, ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)

    # Vehicle identification — plate is the canonical lookup key
    plate_number = Column(String, nullable=False)       # "ABC-123", "XYZ 4567"
    model = Column(String, nullable=True)               # "Toyota Corolla 2020"
    color = Column(String, nullable=True)               # "Blanco" / "Negro"

    # Metadata
    is_active = Column(Boolean, default=True)           # soft delete
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_vehicle_guest", "guest_id"),
        # Property + plate is THE hot lookup ("whose car is this?" / OCR).
        # Not declared UNIQUE because two guests might legitimately share a
        # car (couple registers same plate under both names) — service-level
        # de-dup is enough.
        Index("idx_vehicle_property_plate", "property_id", "plate_number"),
        Index("idx_vehicle_guest_active", "guest_id", "is_active"),
    )


class CheckinVehicle(Base):
    """Per-stay vehicle ↔ checkin link (v1.10.0 — Phase 2a-ext).

    N:M between checkins and guest_vehicles. A checkin records WHICH of the
    guest's registered vehicles they brought THIS time, plus visit-specific
    data (parking spot, key deposited for valet).

    UNIQUE on (checkin_id, vehicle_id) prevents the same car from appearing
    twice on one checkin. To bring 2 cars on one stay → 2 rows (one per
    vehicle).
    """
    __tablename__ = "checkin_vehicles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    checkin_id = Column(Integer, ForeignKey("checkins.id", ondelete="CASCADE"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("guest_vehicles.id", ondelete="CASCADE"), nullable=False)

    # Per-visit parking metadata (optional — a hotel without valet may leave both NULL)
    parking_spot = Column(String, nullable=True)        # "A-12", "Garage 2", "Calle"
    key_deposited = Column(Boolean, default=False)      # valet: did the guest leave the key?

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("checkin_id", "vehicle_id", name="uq_checkin_vehicle"),
        Index("idx_checkin_vehicles_checkin", "checkin_id"),
        Index("idx_checkin_vehicles_vehicle", "vehicle_id"),
    )



# ==========================================
# MIGRACIÓN
# ==========================================

def clean_days(val):
    try:
        match = re.search(r'\d+', str(val))
        return int(match.group()) if match else 1
    except: return 1

def init_db():
    """Create all database tables. Data seeding is handled by scripts/seed_monges.py."""
    Base.metadata.create_all(engine)
    logger.info("Database tables created")

if __name__ == "__main__":
    init_db()
