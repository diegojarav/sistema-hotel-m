"""
iCal Sync Service — Booking.com / Airbnb Integration
=====================================================

Handles:
- Import: Pull .ics feeds from OTAs, upsert reservations
- Export: Generate .ics calendars for rooms (OTAs pull these)
- Background sync: Called every 15 minutes by the auto-sync task
"""

import requests
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

import icalendar
from sqlalchemy.orm import Session

from database import Reservation, Room, ICalFeed, session_factory
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)

SYNC_TIMEOUT = 30  # seconds


class ICalService:
    """Service for iCal feed synchronization."""

    # ==========================================
    # IMPORT — Pull from OTA iCal URLs
    # ==========================================

    @staticmethod
    @with_db
    def sync_feed(db: Session, feed_id: int) -> Dict[str, Any]:
        """
        Fetch a single iCal feed URL, parse VEVENTs, upsert reservations.
        Returns: {created: N, updated: N, errors: [...]}
        """
        feed = db.query(ICalFeed).filter(ICalFeed.id == feed_id).first()
        if not feed:
            return {"created": 0, "updated": 0, "errors": ["Feed not found"]}

        result = {"created": 0, "updated": 0, "errors": []}

        try:
            response = requests.get(feed.ical_url, timeout=SYNC_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            error_msg = f"Failed to fetch iCal URL for feed {feed.id}: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result

        try:
            cal = icalendar.Calendar.from_ical(response.text)
        except Exception as e:
            error_msg = f"Failed to parse iCal data for feed {feed.id}: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return result

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            try:
                uid = str(component.get("uid", ""))
                if not uid:
                    continue

                dtstart = component.get("dtstart")
                dtend = component.get("dtend")
                summary = str(component.get("summary", "OTA Guest"))

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

                # Check if reservation with this external_id already exists
                existing = db.query(Reservation).filter(
                    Reservation.external_id == uid
                ).first()

                if existing:
                    # Update dates if changed
                    changed = False
                    if existing.check_in_date != check_in:
                        existing.check_in_date = check_in
                        changed = True
                    if existing.stay_days != stay_days:
                        existing.stay_days = stay_days
                        changed = True
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
                        status="Confirmada",
                        price=0,  # OTA manages pricing
                        reserved_by=feed.source,
                        received_by="iCal Sync",
                        property_id="los-monges",
                    )
                    db.add(new_res)
                    result["created"] += 1

            except Exception as e:
                error_msg = f"Error processing VEVENT in feed {feed.id}: {e}"
                logger.warning(error_msg)
                result["errors"].append(error_msg)

        # Update last synced timestamp
        feed.last_synced_at = datetime.now()
        db.commit()

        logger.info(
            f"iCal sync feed {feed.id} ({feed.source}): "
            f"created={result['created']}, updated={result['updated']}, "
            f"errors={len(result['errors'])}"
        )
        return result

    @staticmethod
    @with_db
    def sync_all_feeds(db: Session) -> Dict[str, Any]:
        """Sync all enabled feeds. Returns aggregated results."""
        feeds = db.query(ICalFeed).filter(ICalFeed.sync_enabled == 1).all()
        feed_ids = [f.id for f in feeds]

        totals = {"created": 0, "updated": 0, "errors": [], "feeds_synced": 0}

        for feed_id in feed_ids:
            result = ICalService.sync_feed(db=db, feed_id=feed_id)
            totals["created"] += result["created"]
            totals["updated"] += result["updated"]
            totals["errors"].extend(result["errors"])
            totals["feeds_synced"] += 1

        logger.info(
            f"iCal sync all: {totals['feeds_synced']} feeds, "
            f"created={totals['created']}, updated={totals['updated']}"
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
        """List all configured iCal feeds."""
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
            }
            for f in feeds
        ]

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
