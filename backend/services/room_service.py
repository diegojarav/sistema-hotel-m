from sqlalchemy.orm import Session
from database import Room, RoomCategory, Reservation
from typing import List, Dict
from datetime import date, timedelta

from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class RoomService:
    """Service for room and category operations."""

    DEFAULT_PROPERTY_ID = "los-monges"

    @staticmethod
    @with_db
    def get_all_categories(db: Session, property_id: str = None) -> List[Dict]:
        """
        Return all active categories with pricing.

        Args:
            property_id: Property ID to filter by (defaults to los-monges)

        Returns:
            List of category dictionaries with id, name, base_price, max_capacity, etc.
        """
        prop_id = property_id or RoomService.DEFAULT_PROPERTY_ID

        categories = db.query(RoomCategory).filter(
            RoomCategory.property_id == prop_id,
            RoomCategory.active == 1
        ).order_by(RoomCategory.sort_order).all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "base_price": c.base_price,
                "max_capacity": c.max_capacity,
                "bed_configuration": c.bed_configuration,
                "amenities": c.amenities,
                "sort_order": c.sort_order
            }
            for c in categories
        ]

    @staticmethod
    @with_db
    def get_available_rooms(
        db: Session,
        check_in: date,
        check_out: date,
        category_id: str = None,
        property_id: str = None
    ) -> List[Dict]:
        """
        Return rooms available for the date range with FULL CONFLICT DETECTION.

        Algorithm:
        1. Filter by room.active = 1 and room.status = 'available'
        2. Check against existing reservations (status='Confirmada')
        3. A room is unavailable if ANY reservation overlaps the date range
        4. Optionally filter by category_id

        Args:
            check_in: Check-in date
            check_out: Check-out date
            category_id: Optional category to filter by
            property_id: Property ID (defaults to los-monges)

        Returns:
            List of available room dictionaries
        """
        prop_id = property_id or RoomService.DEFAULT_PROPERTY_ID

        # Get all active rooms with status 'available'
        query = db.query(Room).filter(
            Room.property_id == prop_id,
            Room.active == 1,
            Room.status == "available"
        )

        if category_id:
            query = query.filter(Room.category_id == category_id)

        all_rooms = query.all()

        # Get category lookup for pricing
        categories = db.query(RoomCategory).filter(RoomCategory.property_id == prop_id).all()
        cat_map = {c.id: c for c in categories}

        # Get all confirmed reservations that might conflict
        confirmed_reservations = db.query(Reservation).filter(
            Reservation.status == "Confirmada"
        ).all()

        # Build set of room IDs that are occupied during our date range
        occupied_room_ids = set()
        for res in confirmed_reservations:
            if res.check_in_date and res.stay_days:
                res_start = res.check_in_date
                res_end = res_start + timedelta(days=res.stay_days)

                # Check overlap
                if res_start < check_out and res_end > check_in:
                    if res.room_id:
                        occupied_room_ids.add(res.room_id)

        # Filter out occupied rooms and build response
        available_rooms = []
        for room in all_rooms:
            if room.id not in occupied_room_ids:
                cat = cat_map.get(room.category_id)
                available_rooms.append({
                    "id": room.id,
                    "internal_code": room.internal_code,
                    "category_id": room.category_id,
                    "category_name": cat.name if cat else "Sin Categoría",
                    "floor": room.floor,
                    "base_price": room.custom_price or (cat.base_price if cat else 0),
                    "max_capacity": cat.max_capacity if cat else 0,
                    "status": room.status
                })

        # Sort by internal_code for consistent ordering
        available_rooms.sort(key=lambda x: x.get("internal_code") or x["id"])

        return available_rooms

    @staticmethod
    @with_db
    def get_room_price(db: Session, room_id: str) -> float:
        """
        Get the price for a specific room.

        Returns room.custom_price if set, otherwise category.base_price.

        Args:
            room_id: Room ID

        Returns:
            Price as float, or 0 if not found
        """
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            return 0.0

        if room.custom_price:
            return room.custom_price

        if room.category_id:
            category = db.query(RoomCategory).filter(RoomCategory.id == room.category_id).first()
            if category:
                return category.base_price

        return 0.0

    @staticmethod
    @with_db
    def get_all_rooms(db: Session, property_id: str = None, active_only: bool = True) -> List[Dict]:
        """
        Get all rooms with category information.

        Args:
            property_id: Property ID (defaults to los-monges)
            active_only: If True, only return active rooms

        Returns:
            List of room dictionaries with category info
        """
        prop_id = property_id or RoomService.DEFAULT_PROPERTY_ID

        query = db.query(Room).filter(Room.property_id == prop_id)
        if active_only:
            query = query.filter(Room.active == 1)

        rooms = query.all()

        # Build category lookup
        categories = db.query(RoomCategory).filter(RoomCategory.property_id == prop_id).all()
        cat_map = {c.id: c for c in categories}

        result = []
        for r in rooms:
            cat = cat_map.get(r.category_id)
            result.append({
                "id": r.id,
                "internal_code": r.internal_code,
                "category_id": r.category_id,
                "category_name": cat.name if cat else "Sin Categoría",
                "floor": r.floor,
                "status": r.status,
                "base_price": r.custom_price or (cat.base_price if cat else 0),
                "max_capacity": cat.max_capacity if cat else 0,
                "active": r.active
            })

        result.sort(key=lambda x: x.get("internal_code") or x["id"])
        return result
