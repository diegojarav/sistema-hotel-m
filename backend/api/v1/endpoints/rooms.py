"""
Hotel PMS API - Room Endpoints
==================================

HYBRID MONOLITH: Imports from root database.py and services.py
Updated for RoomCategory-based schema (Los Monges MVP)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import date, datetime

# Import from API deps
from api.deps import get_db, get_current_user, require_role

# IMPORT FROM ROOT - Single Source of Truth
from database import Room, RoomCategory, User
from services import ReservationService

# Property ID (Los Monges for now - will be dynamic in multi-tenant)
PROPERTY_ID = "los-monges"

router = APIRouter()


# ==========================================
# API-SPECIFIC SCHEMAS
# ==========================================

from pydantic import BaseModel
from typing import Optional


class RoomDTO(BaseModel):
    """Room information with category details."""
    id: str
    category_id: Optional[str] = None
    category_name: str = "Sin Categoría"
    internal_code: Optional[str] = None
    floor: Optional[int] = None
    status: str
    base_price: Optional[float] = None


class RoomStatusDTO(BaseModel):
    """Room status for a specific date with category info."""
    room_id: str
    category_id: Optional[str] = None
    category_name: str = "Sin Categoría"
    base_price: Optional[float] = None
    max_capacity: Optional[int] = None
    internal_code: Optional[str] = None
    floor: Optional[int] = None
    status: str
    huesped: str
    res_id: Optional[str] = None


class RoomCategoryDTO(BaseModel):
    """Room category with pricing information."""
    id: str
    name: str
    description: Optional[str] = None
    base_price: float
    max_capacity: int
    bed_configuration: Optional[str] = None
    amenities: Optional[str] = None
    active: int = 1


class CreateRoomsRequest(BaseModel):
    """Request to create new rooms."""
    category_id: str
    quantity: int
    floor: int


class UpdateRoomStatusRequest(BaseModel):
    """Request to update room status."""
    status: str
    reason: Optional[str] = None


class RoomStatisticsDTO(BaseModel):
    """Room statistics by category."""
    category_name: str
    base_price: Optional[float] = None
    total_rooms: int
    active_rooms: int
    available: int
    occupied: int
    maintenance: int
    cleaning: int


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "",
    response_model=List[RoomDTO],
    summary="List All Rooms",
    description="Get a list of all hotel rooms with their categories and statuses. Supports pagination."
)
def list_rooms(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db)
):
    """Get all active rooms in the hotel with category information."""
    # Get all active rooms
    rooms = db.query(Room).filter(Room.active == 1).all()

    if not rooms:
        return []

    # Build category lookup
    categories = db.query(RoomCategory).all()
    cat_map = {c.id: c for c in categories}

    result = []
    for r in sorted(rooms, key=lambda x: x.id):
        cat = cat_map.get(r.category_id)
        result.append(RoomDTO(
            id=r.id,
            category_id=r.category_id,
            category_name=cat.name if cat else "Sin Categoría",
            internal_code=r.internal_code,
            floor=r.floor,
            status=r.status or "available",
            base_price=r.custom_price or (cat.base_price if cat else None)
        ))

    # PERF-004: Apply pagination
    return result[skip:skip + limit]


@router.get(
    "/categories",
    response_model=List[RoomCategoryDTO],
    summary="List Room Categories",
    description="Get all room categories with their pricing information."
)
def list_categories(db: Session = Depends(get_db)):
    """Get all active room categories with pricing."""
    categories = db.query(RoomCategory).filter(RoomCategory.active == 1).order_by(RoomCategory.sort_order).all()

    return [
        RoomCategoryDTO(
            id=c.id,
            name=c.name,
            description=c.description,
            base_price=c.base_price,
            max_capacity=c.max_capacity,
            bed_configuration=c.bed_configuration,
            amenities=c.amenities,
            active=c.active
        )
        for c in categories
    ]


@router.get(
    "/status",
    response_model=List[RoomStatusDTO],
    summary="Get Room Status for Date",
    description="Get the occupancy status of all rooms for a specific date with category info."
)
def get_rooms_status(
    target_date: date = Query(default=None, description="Date to check (defaults to today)"),
    check_in: date = Query(default=None, description="Start of date range for availability check"),
    check_out: date = Query(default=None, description="End of date range for availability check"),
    db: Session = Depends(get_db)
):
    """Get status of all rooms for a specific date or date range with full category information."""
    if check_in and check_out:
        # Date range mode: mark rooms occupied if ANY reservation overlaps
        status_list = ReservationService.get_range_status(db, check_in, check_out)
    else:
        check_date = target_date or date.today()
        status_list = ReservationService.get_daily_status(db, check_date)

    # Get all rooms with category info for additional details
    rooms = db.query(Room).filter(Room.active == 1).all()
    room_map = {r.id: r for r in rooms}

    categories = db.query(RoomCategory).all()
    cat_map = {c.id: c for c in categories}

    result = []
    for s in status_list:
        room = room_map.get(s["room_id"])
        cat = cat_map.get(room.category_id) if room else None

        result.append(RoomStatusDTO(
            room_id=s["room_id"],
            category_id=room.category_id if room else None,
            category_name=s["type"],  # Service already looks up category name
            base_price=room.custom_price or (cat.base_price if cat else None),
            max_capacity=cat.max_capacity if cat else None,
            internal_code=room.internal_code if room else None,
            floor=room.floor if room else None,
            status=s["status"],
            huesped=s["huesped"],
            res_id=s.get("res_id")
        ))

    return result


@router.get(
    "/{room_id}",
    response_model=RoomDTO,
    summary="Get Room Details",
    description="Get details of a specific room with category information."
)
def get_room(room_id: str, db: Session = Depends(get_db)):
    """Get a specific room by ID with category details."""
    room = db.query(Room).filter(Room.id == room_id).first()

    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    # Get category info
    cat = None
    if room.category_id:
        cat = db.query(RoomCategory).filter(RoomCategory.id == room.category_id).first()

    return RoomDTO(
        id=room.id,
        category_id=room.category_id,
        category_name=cat.name if cat else "Sin Categoría",
        internal_code=room.internal_code,
        floor=room.floor,
        status=room.status or "available",
        base_price=room.custom_price or (cat.base_price if cat else None)
    )


# ==========================================
# ADMIN ENDPOINTS (Require Authentication)
# ==========================================

@router.post(
    "",
    response_model=dict,
    summary="Create New Rooms",
    description="Create new rooms for a category. Requires authentication."
)
def create_rooms(
    request: CreateRoomsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Create new rooms for a category."""
    # Validate category exists
    category = db.query(RoomCategory).filter(RoomCategory.id == request.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail=f"Category {request.category_id} not found")

    # Get current room count for this category
    current_count = db.query(Room).filter(
        Room.category_id == request.category_id,
        Room.property_id == PROPERTY_ID
    ).count()

    # Get next room number (simple approach: count existing rooms + 1)
    existing_count = db.query(Room).filter(Room.property_id == PROPERTY_ID).count()
    next_room_num = existing_count + 1

    # Generate prefix from category name
    words = category.name.split()[:2]
    prefix = ''.join(word[0].upper() for word in words if word)

    created = 0
    for i in range(request.quantity):
        room_id = f"{PROPERTY_ID}-room-{next_room_num + i:03d}"
        internal_code = f"{prefix}-{current_count + i + 1:02d}"

        room = Room(
            id=room_id,
            property_id=PROPERTY_ID,
            category_id=request.category_id,
            floor=request.floor,
            internal_code=internal_code,
            status="available",
            active=1,
            created_at=datetime.now()
        )
        db.add(room)
        created += 1

    db.commit()
    return {"success": True, "message": f"Created {created} rooms", "count": created}


