"""
Kitchen Report Service (v1.7.0 — Phase 4)
==========================================

Builds the daily breakfast-count report the kitchen uses to plan preparation.

Key rule (from spec)
--------------------
A guest who **checks out today IS** included in today's breakfast count
(they haven't left yet — they still eat that morning).

A guest who **checks in today is NOT** included in today's breakfast
(they arrive later in the day, too late for that morning's breakfast).

So for a target date D, we return reservations where the guest slept the
night of D-1:

    check_in_date <= D - 1 (i.e. check_in_date < D)
    check_in_date + stay_days >= D

This means the guest arrived on or before D-1 and hasn't checked out yet on
the morning of D. Both mid-stay and same-day-checkout guests qualify.

When `meals_enabled=False`, every call returns a disabled/empty payload so
UI layers can render the "Servicio de comidas no habilitado" message without
guessing at any schema.
"""

from datetime import date, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from database import Reservation, Room, RoomCategory, MealPlan, Property
from services._base import with_db
from logging_config import get_logger

logger = get_logger(__name__)

# Active reservation statuses (payment-aware lifecycle + legacy values)
ACTIVE_STATES = [
    "RESERVADA", "SEÑADA", "CONFIRMADA",  # v1.4.0+
    "Confirmada", "Pendiente",             # legacy
]


class KitchenReportService:
    """Computes breakfast/meal counts per date."""

    @staticmethod
    @with_db
    def get_daily_report(
        db: Session,
        fecha: date,
        property_id: str = "los-monges",
    ) -> Dict[str, Any]:
        """Return the per-room breakfast breakdown for a given date.

        Response shape::

            {
              "enabled": bool,
              "fecha": "YYYY-MM-DD",
              "property_id": str,
              "mode": str|None,         # INCLUIDO | OPCIONAL_PERSONA | OPCIONAL_HABITACION
              "total_with_breakfast": int,
              "total_without": int,
              "rooms": [
                {
                  "reservation_id": str,
                  "room_id": str,
                  "internal_code": str,
                  "room_type": str,
                  "guest_name": str,
                  "guests_count": int,
                  "breakfast_guests": int,
                  "plan_id": str|None,
                  "plan_code": str|None,
                  "plan_name": str|None,
                  "checkout_date": "YYYY-MM-DD",
                  "checkout_today": bool,
                  "check_in_date": "YYYY-MM-DD",
                },
                ...
              ],
            }

        When `meals_enabled=False`, returns an empty payload with
        `enabled=False` (no rooms). Callers render a "Servicio no habilitado"
        message in that case.
        """
        # Check meals config
        prop = db.query(Property).filter(Property.id == property_id).first()
        meals_enabled = bool(prop and prop.meals_enabled)
        mode = prop.meal_inclusion_mode if prop else None

        payload: Dict[str, Any] = {
            "enabled": meals_enabled,
            "fecha": fecha.isoformat(),
            "property_id": property_id,
            "mode": mode,
            "total_with_breakfast": 0,
            "total_without": 0,
            "rooms": [],
        }

        if not meals_enabled:
            return payload

        # Query reservations where guest slept night of D-1 and is still present.
        # In practice: checked in on or before (D-1), checkout >= D.
        day_before = fecha - timedelta(days=1)

        # Lower bound guard (max realistic stay = 365 days) to avoid full-table scan.
        max_stay_days = 365
        earliest_checkin = day_before - timedelta(days=max_stay_days)

        reservations = (
            db.query(Reservation)
            .filter(
                Reservation.status.in_(ACTIVE_STATES),
                Reservation.check_in_date <= day_before,
                Reservation.check_in_date >= earliest_checkin,
            )
            .all()
        )

        # Filter to those still occupying the room on the target date
        # (check_in_date + stay_days >= fecha → hasn't fully checked out).
        active = []
        for r in reservations:
            if r.stay_days is None or r.stay_days <= 0:
                continue
            checkout_date = r.check_in_date + timedelta(days=r.stay_days)
            if checkout_date >= fecha:
                active.append((r, checkout_date))

        # Preload rooms + categories + plans into dicts for fast lookup
        room_ids = {r.room_id for r, _ in active if r.room_id}
        rooms_by_id = {
            rm.id: rm
            for rm in db.query(Room).filter(Room.id.in_(room_ids)).all()
        } if room_ids else {}
        cat_ids = {rm.category_id for rm in rooms_by_id.values() if rm.category_id}
        cat_names = {
            c.id: c.name
            for c in db.query(RoomCategory).filter(RoomCategory.id.in_(cat_ids)).all()
        } if cat_ids else {}
        plan_ids = {r.meal_plan_id for r, _ in active if r.meal_plan_id}
        plans_by_id = {
            p.id: p
            for p in db.query(MealPlan).filter(MealPlan.id.in_(plan_ids)).all()
        } if plan_ids else {}

        rows: List[Dict[str, Any]] = []
        total_bf = 0
        total_without = 0

        for res, checkout_date in active:
            room = rooms_by_id.get(res.room_id) if res.room_id else None
            room_internal = (room.internal_code if room and room.internal_code else res.room_type) or (res.room_id or "-")
            room_type = cat_names.get(room.category_id, room_internal) if room else (res.room_type or "-")

            # Determine effective breakfast count:
            # - INCLUIDO mode → every guest eats (breakfast_guests defaults to guests_count implicitly)
            # - OPCIONAL_* → use stored breakfast_guests (null → 0)
            # We don't have a reliable "guests_count" on Reservation today; fall back to 1
            # if breakfast_guests is null and we're in INCLUIDO mode.
            guests_count = _estimate_guests_count(res)
            if mode == "INCLUIDO":
                bf_count = res.breakfast_guests if res.breakfast_guests is not None else guests_count
            else:
                bf_count = int(res.breakfast_guests or 0)
            bf_count = max(0, min(bf_count, guests_count))
            without_count = max(0, guests_count - bf_count)

            plan = plans_by_id.get(res.meal_plan_id) if res.meal_plan_id else None
            plan_code = plan.code if plan else (None if mode != "INCLUIDO" else "CON_DESAYUNO")
            plan_name = plan.name if plan else (None if mode != "INCLUIDO" else "Con desayuno (incluido)")

            rows.append({
                "reservation_id": res.id,
                "room_id": res.room_id or "",
                "internal_code": room_internal,
                "room_type": room_type,
                "guest_name": res.guest_name or "-",
                "guests_count": guests_count,
                "breakfast_guests": bf_count,
                "plan_id": res.meal_plan_id,
                "plan_code": plan_code,
                "plan_name": plan_name,
                "checkout_date": checkout_date.isoformat(),
                "checkout_today": checkout_date == fecha,
                "check_in_date": res.check_in_date.isoformat() if res.check_in_date else None,
            })
            total_bf += bf_count
            total_without += without_count

        # Sort by room internal_code for predictable output
        rows.sort(key=lambda r: (r["internal_code"] or "", r["guest_name"] or ""))

        payload["rooms"] = rows
        payload["total_with_breakfast"] = total_bf
        payload["total_without"] = total_without
        return payload


def _estimate_guests_count(reservation: Reservation) -> int:
    """Best-effort guests count.

    The Reservation model doesn't currently expose a structured guests_count
    column. We fall back to heuristics:
      1. If `breakfast_guests` is set explicitly, assume at least that many.
      2. Otherwise default to 1 (single occupancy) — conservative for kitchen prep.
    """
    if reservation.breakfast_guests is not None and reservation.breakfast_guests > 0:
        return reservation.breakfast_guests
    return 1
