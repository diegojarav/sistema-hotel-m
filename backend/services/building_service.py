"""
BuildingService — physical building / wing within a property (v1.10.0 — Phase 2a).
===================================================================================

Manages the `buildings` table. Hotels with annexes, separate buildings, or
distinct wings need to group rooms beyond floor + category. Rooms reference
their building via `rooms.building_id` (FK promoted in Phase 2a).

The default seed (one "Edificio Principal" per property) is created by
migration 012 — this service is what the admin UI uses to add additional
buildings, rename them, or retire them.

Per skill §4 conventions: every method takes `property_id` explicitly,
filters every query by it, and uses `@with_db` with `db: Session` as the
first positional parameter.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database import Building, Room
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class BuildingServiceError(Exception):
    """Raised on Building business-rule violations (Spanish-friendly)."""


class BuildingService:

    @staticmethod
    @with_db
    def create_building(db: Session, property_id: str, data: Dict[str, Any]) -> Building:
        """Create a new building under `property_id`.

        Required keys: id, name. Optional: description, floors, sort_order.
        Raises `BuildingServiceError` if id or name collides (UNIQUE).
        """
        building_id = (data.get("id") or "").strip()
        name = (data.get("name") or "").strip()
        if not building_id:
            raise BuildingServiceError("El edificio necesita un identificador")
        if not name:
            raise BuildingServiceError("El edificio necesita un nombre")

        # Pre-check unique constraints to surface a friendly message
        if db.query(Building).filter(Building.id == building_id).first():
            raise BuildingServiceError(f"Ya existe un edificio con id '{building_id}'")
        existing_name = (
            db.query(Building)
            .filter(Building.property_id == property_id, Building.name == name)
            .first()
        )
        if existing_name:
            raise BuildingServiceError(
                f"Ya existe un edificio llamado '{name}' en esta propiedad"
            )

        b = Building(
            id=building_id,
            property_id=property_id,
            name=name,
            description=data.get("description") or None,
            floors=data.get("floors"),
            sort_order=int(data.get("sort_order") or 0),
            is_active=True,
        )
        db.add(b)
        db.commit()
        db.refresh(b)
        logger.info(f"Created Building '{building_id}' ({name}) for property {property_id}")
        return b

    @staticmethod
    @with_db
    def get_building(db: Session, building_id: str) -> Optional[Building]:
        return db.query(Building).filter(Building.id == building_id).first()

    @staticmethod
    @with_db
    def list_buildings(
        db: Session,
        property_id: str,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List buildings (with room_count) ordered by sort_order, name.

        Returns dicts (not ORM objects) so the room_count aggregate is included
        without forcing a separate query in the endpoint layer.
        """
        q = db.query(Building).filter(Building.property_id == property_id)
        if active_only:
            q = q.filter(Building.is_active == True)  # noqa: E712
        buildings = q.order_by(Building.sort_order, Building.name).all()

        # Build room_count map in one query
        building_ids = [b.id for b in buildings]
        counts: Dict[str, int] = {bid: 0 for bid in building_ids}
        if building_ids:
            from sqlalchemy import func
            rows = (
                db.query(Room.building_id, func.count(Room.id))
                .filter(Room.building_id.in_(building_ids))
                .group_by(Room.building_id)
                .all()
            )
            for bid, n in rows:
                counts[bid] = n

        return [
            {
                "id": b.id,
                "property_id": b.property_id,
                "name": b.name,
                "description": b.description,
                "floors": b.floors,
                "sort_order": b.sort_order,
                "is_active": bool(b.is_active),
                "room_count": counts.get(b.id, 0),
                "created_at": b.created_at,
                "updated_at": b.updated_at,
            }
            for b in buildings
        ]

    @staticmethod
    @with_db
    def update_building(
        db: Session,
        building_id: str,
        data: Dict[str, Any],
    ) -> Optional[Building]:
        """Partial update. Returns the updated building, or None if not found.

        Raises `BuildingServiceError` if the new name collides with another
        building in the same property.
        """
        b = db.query(Building).filter(Building.id == building_id).first()
        if not b:
            return None

        # Name uniqueness check (only if changing)
        if "name" in data and data["name"]:
            new_name = data["name"].strip()
            if new_name != b.name:
                clash = (
                    db.query(Building)
                    .filter(Building.property_id == b.property_id)
                    .filter(Building.name == new_name)
                    .filter(Building.id != b.id)
                    .first()
                )
                if clash:
                    raise BuildingServiceError(
                        f"Ya existe un edificio llamado '{new_name}' en esta propiedad"
                    )
                b.name = new_name

        for col in ("description",):
            if col in data:
                val = data[col]
                if isinstance(val, str):
                    val = val.strip() or None
                setattr(b, col, val)

        if "floors" in data and data["floors"] is not None:
            b.floors = int(data["floors"])
        if "sort_order" in data and data["sort_order"] is not None:
            b.sort_order = int(data["sort_order"])
        if "is_active" in data and data["is_active"] is not None:
            b.is_active = bool(data["is_active"])

        b.updated_at = datetime.now()
        db.commit()
        db.refresh(b)
        return b
