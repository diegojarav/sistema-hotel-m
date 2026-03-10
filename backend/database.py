import os
from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, DateTime, Time, event, Boolean
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

# 2. Habilitar WAL Mode al conectar
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")  # Balance rendimiento/seguridad
    cursor.execute("PRAGMA busy_timeout=30000")  # 30s timeout en nivel SQLite
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
    password = Column(String, nullable=False) # Plain text por compatibilidad v1, upgradear a hash después
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
    property_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    base_price = Column(Float, nullable=False)
    max_capacity = Column(Integer, nullable=False)
    bed_configuration = Column(String, nullable=True)  # JSON
    amenities = Column(String, nullable=True)  # JSON
    image_url = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Room(Base):
    """Rooms with new schema supporting categories and multi-tenant."""
    __tablename__ = "rooms"
    id = Column(String, primary_key=True)
    # PERF-006: Added indexes for frequently filtered columns
    property_id = Column(String, nullable=False, index=True)
    building_id = Column(String, nullable=True)
    category_id = Column(String, ForeignKey("room_categories.id"), nullable=True)
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
    active = Column(Integer, default=1)

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(String, primary_key=True) # "0001255"
    created_at = Column(DateTime, default=datetime.now)

    # PERF-006: Added indexes for frequently filtered columns
    check_in_date = Column(Date, index=True) # Fecha_Entrada
    stay_days = Column(Integer)
    guest_name = Column(String) # A_Nombre_De

    room_id = Column(String, ForeignKey("rooms.id"), index=True)
    room_type = Column(String)

    price = Column(Float)
    arrival_time = Column(Time, nullable=True) # Hora_Llegada

    reserved_by = Column(String) # Reservado_Por
    contact_phone = Column(String) # Telefono
    received_by = Column(String) # Recibido_Por

    status = Column(String, index=True) # Confirmada, Cancelada
    cancellation_reason = Column(String, nullable=True)
    cancelled_by = Column(String, nullable=True)

    # New fields for Los Monges / Pricing System
    property_id = Column(String, nullable=True)
    category_id = Column(String, nullable=True)
    client_type_id = Column(String, nullable=True)
    contract_id = Column(String, nullable=True)
    price_breakdown = Column(String, nullable=True) # JSON
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

class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(Date) # Fecha_Ingreso

    room_id = Column(String, ForeignKey("rooms.id"))
    reservation_id = Column(String, ForeignKey("reservations.id"), nullable=True, index=True)
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
    
    billing_name = Column(String) # Facturacion_Nombre
    billing_ruc = Column(String) # Facturacion_RUC
    
    vehicle_model = Column(String)
    vehicle_plate = Column(String)
    
    digital_signature = Column(String) # Base64 o "Pendiente"


class SystemSetting(Base):
    """System settings per property (Los Monges MVP)."""
    __tablename__ = "system_settings"
    id = Column(String, primary_key=True)
    property_id = Column(String, nullable=False)
    setting_key = Column(String, nullable=False)
    setting_value = Column(String, nullable=True)
    setting_type = Column(String, default="string")
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = Column(String, nullable=True)


class ClientType(Base):
    """Client types for dynamic pricing (Los Monges)."""
    __tablename__ = "client_types"
    id = Column(String, primary_key=True)
    property_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    default_discount_percent = Column(Float, default=0.0)
    requires_contract = Column(Integer, default=0)
    min_rooms_per_booking = Column(Integer, default=1)
    color = Column(String, default="#6B7280")
    icon = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


class ClientContract(Base):
    """Corporate contracts."""
    __tablename__ = "client_contracts"
    id = Column(String, primary_key=True)
    property_id = Column(String, nullable=False)
    client_type_id = Column(String, ForeignKey("client_types.id"), nullable=False)
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
    active = Column(Integer, default=1)


class PricingSeason(Base):
    """Seasonal pricing rules."""
    __tablename__ = "pricing_seasons"
    id = Column(String, primary_key=True)
    property_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    price_modifier = Column(Float, nullable=False)
    applies_to_categories = Column(String, nullable=True) # JSON
    priority = Column(Integer, default=0)
    color = Column(String, default="#F59E0B")
    active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


class PriceCalculation(Base):
    """Audit log for price calculations."""
    __tablename__ = "price_calculations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_id = Column(String, nullable=True)
    property_id = Column(String, nullable=False)
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
    calculation_details = Column(String, nullable=True) # JSON
    calculated_at = Column(DateTime, default=datetime.now)
    calculated_by = Column(String, nullable=True)



class Property(Base):
    """Properties (Hotels) with check-in/check-out configuration."""
    __tablename__ = "properties"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=True)
    display_mode = Column(String, default="category")
    theme_background = Column(String, default="#FFFFFF")
    theme_text = Column(String, default="#000000")
    theme_primary = Column(String, default="#1E3A5F")
    check_in_start = Column(String, default="07:00")
    check_in_end = Column(String, default="22:00")
    check_out_time = Column(String, default="10:00")
    breakfast_included = Column(Integer, default=0)
    parking_available = Column(Integer, default=1)
    timezone = Column(String, default="America/Asuncion")
    currency = Column(String, default="PYG")
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    facebook_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    active = Column(Integer, default=1)


class ICalFeed(Base):
    """iCal feed URLs for Booking.com/Airbnb sync per room."""
    __tablename__ = "ical_feeds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=False)
    source = Column(String, nullable=False)  # "Booking.com" or "Airbnb"
    ical_url = Column(String, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    sync_enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


class AIAgentPermission(Base):
    """Permissions for AI Agents."""
    __tablename__ = "ai_agent_permissions"
    id = Column(String, primary_key=True)
    property_id = Column(String, ForeignKey("properties.id"), nullable=True)
    role = Column(String, nullable=False)
    can_view_reservations = Column(Integer, default=1)
    can_create_reservations = Column(Integer, default=1)
    can_modify_reservations = Column(Integer, default=0)
    can_cancel_reservations = Column(Integer, default=0)
    can_view_guests = Column(Integer, default=1)
    can_modify_guests = Column(Integer, default=0)
    can_view_rooms = Column(Integer, default=1)
    can_modify_rooms = Column(Integer, default=0)
    can_modify_room_status = Column(Integer, default=0)
    can_view_prices = Column(Integer, default=1)
    can_modify_prices = Column(Integer, default=0)
    can_view_reports = Column(Integer, default=1)
    can_export_data = Column(Integer, default=0)
    can_modify_settings = Column(Integer, default=0)
    requires_confirmation = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)



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
