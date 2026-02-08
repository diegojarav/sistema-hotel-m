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

# Backward compat: app.py imports schemas through services
from schemas import ReservationCreate, CheckInCreate, UserDTO

__all__ = [
    "get_db", "with_db",
    "AuthService", "ReservationService", "GuestService",
    "SettingsService", "PricingService", "RoomService",
    "ReservationCreate", "CheckInCreate", "UserDTO",
]