@router.patch(
    "/{room_id}/status",
    response_model=dict,
    summary="Update Room Status",
    description="Update the status of a room. Requires authentication."
)
def update_room_status(
    room_id: str,
    request: UpdateRoomStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "supervisor"))
):
    """Update room status with logging."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    old_status = room.status

    # Update room
    room.status = request.status
    room.status_reason = request.reason
    room.status_changed_at = datetime.now()
    room.status_changed_by = current_user.username
    room.updated_at = datetime.now()

    # TODO: Add RoomStatusLog model to database.py and enable logging
    # For now, status changes are tracked in the room record itself
    db.commit()

    return {"success": True, "message": "Status updated"}


@router.patch(
    "/{room_id}/active",
    response_model=dict,
    summary="Toggle Room Active Status",
    description="Activate or deactivate a room. Requires authentication."
)
def toggle_room_active(
    room_id: str,
    active: bool = Query(..., description="Set to true to activate, false to deactivate"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Activate or deactivate a room."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    room.active = 1 if active else 0
    room.updated_at = datetime.now()
    db.commit()

    status_text = "activated" if active else "deactivated"
    return {"success": True, "message": f"Room {status_text}"}


@router.delete(
    "/{room_id}",
    response_model=dict,
    summary="Delete Room",
    description="Permanently delete a room. Requires authentication."
)
def delete_room(
    room_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Permanently delete a room."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    db.delete(room)
    db.commit()

    return {"success": True, "message": "Room deleted"}


@router.get(
    "/statistics/by-category",
    response_model=List[RoomStatisticsDTO],
    summary="Get Room Statistics",
    description="Get room count statistics grouped by category."
)
def get_room_statistics(db: Session = Depends(get_db)):
    """Get room statistics by category."""
    # Get all active categories
    categories = db.query(RoomCategory).filter(
        RoomCategory.property_id == PROPERTY_ID,
        RoomCategory.active == 1
    ).order_by(RoomCategory.sort_order).all()

    result = []
    for cat in categories:
        # Count rooms by status for this category
        rooms = db.query(Room).filter(
            Room.category_id == cat.id,
            Room.property_id == PROPERTY_ID
        ).all()

        total = len(rooms)
        active = sum(1 for r in rooms if r.active == 1)
        available = sum(1 for r in rooms if r.active == 1 and r.status == "available")
        occupied = sum(1 for r in rooms if r.active == 1 and r.status == "occupied")
        maintenance = sum(1 for r in rooms if r.active == 1 and r.status == "maintenance")
        cleaning = sum(1 for r in rooms if r.active == 1 and r.status == "cleaning")

        result.append(RoomStatisticsDTO(
            category_name=cat.name,
            base_price=cat.base_price,
            total_rooms=total,
            active_rooms=active,
            available=available,
            occupied=occupied,
            maintenance=maintenance,
            cleaning=cleaning
        ))

    return result


@router.get(
    "/count/{category_id}",
    response_model=dict,
    summary="Get Room Count by Category",
    description="Get the number of rooms in a specific category."
)
def get_room_count_by_category(category_id: str, db: Session = Depends(get_db)):
    """Get room count for a specific category."""
    count = db.query(Room).filter(
        Room.category_id == category_id,
        Room.property_id == PROPERTY_ID
    ).count()
    return {"count": count}
