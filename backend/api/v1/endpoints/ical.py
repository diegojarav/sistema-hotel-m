"""
Hotel API - iCal Sync Endpoints
================================

Manages iCal feed configuration and provides .ics export for OTAs.

Import: Admin configures Booking.com/Airbnb iCal URLs per room.
Export: Public .ics endpoints for OTAs to pull availability.
"""

from fastapi import APIRouter, HTTPException, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional

from api.deps import get_current_user, get_db, require_role
from database import User
from logging_config import get_logger
from services import ICalService

logger = get_logger(__name__)

router = APIRouter()


# ==========================================
# SCHEMAS
# ==========================================

class ICalFeedCreate(BaseModel):
    room_id: str = Field(..., description="Room ID to associate feed with")
    source: str = Field(..., description="OTA source: 'Booking.com' or 'Airbnb'")
    ical_url: str = Field(..., description="iCal feed URL from OTA")


class ICalFeedResponse(BaseModel):
    id: int
    room_id: str
    room_label: str
    source: str
    ical_url: str
    last_synced_at: Optional[str] = None
    sync_enabled: bool
    created_at: Optional[str] = None


class ICalFeedCreateResponse(BaseModel):
    id: int
    room_id: str
    source: str


class SyncResultResponse(BaseModel):
    created: int
    updated: int
    errors: List[str]
    feeds_synced: Optional[int] = None


class ToggleFeedRequest(BaseModel):
    enabled: bool


# ==========================================
# FEED MANAGEMENT (Admin)
# ==========================================

@router.get(
    "/feeds",
    response_model=List[ICalFeedResponse],
    summary="List iCal Feeds",
    description="List all configured iCal feed URLs.",
)
def list_feeds(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """List all iCal feeds. Requires admin role."""
    feeds = ICalService.get_all_feeds(db=db)
    return feeds


@router.post(
    "/feeds",
    response_model=ICalFeedCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add iCal Feed",
    description="Configure a new iCal feed URL for a room.",
)
def create_feed(
    request: ICalFeedCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Add a new iCal feed. Requires admin role."""
    if request.source not in ("Booking.com", "Airbnb"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source must be 'Booking.com' or 'Airbnb'.",
        )
    result = ICalService.create_feed(
        db=db,
        room_id=request.room_id,
        source=request.source,
        ical_url=request.ical_url,
    )
    return result


@router.delete(
    "/feeds/{feed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete iCal Feed",
)
def delete_feed(
    feed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Delete an iCal feed. Requires admin role."""
    success = ICalService.delete_feed(db=db, feed_id=feed_id)
    if not success:
        raise HTTPException(status_code=404, detail="Feed not found.")


@router.patch(
    "/feeds/{feed_id}/toggle",
    summary="Enable/Disable Feed",
)
def toggle_feed(
    feed_id: int,
    request: ToggleFeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Toggle feed sync on/off. Requires admin role."""
    success = ICalService.toggle_feed(db=db, feed_id=feed_id, enabled=request.enabled)
    if not success:
        raise HTTPException(status_code=404, detail="Feed not found.")
    return {"status": "enabled" if request.enabled else "disabled"}


# ==========================================
# SYNC TRIGGERS (Admin)
# ==========================================

@router.post(
    "/feeds/sync",
    response_model=SyncResultResponse,
    summary="Sync All Feeds",
    description="Manually trigger sync of all enabled iCal feeds.",
)
def sync_all_feeds(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Sync all enabled feeds. Requires admin role."""
    result = ICalService.sync_all_feeds(db=db)
    return result


@router.post(
    "/feeds/{feed_id}/sync",
    response_model=SyncResultResponse,
    summary="Sync One Feed",
)
def sync_one_feed(
    feed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Sync a single feed. Requires admin role."""
    result = ICalService.sync_feed(db=db, feed_id=feed_id)
    return result


# ==========================================
# iCal EXPORT (Public)
# ==========================================

@router.get(
    "/export/{room_id}.ics",
    summary="Export Room Calendar",
    description="Public .ics feed for a specific room. OTAs pull this URL.",
)
def export_room_ical(
    room_id: str,
    db: Session = Depends(get_db),
):
    """Public iCal export for a room (no auth — OTAs need direct access)."""
    ics_content = ICalService.generate_ical_for_room(db=db, room_id=room_id)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={room_id}.ics"},
    )


@router.get(
    "/export/all.ics",
    summary="Export All Rooms Calendar",
    description="Master .ics feed for all rooms.",
)
def export_all_ical(
    db: Session = Depends(get_db),
):
    """Public master iCal export (no auth)."""
    ics_content = ICalService.generate_ical_all_rooms(db=db)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=all-rooms.ics"},
    )
