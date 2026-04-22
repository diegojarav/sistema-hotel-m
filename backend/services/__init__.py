"""
Services Package - Single Source of Truth for business logic.

Re-exports all service classes and commonly-used schemas for backward compatibility.
All consumers can continue using: from services import AuthService, ReservationCreate, etc.
"""
from services._base import get_db, with_db
from services.auth_service import AuthService
from services.reservation_service import ReservationService
from services.guest_service import GuestService
from services.settings_service import SettingsService
from services.pricing_service import PricingService
from services.room_service import RoomService
from services.ical_service import ICalService
from services.document_service import DocumentService
from services.caja_service import CajaService, CajaSessionError
from services.transaccion_service import TransaccionService, TransaccionError
from services.ical_sync_log_service import ICalSyncLogService
from services.product_service import ProductService, ProductError
from services.consumo_service import ConsumoService, ConsumoError
from services.meal_plan_service import MealPlanService, MealPlanError
from services.kitchen_report_service import KitchenReportService
from services.email_service import EmailService, EmailError

# Backward compat: app.py imports schemas through services
from schemas import ReservationCreate, CheckInCreate, UserDTO

__all__ = [
    "get_db", "with_db",
    "AuthService", "ReservationService", "GuestService",
    "SettingsService", "PricingService", "RoomService",
    "ICalService", "ICalSyncLogService", "DocumentService",
    "CajaService", "CajaSessionError",
    "TransaccionService", "TransaccionError",
    "ProductService", "ProductError",
    "ConsumoService", "ConsumoError",
    "MealPlanService", "MealPlanError",
    "KitchenReportService",
    "EmailService", "EmailError",
    "ReservationCreate", "CheckInCreate", "UserDTO",
]
