"""
Services Package - Single Source of Truth for business logic.

Re-exports all service classes and commonly-used schemas for backward compatibility.
All consumers can continue using: from services import AuthService, ReservationCreate, etc.

v1.10.0 Phase 2a rename
-----------------------
The class formerly known as `GuestService` (managing per-stay CheckIn rows)
is now `CheckInService` in `checkin_service.py`. The new master Guest entity
service lives in `guest_service.py`. To keep existing imports working during
the transition, `GuestService` is NOT aliased to `CheckInService` here —
imports must be updated. Search for `from services import GuestService` and
swap the import name based on intent:
  - reading/writing CheckIn (ficha) records → `CheckInService`
  - reading/writing master Guest entity     → `GuestService`
"""
from services._base import get_db, with_db
from services.auth_service import AuthService
from services.reservation_service import ReservationService
# Phase 2a: NEW master Guest entity (one row per person across stays)
from services.guest_service import GuestService, GuestServiceError
# Phase 2a: pre-rename "GuestService" → CheckInService (manages per-stay fichas)
from services.checkin_service import CheckInService
# Phase 2a: NEW Building entity
from services.building_service import BuildingService, BuildingServiceError
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
from services.ai_agent_permission_service import (
    AIAgentPermissionService,
    AIAgentPermissionError,
    PERMISSION_COLUMNS,
    TOOL_PERMISSION_MAP,
    DEFAULT_PERMISSIONS_BY_ROLE,
)

# Backward compat: app.py imports schemas through services
from schemas import ReservationCreate, CheckInCreate, UserDTO

__all__ = [
    "get_db", "with_db",
    "AuthService", "ReservationService",
    "GuestService", "GuestServiceError",      # NEW Phase 2a master entity
    "CheckInService",                         # renamed from GuestService
    "BuildingService", "BuildingServiceError",
    "SettingsService", "PricingService", "RoomService",
    "ICalService", "ICalSyncLogService", "DocumentService",
    "CajaService", "CajaSessionError",
    "TransaccionService", "TransaccionError",
    "ProductService", "ProductError",
    "ConsumoService", "ConsumoError",
    "MealPlanService", "MealPlanError",
    "KitchenReportService",
    "EmailService", "EmailError",
    "AIAgentPermissionService", "AIAgentPermissionError",
    "PERMISSION_COLUMNS", "TOOL_PERMISSION_MAP", "DEFAULT_PERMISSIONS_BY_ROLE",
    "ReservationCreate", "CheckInCreate", "UserDTO",
]
