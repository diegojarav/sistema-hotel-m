"""
Hotel-day operational logic (v1.10.0 — Phase 2e)
=================================================

A "hotel day" is the hotel's operational day, which does NOT end at midnight
but at the next morning's check-out time. Until check-out happens, the night
of day D is still in progress — the receptionist on the desk at 02:00 of
calendar day D+1 is still working "the night of D".

Why this matters
----------------
Pre-Phase-2e the system rejected any reservation with `check_in_date < today`
(see schemas.py:225 — Pydantic `validate_date_coherence`). At 00:08 of D+1
that's an OPERATIONAL bug: a guest walks in for "tonight" (which started on
D) and the system blocks the booking because D is already "yesterday" by
the wall clock.

The fix is a small utility module that:
  1. Computes the *current hotel day* from the wall clock + the hotel's
     check-out time.
  2. Decides whether a reservation for a given `check_in_date` can still
     be created (the cutoff is the hotel's check-out time on the day
     AFTER `check_in_date`).

Both helpers accept the `check_out_time` (as `time` or "HH:MM" string —
Property stores it as a string) so a hotel that uses e.g. 12:00 check-out
gets the same logic with a later cutoff.

Defaults are the Los Monges defaults (07:00–22:00 check-in / 10:00 check-
out) so callers that don't pass anything still behave sanely.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional, Union

# Hotel-default check-out: 10 AM. Matches Property.check_out_time default.
DEFAULT_CHECK_OUT_TIME = time(10, 0)


def _coerce_time(value: Union[time, str, None], fallback: time = DEFAULT_CHECK_OUT_TIME) -> time:
    """Accept a `time`, an "HH:MM[:SS]" string, or None → fallback.

    Property.check_out_time is stored as a string in the DB; this helper
    lets callers pass either shape without thinking about it.
    """
    if value is None:
        return fallback
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return fallback
        try:
            # "HH:MM" or "HH:MM:SS"
            parts = cleaned.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            second = int(parts[2]) if len(parts) > 2 else 0
            return time(hour, minute, second)
        except (ValueError, IndexError):
            return fallback
    return fallback


def get_current_hotel_day(
    check_out_time: Union[time, str, None] = None,
    *,
    now: Optional[datetime] = None,
) -> date:
    """Return the current operational hotel day.

    Before the check-out wall-clock time, "today" by the calendar is still
    the previous hotel day (yesterday's night hasn't ended yet). After
    check-out, the new hotel day has begun.

    Examples (with check_out=10:00):
        wall clock 2026-05-12 02:00  →  hotel_day = 2026-05-11
        wall clock 2026-05-12 09:59  →  hotel_day = 2026-05-11
        wall clock 2026-05-12 10:00  →  hotel_day = 2026-05-12
        wall clock 2026-05-12 23:30  →  hotel_day = 2026-05-12

    Args:
        check_out_time: the hotel's check-out time (`time` or "HH:MM" string,
            default 10:00).
        now: optional injection for testing — defaults to `datetime.now()`.
    """
    co = _coerce_time(check_out_time)
    moment = now or datetime.now()
    if moment.time() < co:
        return moment.date() - timedelta(days=1)
    return moment.date()


def can_create_reservation_for_date(
    check_in_date: date,
    check_out_time: Union[time, str, None] = None,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Can a reservation be created for `check_in_date` *right now*?

    Allowed as long as the wall-clock hasn't passed the check-out time of
    the day AFTER `check_in_date`. In other words, the night of
    `check_in_date` (which extends until check-out on `check_in_date + 1`)
    is still in progress or in the future.

    Examples (with check_out=10:00):
        check_in=2026-05-11, now=2026-05-11 23:00  →  True  (current night)
        check_in=2026-05-11, now=2026-05-12 02:00  →  True  (still that night)
        check_in=2026-05-11, now=2026-05-12 09:59  →  True  (still that night)
        check_in=2026-05-11, now=2026-05-12 10:01  →  False (night ended)
        check_in=2026-05-20, now=2026-05-12 02:00  →  True  (future)

    Args:
        check_in_date: the proposed check-in date.
        check_out_time: the hotel's check-out time, default 10:00.
        now: optional injection for testing.
    """
    co = _coerce_time(check_out_time)
    moment = now or datetime.now()
    deadline = datetime.combine(check_in_date + timedelta(days=1), co)
    return moment < deadline
