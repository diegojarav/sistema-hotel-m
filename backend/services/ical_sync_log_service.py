"""
ICalSyncLog Service
====================
Audit trail for iCal sync attempts. Each sync (success or failure) inserts
one row, with counts and error context. Pruned to last N entries per feed
to keep the table small.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import ICalSyncLog
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class ICalSyncLogService:
    """Read/write helpers for the ical_sync_log table."""

    @staticmethod
    @with_db
    def record(
        db: Session,
        feed_id: int,
        status: str,
        created_count: int = 0,
        updated_count: int = 0,
        flagged_for_review_count: int = 0,
        conflicts_detected: int = 0,
        error_message: Optional[str] = None,
        duration_ms: int = 0,
    ) -> ICalSyncLog:
        """Insert a single sync attempt log row."""
        if status not in ("OK", "ERROR"):
            status = "ERROR"
        log = ICalSyncLog(
            feed_id=feed_id,
            attempted_at=datetime.now(),
            status=status,
            created_count=created_count,
            updated_count=updated_count,
            flagged_for_review_count=flagged_for_review_count,
            conflicts_detected=conflicts_detected,
            error_message=(error_message or "")[:500] or None,
            duration_ms=int(max(0, duration_ms)),
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    @with_db
    def list_for_feed(db: Session, feed_id: int, limit: int = 20) -> List[ICalSyncLog]:
        """Return the N most recent sync attempts for a feed (newest first)."""
        return (
            db.query(ICalSyncLog)
            .filter(ICalSyncLog.feed_id == feed_id)
            .order_by(desc(ICalSyncLog.attempted_at))
            .limit(limit)
            .all()
        )

    @staticmethod
    @with_db
    def prune(db: Session, feed_id: int, keep: int = 100) -> int:
        """Delete all but the most recent `keep` log entries for a feed.

        Returns the number of rows deleted.
        """
        # Find the cutoff id (id of the Nth most recent row)
        rows = (
            db.query(ICalSyncLog.id)
            .filter(ICalSyncLog.feed_id == feed_id)
            .order_by(desc(ICalSyncLog.attempted_at))
            .limit(keep)
            .all()
        )
        if len(rows) < keep:
            return 0  # Nothing to prune

        keep_ids = {r[0] for r in rows}
        deleted = (
            db.query(ICalSyncLog)
            .filter(
                ICalSyncLog.feed_id == feed_id,
                ~ICalSyncLog.id.in_(keep_ids),
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info(f"Pruned {deleted} old sync log row(s) for feed {feed_id}")
        return deleted
