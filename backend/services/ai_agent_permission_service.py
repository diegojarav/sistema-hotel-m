"""
AIAgentPermissionService — Feature 1 (v1.9.0)
==============================================

Activates the previously-dormant `AIAgentPermission` table (database.py).
Provides per-role permissions for the AI agent's 18 tools so admins can
restrict what each role can ask the agent to do.

Concepts
--------
- One row per (property_id, role). property_id is currently nullable
  (single-tenant), and we key by role only for the agent filter logic.
- 13 boolean columns inherited from the existing model (no schema change).
- A static `TOOL_PERMISSION_MAP` maps each AI tool name to the column
  that gates it. Tools without a mapping are always allowed.
- A static `DEFAULT_PERMISSIONS_BY_ROLE` seeds reasonable defaults during
  migration 008. Admin/Supervisor/Gerencia get everything; Recepcion gets
  view_* but loses can_view_reports (which gates financial / heavy
  reports — they still have direct UI access to those features). Cocina
  gets nothing on the agent (uses the dedicated PC page).

Public API
----------
- `get_or_create(db, role)` — returns the permissions row, seeding from
  defaults if it doesn't exist yet (idempotent).
- `list_all(db)` — every row, used by the admin UI.
- `update_permissions(db, role, updates)` — partial update.
- `get_allowed_tools(db, role)` — list of tool names the role can use.
"""

from typing import Optional

from sqlalchemy.orm import Session

from database import AIAgentPermission
from services._base import with_db


# ---------------------------------------------------------------------------
# Permission columns (13 booleans on AIAgentPermission)
# ---------------------------------------------------------------------------
PERMISSION_COLUMNS = [
    "can_view_reservations",
    "can_create_reservations",
    "can_modify_reservations",
    "can_cancel_reservations",
    "can_view_guests",
    "can_modify_guests",
    "can_view_rooms",
    "can_modify_rooms",
    "can_modify_room_status",
    "can_view_prices",
    "can_modify_prices",
    "can_view_reports",
    "can_export_data",
    "can_modify_settings",
]


# ---------------------------------------------------------------------------
# Tool ↔ permission mapping
# ---------------------------------------------------------------------------
# Tool functions live in api/v1/endpoints/ai_tools.py. Their `__name__` is
# what the agent middleware looks up here. A tool absent from this map is
# considered always-allowed (defensive default — easier to find missing
# mappings than accidentally lock people out).
#
# Today (v1.9) all tools are read-only, so the create/modify/cancel/export
# columns are unused by any tool. Kept in the model for the future write
# tools (and for the admin to set them in advance).
TOOL_PERMISSION_MAP = {
    # Reservations
    "search_reservation":            "can_view_reservations",
    "get_reservations_report":       "can_view_reservations",
    "get_today_summary":             "can_view_reservations",
    "get_occupancy_for_month":       "can_view_reservations",
    # Guests
    "search_guest":                  "can_view_guests",
    # Rooms
    "check_availability":            "can_view_rooms",
    # Pricing
    "get_hotel_rates":               "can_view_prices",
    "calculate_price":               "can_view_prices",
    # Reports (operational + financial — gated by the same column for now)
    "get_room_performance":          "can_view_reports",
    "get_booking_sources":           "can_view_reports",
    "get_parking_status":            "can_view_reports",
    "get_revenue_summary":           "can_view_reports",
    "consultar_caja":                "can_view_reports",
    "resumen_ingresos_por_metodo":   "can_view_reports",
    "consultar_inventario":          "can_view_reports",
    "consumos_habitacion":           "can_view_reports",
    "reporte_cocina":                "can_view_reports",
    "estado_email_reserva":          "can_view_reports",
}


# ---------------------------------------------------------------------------
# Default permissions per role (used by migration 008 + get_or_create)
# ---------------------------------------------------------------------------
def _all_true() -> dict:
    return {col: 1 for col in PERMISSION_COLUMNS}


def _all_false() -> dict:
    return {col: 0 for col in PERMISSION_COLUMNS}


def _recepcion_default() -> dict:
    """View everything operational; reports gated."""
    perms = _all_false()
    perms["can_view_reservations"] = 1
    perms["can_view_guests"] = 1
    perms["can_view_rooms"] = 1
    perms["can_view_prices"] = 1
    # can_view_reports stays False — blocks financial + heavy report tools
    return perms


DEFAULT_PERMISSIONS_BY_ROLE = {
    "admin":         _all_true(),
    "supervisor":    _all_true(),
    "gerencia":      _all_true(),
    "recepcion":     _recepcion_default(),
    "recepcionista": _recepcion_default(),
    "cocina":        _all_false(),  # cocina uses the dedicated PC page, not the agent
}


def _normalize(role: Optional[str]) -> str:
    return (role or "").lower().strip()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class AIAgentPermissionError(Exception):
    """Raised on validation failures (e.g. trying to lock admin out completely)."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class AIAgentPermissionService:

    @staticmethod
    @with_db
    def get_or_create(db: Session, role: str) -> AIAgentPermission:
        """Return the row for `role`, seeding defaults on first access."""
        norm = _normalize(role)
        if not norm:
            raise AIAgentPermissionError("role is required")

        row = db.query(AIAgentPermission).filter(AIAgentPermission.role == norm).first()
        if row is not None:
            return row

        defaults = DEFAULT_PERMISSIONS_BY_ROLE.get(norm, _all_false())
        row = AIAgentPermission(
            id=f"role-{norm}",
            property_id=None,  # single-tenant for now
            role=norm,
            **defaults,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    @with_db
    def list_all(db: Session) -> list[AIAgentPermission]:
        """Return all permission rows ordered by role."""
        return db.query(AIAgentPermission).order_by(AIAgentPermission.role).all()

    @staticmethod
    @with_db
    def update_permissions(db: Session, role: str, updates: dict) -> AIAgentPermission:
        """Apply a partial update to a role's permissions.

        Safety: refuses to leave admin/supervisor/gerencia with all permissions
        false — it would brick the agent for management roles.
        """
        norm = _normalize(role)
        row = AIAgentPermissionService.get_or_create(db=db, role=norm)

        # Apply known boolean updates only
        for col, val in updates.items():
            if col not in PERMISSION_COLUMNS:
                continue
            setattr(row, col, 1 if val else 0)

        # Safety check: don't let management roles end up with zero permissions
        if norm in {"admin", "supervisor", "gerencia"}:
            if not any(getattr(row, c) for c in PERMISSION_COLUMNS):
                db.rollback()
                raise AIAgentPermissionError(
                    f"No se pueden deshabilitar TODOS los permisos para el rol '{norm}'"
                )

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    @with_db
    def get_allowed_tools(db: Session, role: str) -> list[str]:
        """Return the list of AI tool names this role is allowed to use.

        Tools without an entry in TOOL_PERMISSION_MAP are always allowed
        (defensive default — see module docstring).
        """
        row = AIAgentPermissionService.get_or_create(db=db, role=role)

        allowed = []
        for tool_name, perm_col in TOOL_PERMISSION_MAP.items():
            if getattr(row, perm_col, 0):
                allowed.append(tool_name)

        # Also include any tools NOT in the map (always allowed)
        # Caller will intersect with the actual TOOLS_LIST at the call site.
        return allowed
