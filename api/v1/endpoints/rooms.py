"""
Hotel Munich API - Room Endpoints
==================================

HYBRID MONOLITH: Imports from root database.py and services.py
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date

# Import from API deps
from api.deps import get_db

# IMPORT FROM ROOT - Single Source of Truth
from database import Room
from services import ReservationService

router = APIRouter()


# ==========================================
# API-SPECIFIC SCHEMAS
# ==========================================

from pydantic import BaseModel
from typing import Optional


class RoomDTO(BaseModel):
    """Room information."""
    id: str
    type: str
    status: str


class RoomStatusDTO(BaseModel):
    """Room status for a specific date."""
    room_id: str
    type: str
    status: str
    huesped: str
    res_id: Optional[str] = None


# Room IDs constant
ROOM_IDS = [
    "31", "32", "33", "34", "35", "36",
    "21", "22", "23", "24", "25", "26", "27", "28"
]


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "",
    response_model=List[RoomDTO],
    summary="List All Rooms",
    description="Get a list of all hotel rooms with their types and statuses."
)
def list_rooms(db: Session = Depends(get_db)):
    """Get all rooms in the hotel."""
    rooms = db.query(Room).all()
    
    if not rooms:
        return [RoomDTO(id=rid, type="Standard", status="Active") for rid in ROOM_IDS]
    
    return [
        RoomDTO(id=r.id, type=r.type or "Standard", status=r.status or "Active")
        for r in sorted(rooms, key=lambda x: x.id)
    ]


@router.get(
    "/status",
    response_model=List[RoomStatusDTO],
    summary="Get Room Status for Date",
    description="Get the occupancy status of all rooms for a specific date."
)
def get_rooms_status(
    target_date: date = Query(default=None, description="Date to check (defaults to today)"),
    db: Session = Depends(get_db)
):
    """Get status of all rooms for a specific date."""
    check_date = target_date or date.today()
    status_list = ReservationService.get_daily_status(db, check_date)
    
    return [
        RoomStatusDTO(
            room_id=s["room_id"],
            type=s["type"],
            status=s["status"],
            huesped=s["huesped"],
            res_id=s.get("res_id")
        )
        for s in status_list
    ]


@router.get(
    "/{room_id}",
    response_model=RoomDTO,
    summary="Get Room Details",
    description="Get details of a specific room."
)
def get_room(room_id: str, db: Session = Depends(get_db)):
    """Get a specific room by ID."""
    room = db.query(Room).filter(Room.id == room_id).first()
    
    if not room:
        if room_id in ROOM_IDS:
            return RoomDTO(id=room_id, type="Standard", status="Active")
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
    
    return RoomDTO(id=room.id, type=room.type or "Standard", status=room.status or "Active")
