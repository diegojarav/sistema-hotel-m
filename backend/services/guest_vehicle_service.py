"""
GuestVehicleService — registered vehicles per Guest (v1.10.0 — Phase 2a-ext).
=============================================================================

Manages the `guest_vehicles` table and the per-stay `checkin_vehicles` link.

A guest registers up to 5 vehicles (limit enforced here — a familia con 3
autos + 2 motos is real, more crosses into "fleet"). Each visit records
which of those vehicles came along (CheckinVehicle row), plus optional
parking spot and key-deposit flag for valet.

Plate search powers both the "whose car is this?" lookup at the front desk
AND the future OCR pipeline (camera → plate → service.search_by_plate →
guest + active reservation → push to recepción).

Vehicle limit
-------------
`MAX_VEHICLES_PER_GUEST = 5` is the soft cap. Reached → raise
`GuestVehicleError` with a Spanish-friendly message. Soft-deleted
(is_active=False) vehicles do NOT count toward the limit, so the recepcionist
can always replace one without un-deleting.

Plate normalisation
-------------------
Plate is uppercased + whitespace-stripped at write time (validator on the
Pydantic schema). Search also uppercases the query before matching.
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database import (
    CheckIn,
    CheckinVehicle,
    Guest,
    GuestVehicle,
    Reservation,
    Room,
)
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


MAX_VEHICLES_PER_GUEST = 5


class GuestVehicleError(Exception):
    """Raised on GuestVehicle business-rule violations (Spanish messages)."""


class GuestVehicleService:

    # ------------------------------------------------------------------
    # Vehicle CRUD
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def create_vehicle(
        db: Session,
        guest_id: int,
        property_id: str,
        data: Dict[str, Any],
    ) -> GuestVehicle:
        """Register a new vehicle to `guest_id`. Enforces 5-per-guest cap."""
        guest = db.query(Guest).filter(Guest.id == guest_id).first()
        if guest is None:
            raise GuestVehicleError(f"No existe huésped con id {guest_id}")
        if guest.property_id != property_id:
            raise GuestVehicleError(
                f"El huésped {guest_id} pertenece a otra propiedad"
            )

        plate = _norm_plate(data.get("plate_number"))
        if not plate:
            raise GuestVehicleError("La chapa no puede estar vacía")

        # Limit check — soft-deleted vehicles don't count.
        active_count = (
            db.query(GuestVehicle)
            .filter(
                GuestVehicle.guest_id == guest_id,
                GuestVehicle.is_active == True,  # noqa: E712
            )
            .count()
        )
        if active_count >= MAX_VEHICLES_PER_GUEST:
            raise GuestVehicleError(
                f"Límite de vehículos alcanzado: máximo {MAX_VEHICLES_PER_GUEST} "
                f"por huésped. Eliminá uno antes de agregar otro."
            )

        # De-dup: if the same plate is already active for this guest, return it.
        existing = (
            db.query(GuestVehicle)
            .filter(
                GuestVehicle.guest_id == guest_id,
                GuestVehicle.plate_number == plate,
                GuestVehicle.is_active == True,  # noqa: E712
            )
            .first()
        )
        if existing is not None:
            logger.info(
                f"GuestVehicle: returning existing #{existing.id} for guest #{guest_id} plate={plate}"
            )
            return existing

        v = GuestVehicle(
            guest_id=guest_id,
            property_id=property_id,
            plate_number=plate,
            model=_strip_or_none(data.get("model")),
            color=_strip_or_none(data.get("color")),
            is_active=True,
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        logger.info(
            f"Created GuestVehicle #{v.id} for guest #{guest_id} (plate={plate})"
        )
        return v

    @staticmethod
    @with_db
    def get_vehicle(db: Session, vehicle_id: int) -> Optional[GuestVehicle]:
        return db.query(GuestVehicle).filter(GuestVehicle.id == vehicle_id).first()

    @staticmethod
    @with_db
    def get_vehicles(
        db: Session,
        guest_id: int,
        active_only: bool = True,
    ) -> List[GuestVehicle]:
        """All vehicles for `guest_id`, ordered by created_at."""
        q = db.query(GuestVehicle).filter(GuestVehicle.guest_id == guest_id)
        if active_only:
            q = q.filter(GuestVehicle.is_active == True)  # noqa: E712
        return q.order_by(GuestVehicle.created_at).all()

    @staticmethod
    @with_db
    def update_vehicle(
        db: Session,
        vehicle_id: int,
        data: Dict[str, Any],
    ) -> Optional[GuestVehicle]:
        v = db.query(GuestVehicle).filter(GuestVehicle.id == vehicle_id).first()
        if v is None:
            return None
        if "plate_number" in data and data["plate_number"]:
            plate = _norm_plate(data["plate_number"])
            if not plate:
                raise GuestVehicleError("La chapa no puede estar vacía")
            v.plate_number = plate
        for col in ("model", "color"):
            if col in data:
                val = data[col]
                if isinstance(val, str):
                    val = val.strip() or None
                setattr(v, col, val)
        if "is_active" in data and data["is_active"] is not None:
            v.is_active = bool(data["is_active"])
        v.updated_at = datetime.now()
        db.commit()
        db.refresh(v)
        return v

    @staticmethod
    @with_db
    def delete_vehicle(db: Session, vehicle_id: int) -> bool:
        """Soft delete (is_active=False). Returns True if found."""
        v = db.query(GuestVehicle).filter(GuestVehicle.id == vehicle_id).first()
        if v is None:
            return False
        v.is_active = False
        v.updated_at = datetime.now()
        db.commit()
        return True

    # ------------------------------------------------------------------
    # Plate search — "whose car is this?" + OCR future
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def search_by_plate(
        db: Session,
        property_id: str,
        plate: str,
    ) -> Optional[Dict[str, Any]]:
        """Find a vehicle by plate. Returns vehicle + guest + active reservation.

        Returns None if no match. Match is case-insensitive on plate (uppercased
        on both sides). Substring match: searching "ABC" will find "ABC-123".
        Full-plate exact match wins over partial.

        Result shape (when found):
            {
              "vehicle": GuestVehicle row,
              "guest": Guest row,
              "active_reservation": {
                "id": str, "room_id": str, "room_internal_code": str,
                "check_in_date": date, "check_out_date": date,
              } | None,
            }
        """
        norm = _norm_plate(plate)
        if not norm:
            return None

        # Try exact first, then partial — exact is more useful for OCR.
        v = (
            db.query(GuestVehicle)
            .filter(
                GuestVehicle.property_id == property_id,
                GuestVehicle.is_active == True,  # noqa: E712
                GuestVehicle.plate_number == norm,
            )
            .first()
        )
        if v is None:
            v = (
                db.query(GuestVehicle)
                .filter(
                    GuestVehicle.property_id == property_id,
                    GuestVehicle.is_active == True,  # noqa: E712
                    GuestVehicle.plate_number.ilike(f"%{norm}%"),
                )
                .order_by(GuestVehicle.created_at.desc())
                .first()
            )

        if v is None:
            return None

        guest = db.query(Guest).filter(Guest.id == v.guest_id).first()
        if guest is None:
            # Orphan vehicle (FK CASCADE should have deleted it; defensive)
            logger.warning(f"GuestVehicle #{v.id} has no Guest row")
            return None

        # Active or upcoming reservation lookup. "Active" = today between
        # check_in and check_out, OR upcoming within ~7 days. Status filter
        # excludes cancelled.
        today = date.today()
        soon = today + timedelta(days=7)
        active_states = ["RESERVADA", "SEÑADA", "CONFIRMADA", "Confirmada", "Pendiente"]
        candidate_res = (
            db.query(Reservation)
            .filter(
                Reservation.guest_id == guest.id,
                Reservation.status.in_(active_states),
                Reservation.check_in_date <= soon,
            )
            .order_by(Reservation.check_in_date.desc())
            .all()
        )
        active = None
        for r in candidate_res:
            if not r.check_in_date or not r.stay_days:
                continue
            check_out = r.check_in_date + timedelta(days=r.stay_days)
            if r.check_in_date <= today < check_out:
                active = r
                break
            # Upcoming within 7 days
            if r.check_in_date >= today and r.check_in_date <= soon and active is None:
                active = r

        active_summary = None
        if active is not None:
            room = db.query(Room).filter(Room.id == active.room_id).first()
            check_out = active.check_in_date + timedelta(days=active.stay_days or 0)
            active_summary = {
                "id": active.id,
                "room_id": active.room_id,
                "room_internal_code": room.internal_code if room else active.room_id,
                "check_in_date": active.check_in_date,
                "check_out_date": check_out,
                "status": active.status,
            }

        return {
            "vehicle": v,
            "guest": guest,
            "active_reservation": active_summary,
        }

    # ------------------------------------------------------------------
    # Per-stay link (CheckinVehicle)
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def link_to_checkin(
        db: Session,
        checkin_id: int,
        vehicle_id: int,
        parking_spot: Optional[str] = None,
        key_deposited: bool = False,
    ) -> CheckinVehicle:
        """Link a registered vehicle to a specific check-in.

        Idempotent on (checkin_id, vehicle_id) — calling twice returns the
        existing link with updated parking_spot / key_deposited.
        """
        ci = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if ci is None:
            raise GuestVehicleError(f"No existe ficha (CheckIn) con id {checkin_id}")
        v = db.query(GuestVehicle).filter(GuestVehicle.id == vehicle_id).first()
        if v is None:
            raise GuestVehicleError(f"No existe vehículo con id {vehicle_id}")
        if not v.is_active:
            raise GuestVehicleError("El vehículo está dado de baja")

        existing = (
            db.query(CheckinVehicle)
            .filter(
                CheckinVehicle.checkin_id == checkin_id,
                CheckinVehicle.vehicle_id == vehicle_id,
            )
            .first()
        )
        if existing is not None:
            existing.parking_spot = (parking_spot or "").strip() or existing.parking_spot
            existing.key_deposited = bool(key_deposited)
            db.commit()
            db.refresh(existing)
            return existing

        link = CheckinVehicle(
            checkin_id=checkin_id,
            vehicle_id=vehicle_id,
            parking_spot=(parking_spot or "").strip() or None,
            key_deposited=bool(key_deposited),
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        return link

    @staticmethod
    @with_db
    def unlink_from_checkin(
        db: Session,
        checkin_id: int,
        vehicle_id: int,
    ) -> bool:
        link = (
            db.query(CheckinVehicle)
            .filter(
                CheckinVehicle.checkin_id == checkin_id,
                CheckinVehicle.vehicle_id == vehicle_id,
            )
            .first()
        )
        if link is None:
            return False
        db.delete(link)
        db.commit()
        return True

    @staticmethod
    @with_db
    def get_checkin_vehicles(
        db: Session,
        checkin_id: int,
    ) -> List[Dict[str, Any]]:
        """Return per-stay vehicle links with denormalised vehicle fields."""
        rows = (
            db.query(CheckinVehicle, GuestVehicle)
            .join(GuestVehicle, GuestVehicle.id == CheckinVehicle.vehicle_id)
            .filter(CheckinVehicle.checkin_id == checkin_id)
            .order_by(CheckinVehicle.created_at)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for link, v in rows:
            out.append({
                "id": link.id,
                "checkin_id": link.checkin_id,
                "vehicle_id": link.vehicle_id,
                "parking_spot": link.parking_spot,
                "key_deposited": bool(link.key_deposited),
                "created_at": link.created_at,
                "plate_number": v.plate_number,
                "model": v.model,
                "color": v.color,
            })
        return out


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _strip_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _norm_plate(s: Any) -> str:
    """Plate normalisation: trim + uppercase. Empty → empty string."""
    if s is None:
        return ""
    return str(s).strip().upper()
