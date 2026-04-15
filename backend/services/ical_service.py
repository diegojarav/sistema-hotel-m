"""
iCal Sync Service — Channel Manager v2 (v1.5.0 Phase 2)
========================================================

Handles:
- Import: Pull .ics feeds from OTAs (Booking.com, Airbnb, Vrbo, Expedia, Custom),
  upsert reservations, detect cancellations, detect conflicts
- Export: Generate .ics calendars for rooms (OTAs pull these)
- Background sync: Called every 15 minutes by the auto-sync task
- Health tracking: per-feed last_sync_status, consecutive_failures, sync log
- Discord alerts: ERROR-level logs auto-route via DiscordWebhookHandler
"""

import requests
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Set

import icalendar
from sqlalchemy.orm import Session

from database import Reservation, Room, ICalFeed, session_factory
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)

SYNC_TIMEOUT = 30  # seconds
DISCORD_ALERT_THRESHOLD = 3  # consecutive failures before Discord alert
SYNC_LOG_KEEP = 100  # keep last N sync log entries per feed

# Active reservation states (legacy + v1.4.0 new lifecycle)
ACTIVE_RESERVATION_STATES = (
    "RESERVADA", "SEÑADA", "CONFIRMADA",
    "Confirmada", "Pendiente",
)


class ICalService:
    """Service for iCal feed synchronization."""

    # ==========================================
    # IMPORT — Pull from OTA iCal URLs
    # ==========================================

    @staticmethod
    @with_db
    def sync_feed(db: Session, feed_id: int) -> Dict[str, Any]:
        """
        Fetch a single iCal feed URL, parse VEVENTs, upsert reservations,
        detect cancellations + conflicts, write a sync log row, and update
        per-feed health.

        Returns: {
            created, updated, flagged_for_review, conflicts, errors,
            duration_ms, status: 'OK'|'ERROR'
        }
        """
        from services.ical_sync_log_service import ICalSyncLogService

        started_at = datetime.now()
        feed = db.query(ICalFeed).filter(ICalFeed.id == feed_id).first()
        if not feed:
            return {
                "created": 0, "updated": 0, "flagged_for_review": 0,
                "conflicts": 0, "errors": ["Feed not found"], "status": "ERROR",
                "duration_ms": 0,
            }

        # Always record the attempt timestamp
        feed.last_sync_attempted_at = started_at

        result = {
            "created": 0, "updated": 0, "flagged_for_review": 0,
            "conflicts": 0, "errors": [],
        }

        # ---- Fetch ----
        try:
            response = requests.get(feed.ical_url, timeout=SYNC_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            error_msg = f"Failed to fetch iCal URL: {e}"
            logger.error(f"Feed #{feed.id} ({feed.source}/{feed.room_id}): {error_msg}")
            result["errors"].append(error_msg)
            return _finalize_sync(db, feed, result, started_at, status="ERROR")

        # ---- Parse ----
        try:
            cal = icalendar.Calendar.from_ical(response.text)
        except Exception as e:
            error_msg = f"Failed to parse iCal data: {e}"
            logger.error(f"Feed #{feed.id} ({feed.source}/{feed.room_id}): {error_msg}")
            result["errors"].append(error_msg)
            return _finalize_sync(db, feed, result, started_at, status="ERROR")

        # ---- Process events ----
        current_uids: Set[str] = set()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            try:
                uid = str(component.get("uid", ""))
                if not uid:
                    continue
                current_uids.add(uid)

                dtstart = component.get("dtstart")
                dtend = component.get("dtend")
                summary = str(component.get("summary", "OTA Guest"))
                description = str(component.get("description", "") or "")

                if not dtstart or not dtend:
                    continue

                check_in = dtstart.dt
                check_out = dtend.dt

                # Normalize to date objects (iCal can return date or datetime)
                if isinstance(check_in, datetime):
                    check_in = check_in.date()
                if isinstance(check_out, datetime):
                    check_out = check_out.date()

                stay_days = (check_out - check_in).days
                if stay_days <= 0:
                    continue

                # Conflict detection: another reservation on same room overlapping these dates
                conflict = _check_room_conflict(
                    db, room_id=feed.room_id,
                    check_in=check_in, check_out=check_out,
                    excluding_external_id=uid,
                )
                if conflict:
                    result["conflicts"] += 1
                    logger.warning(
                        f"Feed #{feed.id} CONFLICT: VEVENT UID {uid} ({check_in} -> {check_out}) "
                        f"overlaps with reservation {conflict.id} ({conflict.guest_name}). "
                        f"OTA data is authoritative — creating anyway."
                    )

                # Extract OTA booking ID hint from DESCRIPTION
                ota_booking_id = _extract_ota_booking_id(description)

                # Upsert
                existing = db.query(Reservation).filter(
                    Reservation.external_id == uid
                ).first()

                if existing:
                    changed = False
                    if existing.check_in_date != check_in:
                        existing.check_in_date = check_in
                        changed = True
                    if existing.stay_days != stay_days:
                        existing.stay_days = stay_days
                        changed = True
                    if ota_booking_id and not existing.ota_booking_id:
                        existing.ota_booking_id = ota_booking_id
                        changed = True
                    # If reservation was previously flagged for review and the
                    # UID reappeared, clear the flag (likely a transient OTA glitch)
                    if existing.needs_review:
                        existing.needs_review = False
                        existing.review_reason = None
                        changed = True
                        logger.info(
                            f"Feed #{feed.id}: reservation {existing.id} review flag cleared "
                            f"(UID {uid} reappeared in feed)"
                        )
                    if changed:
                        existing.updated_at = datetime.now()
                        result["updated"] += 1
                else:
                    # Generate next reservation ID
                    last_res = db.query(Reservation).order_by(
                        Reservation.id.desc()
                    ).first()
                    try:
                        next_id = str(int(last_res.id) + 1).zfill(7) if last_res else "0001255"
                    except (ValueError, TypeError):
                        next_id = str(int(datetime.now().timestamp()))

                    new_res = Reservation(
                        id=next_id,
                        check_in_date=check_in,
                        stay_days=stay_days,
                        guest_name=_extract_guest_name(summary),
                        room_id=feed.room_id,
                        source=feed.source,
                        external_id=uid,
                        ota_booking_id=ota_booking_id,
                        status="Confirmada",
                        price=0,  # OTA manages pricing
                        reserved_by=feed.source,
                        received_by="iCal Sync",
                        property_id="los-monges",
                    )
                    db.add(new_res)
                    db.flush()  # so subsequent ID generations see this row
                    result["created"] += 1

            except Exception as e:
                error_msg = f"Error processing VEVENT: {e}"
                logger.warning(f"Feed #{feed.id}: {error_msg}")
                result["errors"].append(error_msg)

        # ---- Detect cancellations: UIDs that were in our DB but disappeared from feed ----
        flagged = _flag_disappeared_reservations(db, feed, current_uids)
        result["flagged_for_review"] = len(flagged)
        for res in flagged:
            logger.error(
                f"OTA CANCELLATION DETECTED: reservation {res.id} ({res.guest_name}) "
                f"disappeared from {feed.source} feed (UID {res.external_id}). "
                f"Flagged for operator review."
            )

        # ---- Finalize ----
        status = "ERROR" if result["errors"] else "OK"
        return _finalize_sync(db, feed, result, started_at, status=status)

    @staticmethod
    @with_db
    def sync_all_feeds(db: Session) -> Dict[str, Any]:
        """Sync all enabled feeds. Returns aggregated results."""
        feeds = db.query(ICalFeed).filter(ICalFeed.sync_enabled == 1).all()
        feed_ids = [f.id for f in feeds]

        totals = {
            "created": 0, "updated": 0,
            "flagged_for_review": 0, "conflicts": 0,
            "errors": [], "feeds_synced": 0,
        }

        for feed_id in feed_ids:
            result = ICalService.sync_feed(db=db, feed_id=feed_id)
            totals["created"] += result.get("created", 0)
            totals["updated"] += result.get("updated", 0)
            totals["flagged_for_review"] += result.get("flagged_for_review", 0)
            totals["conflicts"] += result.get("conflicts", 0)
            totals["errors"].extend(result.get("errors", []))
            totals["feeds_synced"] += 1

        logger.info(
            f"iCal sync all: {totals['feeds_synced']} feeds, "
            f"created={totals['created']}, updated={totals['updated']}, "
            f"flagged={totals['flagged_for_review']}, conflicts={totals['conflicts']}"
        )
        return totals

    @staticmethod
    def sync_all_feeds_standalone():
        """
        Standalone sync (creates its own DB session).
        Used by background auto-sync task — NOT via FastAPI Depends.
        """
        db = session_factory()
        try:
            feeds = db.query(ICalFeed).filter(ICalFeed.sync_enabled == 1).all()
            feed_ids = [f.id for f in feeds]

            for feed_id in feed_ids:
                ICalService.sync_feed(db=db, feed_id=feed_id)
        except Exception as e:
            logger.error(f"iCal standalone sync error: {e}")
            db.rollback()
        finally:
            db.close()

    # ==========================================
    # EXPORT — Generate .ics for OTAs to pull
    # ==========================================

    @staticmethod
    @with_db
    def generate_ical_for_room(db: Session, room_id: str) -> str:
        """Generate .ics calendar content for a specific room."""
        cal = icalendar.Calendar()
        cal.add("prodid", "-//Hotel PMS//")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")

        # Get room info for calendar name
        room = db.query(Room).filter(Room.id == room_id).first()
        room_label = room.internal_code if room else room_id
        cal.add("x-wr-calname", f"Hotel - {room_label}")

        reservations = db.query(Reservation).filter(
            Reservation.room_id == room_id,
            Reservation.status != "Cancelada",
            Reservation.check_in_date >= date.today() - timedelta(days=30),
        ).all()

        for res in reservations:
            event = icalendar.Event()
            event.add("uid", f"{res.id}@hotel-pms")
            event.add("dtstart", res.check_in_date)
            check_out = res.check_in_date + timedelta(days=res.stay_days)
            event.add("dtend", check_out)
            event.add("summary", f"Reserved - {res.guest_name or 'Guest'}")
            event.add("dtstamp", res.created_at or datetime.now())
            if res.source:
                event.add("description", f"Source: {res.source}")
            cal.add_component(event)

        return cal.to_ical().decode()

    @staticmethod
    @with_db
    def generate_ical_all_rooms(db: Session) -> str:
        """Generate master .ics calendar for all rooms."""
        cal = icalendar.Calendar()
        cal.add("prodid", "-//Hotel PMS//")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", "Hotel - All Rooms")

        reservations = db.query(Reservation).filter(
            Reservation.status != "Cancelada",
            Reservation.check_in_date >= date.today() - timedelta(days=30),
        ).all()

        # Build room label lookup
        rooms = db.query(Room).all()
        room_labels = {r.id: r.internal_code for r in rooms}

        for res in reservations:
            event = icalendar.Event()
            event.add("uid", f"{res.id}@hotel-pms")
            event.add("dtstart", res.check_in_date)
            check_out = res.check_in_date + timedelta(days=res.stay_days)
            event.add("dtend", check_out)
            room_label = room_labels.get(res.room_id, res.room_id)
            event.add("summary", f"{room_label} - {res.guest_name or 'Guest'}")
            event.add("dtstamp", res.created_at or datetime.now())
            cal.add_component(event)

        return cal.to_ical().decode()

    # ==========================================
    # FEED CRUD
    # ==========================================

    @staticmethod
    @with_db
    def get_all_feeds(db: Session) -> List[Dict[str, Any]]:
        """List all configured iCal feeds, including v1.5.0 health fields."""
        feeds = db.query(ICalFeed).all()
        # Build room label lookup
        rooms = db.query(Room).all()
        room_labels = {r.id: r.internal_code for r in rooms}

        return [
            {
                "id": f.id,
                "room_id": f.room_id,
                "room_label": room_labels.get(f.room_id, f.room_id),
                "source": f.source,
                "ical_url": f.ical_url,
                "last_synced_at": f.last_synced_at.isoformat() if f.last_synced_at else None,
                "sync_enabled": bool(f.sync_enabled),
                "created_at": f.created_at.isoformat() if f.created_at else None,
                # v1.5.0 health fields
                "last_sync_status": f.last_sync_status or "NEVER",
                "last_sync_error": f.last_sync_error,
                "consecutive_failures": f.consecutive_failures or 0,
                "last_sync_attempted_at": (
                    f.last_sync_attempted_at.isoformat() if f.last_sync_attempted_at else None
                ),
                "health_badge": _health_badge(f),
            }
            for f in feeds
        ]

    @staticmethod
    @with_db
    def get_feed_health(db: Session, feed_id: int) -> Optional[Dict[str, Any]]:
        """Return per-feed health summary or None if not found."""
        f = db.query(ICalFeed).filter(ICalFeed.id == feed_id).first()
        if not f:
            return None
        room = db.query(Room).filter(Room.id == f.room_id).first()
        return {
            "feed_id": f.id,
            "source": f.source,
            "room_id": f.room_id,
            "room_label": room.internal_code if room else f.room_id,
            "last_sync_status": f.last_sync_status or "NEVER",
            "last_sync_error": f.last_sync_error,
            "consecutive_failures": f.consecutive_failures or 0,
            "last_sync_attempted_at": f.last_sync_attempted_at,
            "last_synced_at": f.last_synced_at,
            "health_badge": _health_badge(f),
        }

    @staticmethod
    @with_db
    def create_feed(db: Session, room_id: str, source: str, ical_url: str) -> Dict[str, Any]:
        """Create a new iCal feed configuration."""
        feed = ICalFeed(
            room_id=room_id,
            source=source,
            ical_url=ical_url,
        )
        db.add(feed)
        db.commit()
        db.refresh(feed)
        return {"id": feed.id, "room_id": feed.room_id, "source": feed.source}

    @staticmethod
    @with_db
    def delete_feed(db: Session, feed_id: int) -> bool:
        """Delete an iCal feed."""
        feed = db.query(ICalFeed).filter(ICalFeed.id == feed_id).first()
        if not feed:
            return False
        db.delete(feed)
        db.commit()
        return True

    @staticmethod
    @with_db
    def toggle_feed(db: Session, feed_id: int, enabled: bool) -> bool:
        """Enable or disable a feed."""
        feed = db.query(ICalFeed).filter(ICalFeed.id == feed_id).first()
        if not feed:
            return False
        feed.sync_enabled = 1 if enabled else 0
        db.commit()
        return True


def _health_badge(feed: ICalFeed) -> str:
    """Map feed state to a UI badge: healthy | warning | error | unknown."""
    status = feed.last_sync_status or "NEVER"
    failures = feed.consecutive_failures or 0
    if status == "NEVER" or feed.last_sync_attempted_at is None:
        return "unknown"
    if failures >= DISCORD_ALERT_THRESHOLD:
        return "error"
    if failures >= 1 or status == "ERROR":
        return "warning"
    return "healthy"


def _extract_guest_name(summary: str) -> str:
    """
    Extract guest name from iCal SUMMARY field.
    Booking.com format: "CLOSED - John Doe" or just "John Doe"
    Airbnb format: "John Doe" or "Reserved - John Doe"
    """
    if not summary:
        return "OTA Guest"

    # Remove common prefixes
    for prefix in ["CLOSED - ", "Reserved - ", "Not available - ", "Airbnb (Not available)"]:
        if summary.startswith(prefix):
            summary = summary[len(prefix):].strip()
            break

    return summary if summary else "OTA Guest"


def _extract_ota_booking_id(description: str) -> Optional[str]:
    """Try to extract an OTA booking reference from the iCal DESCRIPTION text.

    Common patterns:
      - Booking.com: "Reservation: 1234567890"
      - Airbnb: "Reservation URL: https://www.airbnb.com/reservations/HMABCDEFGH"
      - Vrbo: "Reservation ID: HA-1234"
    Returns the matched id string or None.
    """
    if not description:
        return None
    import re
    patterns = [
        r"Reservation\s*(?:ID|#|number)?\s*[:#]?\s*([A-Z0-9\-]{6,})",
        r"Booking\s*(?:ID|number|reference)\s*[:#]?\s*([A-Z0-9\-]{6,})",
        r"airbnb\.com/reservations?/([A-Z0-9]{6,})",
        r"vrbo\.com/.*?/([A-Z0-9\-]{6,})",
    ]
    for pat in patterns:
        m = re.search(pat, description, re.IGNORECASE)
        if m:
            return m.group(1)[:64]  # truncate just in case
    return None


def _check_room_conflict(
    db: Session,
    room_id: str,
    check_in: date,
    check_out: date,
    excluding_external_id: Optional[str] = None,
) -> Optional[Reservation]:
    """Return the first existing reservation that overlaps [check_in, check_out)
    on this room (excluding the same UID), or None.

    Note: SQL can't compute `check_in_date + stay_days` directly, so we filter
    candidates by room/status in SQL and check the date math in Python.
    """
    candidates = db.query(Reservation).filter(
        Reservation.room_id == room_id,
        Reservation.status.in_(ACTIVE_RESERVATION_STATES),
    ).all()
    for r in candidates:
        if excluding_external_id and r.external_id == excluding_external_id:
            continue
        try:
            r_checkout = r.check_in_date + timedelta(days=int(r.stay_days or 0))
        except Exception:
            continue
        # Half-open interval overlap test
        if r.check_in_date < check_out and r_checkout > check_in:
            return r
    return None


def _flag_disappeared_reservations(
    db: Session,
    feed: ICalFeed,
    current_uids: Set[str],
) -> List[Reservation]:
    """Find local reservations whose external_id was previously synced from this
    feed but no longer appears in the current feed payload, and mark them
    needs_review=True.

    Returns the list of newly flagged reservations.
    """
    # Only consider reservations that originated from this feed's source + room
    candidates = db.query(Reservation).filter(
        Reservation.source == feed.source,
        Reservation.room_id == feed.room_id,
        Reservation.external_id.isnot(None),
        Reservation.status.in_(ACTIVE_RESERVATION_STATES),
        Reservation.needs_review == False,
    ).all()

    newly_flagged: List[Reservation] = []
    for r in candidates:
        if r.external_id not in current_uids:
            r.needs_review = True
            r.review_reason = (
                f"UID {r.external_id} desaparecio del feed {feed.source} "
                f"el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            newly_flagged.append(r)
    return newly_flagged


def _finalize_sync(
    db: Session,
    feed: ICalFeed,
    result: Dict[str, Any],
    started_at: datetime,
    status: str,
) -> Dict[str, Any]:
    """Update feed health, write sync log, prune old logs, commit."""
    from services.ical_sync_log_service import ICalSyncLogService

    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
    error_text = "; ".join(result["errors"][:3]) if result["errors"] else None

    # Update feed health
    feed.last_sync_status = status
    if status == "OK":
        feed.consecutive_failures = 0
        feed.last_synced_at = datetime.now()
        feed.last_sync_error = None
    else:
        feed.consecutive_failures = (feed.consecutive_failures or 0) + 1
        feed.last_sync_error = (error_text or "Unknown error")[:500]

    db.commit()

    # Write sync log row (own commit)
    try:
        ICalSyncLogService.record(
            feed_id=feed.id,
            status=status,
            created_count=result["created"],
            updated_count=result["updated"],
            flagged_for_review_count=result["flagged_for_review"],
            conflicts_detected=result["conflicts"],
            error_message=error_text,
            duration_ms=duration_ms,
        )
        # Prune old logs to keep table small
        ICalSyncLogService.prune(feed_id=feed.id, keep=SYNC_LOG_KEEP)
    except Exception as e:
        logger.warning(f"Could not write/prune sync log for feed {feed.id}: {e}")

    # Discord alert if too many consecutive failures (relies on DiscordWebhookHandler)
    if status == "ERROR" and feed.consecutive_failures >= DISCORD_ALERT_THRESHOLD:
        logger.error(
            f"iCal feed #{feed.id} ({feed.source}/{feed.room_id}) has "
            f"{feed.consecutive_failures} consecutive failures. "
            f"Last error: {feed.last_sync_error}"
        )

    logger.info(
        f"iCal sync feed {feed.id} ({feed.source}): status={status}, "
        f"created={result['created']}, updated={result['updated']}, "
        f"flagged={result['flagged_for_review']}, conflicts={result['conflicts']}, "
        f"errors={len(result['errors'])}, duration={duration_ms}ms"
    )

    result["status"] = status
    result["duration_ms"] = duration_ms
    return result
