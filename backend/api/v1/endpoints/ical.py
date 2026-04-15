"""
Hotel API - iCal Sync Endpoints (v1.5.0 — Channel Manager v2)
==============================================================

Manages iCal feed configuration and provides .ics export for OTAs.

Import: Admin configures Booking.com / Airbnb / Vrbo / Expedia / Custom iCal URLs per room.
Export: Public .ics endpoints for OTAs to pull availability (rate-limited).

v1.5.0 additions:
- Expanded OTA sources (Vrbo, Expedia, Custom)
- Per-feed health endpoints (/feeds/{id}/health, /feeds/{id}/logs)
- Rate limiting on public export endpoints (60/min, 30/min)
"""

from fastapi import APIRouter, HTTPException, Depends, Response, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional

from api.deps import get_current_user, get_db, require_role
from api.main import limiter
from database import User
from logging_config import get_logger
from services import ICalService, ICalSyncLogService

logger = get_logger(__name__)

router = APIRouter()

# v1.5.0 — expanded OTA source list
VALID_SOURCES = ["Booking.com", "Airbnb", "Vrbo", "Expedia", "Custom"]


# ==========================================
# SCHEMAS
# ==========================================

class ICalFeedCreate(BaseModel):
    room_id: str = Field(..., description="Room ID to associate feed with")
    source: str = Field(
        ...,
        description=f"OTA source: one of {', '.join(VALID_SOURCES)}. "
                    f"For 'Custom', the source string itself is stored as-is.",
    )
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
    # v1.5.0 — health fields
    last_sync_status: str = "NEVER"
    last_sync_error: Optional[str] = None
    consecutive_failures: int = 0
    last_sync_attempted_at: Optional[str] = None
    health_badge: str = "unknown"  # healthy | warning | error | unknown


class ICalFeedCreateResponse(BaseModel):
    id: int
    room_id: str
    source: str


class SyncResultResponse(BaseModel):
    created: int
    updated: int
    flagged_for_review: int = 0
    conflicts: int = 0
    errors: List[str]
    feeds_synced: Optional[int] = None
    status: Optional[str] = None  # "OK" | "ERROR"
    duration_ms: Optional[int] = None


class ToggleFeedRequest(BaseModel):
    enabled: bool


class FeedHealthResponse(BaseModel):
    feed_id: int
    source: str
    room_id: str
    room_label: Optional[str] = None
    last_sync_status: str
    last_sync_error: Optional[str] = None
    consecutive_failures: int
    last_sync_attempted_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    health_badge: str


class SyncLogEntry(BaseModel):
    id: int
    feed_id: int
    attempted_at: str
    status: str
    created_count: int
    updated_count: int
    flagged_for_review_count: int
    conflicts_detected: int
    error_message: Optional[str] = None
    duration_ms: int


# ==========================================
# FEED MANAGEMENT (Admin)
# ==========================================

@router.get(
    "/feeds",
    response_model=List[ICalFeedResponse],
    summary="List iCal Feeds",
    description="List all configured iCal feed URLs with health status.",
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
    description="Configure a new iCal feed URL for a room. "
                f"Source must be one of: {', '.join(VALID_SOURCES)}.",
)
def create_feed(
    request: ICalFeedCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Add a new iCal feed. Requires admin role."""
    if request.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source must be one of: {', '.join(VALID_SOURCES)}.",
        )
    if not request.ical_url or not request.ical_url.strip().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ical_url must be a valid http(s) URL.",
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
# v1.5.0 — Health & History endpoints
# ==========================================

@router.get(
    "/feeds/{feed_id}/health",
    response_model=FeedHealthResponse,
    summary="Feed Health Summary",
    description="Per-feed health: status, error, consecutive failures, badge.",
)
def feed_health(
    feed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Get health summary for a single feed."""
    health = ICalService.get_feed_health(db=db, feed_id=feed_id)
    if not health:
        raise HTTPException(status_code=404, detail="Feed not found.")
    # Convert datetimes to ISO for response_model
    return {
        **health,
        "last_sync_attempted_at": health["last_sync_attempted_at"].isoformat() if health.get("last_sync_attempted_at") else None,
        "last_synced_at": health["last_synced_at"].isoformat() if health.get("last_synced_at") else None,
    }


@router.get(
    "/feeds/{feed_id}/logs",
    response_model=List[SyncLogEntry],
    summary="Feed Sync History",
    description="Last N sync attempts for a feed (default 20, max 100).",
)
def feed_logs(
    feed_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Get the last N sync log entries for a feed."""
    limit = max(1, min(limit, 100))
    logs = ICalSyncLogService.list_for_feed(db=db, feed_id=feed_id, limit=limit)
    return [
        {
            "id": log.id,
            "feed_id": log.feed_id,
            "attempted_at": log.attempted_at.isoformat() if log.attempted_at else "",
            "status": log.status,
            "created_count": log.created_count,
            "updated_count": log.updated_count,
            "flagged_for_review_count": log.flagged_for_review_count,
            "conflicts_detected": log.conflicts_detected,
            "error_message": log.error_message,
            "duration_ms": log.duration_ms,
        }
        for log in logs
    ]


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
# iCal EXPORT (Public, rate-limited)
# ==========================================

@router.get(
    "/export/{room_id}.ics",
    summary="Export Room Calendar",
    description="Public .ics feed for a specific room. OTAs pull this URL. "
                "Rate limited to 60 requests/minute per IP.",
)
@limiter.limit("60/minute")
def export_room_ical(
    request: Request,
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
    description="Master .ics feed for all rooms. "
                "Rate limited to 30 requests/minute per IP (heavier query).",
)
@limiter.limit("30/minute")
def export_all_ical(
    request: Request,
    db: Session = Depends(get_db),
):
    """Public master iCal export (no auth, rate-limited)."""
    ics_content = ICalService.generate_ical_all_rooms(db=db)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=all-rooms.ics"},
    )
