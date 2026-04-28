"""
GuestService — master Guest entity (v1.10.0 — Phase 2a).
==========================================================

Manages the `guests` table: one row per *person* who has stayed (or will
stay) at the hotel — across multiple visits, multiple reservations, multiple
check-ins. Distinct from `CheckInService` (in `checkin_service.py`) which
manages the per-stay registration record (ficha).

Identity model
--------------
Auto-incrementing integer ID. No business-key UNIQUE constraint — duplicate
detection is best-effort via `find_or_create_guest`'s priority match
(document → email → phone → exact name). A future de-dup/merge tool will
reconcile rows that turn out to be the same person.

Naming pre-Phase-2a
-------------------
Up to v1.10.0 the name `GuestService` was used for what is now
`CheckInService` (per-stay records). The rename happened in Phase 2a; if you
hit an `ImportError`, switch to `from services import CheckInService`.

Public API
----------
- `find_or_create_guest(db, property_id, first_name, last_name, ...)` — entry
  point for the reservation/checkin flow. Smart-matches existing guests.
- `create_guest(db, property_id, data)` — explicit creation (admin UI).
- `get_guest(db, guest_id)` — single-row fetch.
- `update_guest(db, guest_id, data)` — partial update.
- `list_guests(db, property_id, ...)` — paginated list with optional filters.
- `search_guests(db, property_id, query)` — autocomplete-style search.
- `get_guest_history(db, guest_id)` — reservation aggregate + per-reservation
  detail.
- `refresh_aggregates(db, guest_id)` — recompute total_stays/total_spent/
  last_visit_at. Called opportunistically; not load-bearing.
"""

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import Guest, Reservation, Room
from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class GuestServiceError(Exception):
    """Raised on Guest-master business-rule violations (Spanish-friendly)."""


class GuestService:

    # ------------------------------------------------------------------
    # Create / read / update
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def create_guest(db: Session, property_id: str, data: Dict[str, Any]) -> Guest:
        """Create a brand-new master Guest row.

        `data` is a dict (typically the validated dump from `GuestCreate`).
        Required keys: first_name, last_name. All other fields optional.
        Raises `GuestServiceError` on missing required fields.
        """
        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        if not first and not last:
            raise GuestServiceError("El huésped debe tener al menos un nombre o apellido")

        guest = Guest(
            property_id=property_id,
            first_name=first or "(sin nombre)",
            last_name=last or "(sin apellido)",
            document_type=_strip_or_none(data.get("document_type")),
            document_number=_strip_or_none(data.get("document_number")),
            email=_strip_or_none(data.get("email")),
            phone=_strip_or_none(data.get("phone")),
            nationality=_strip_or_none(data.get("nationality")),
            country=_strip_or_none(data.get("country")),
            city=_strip_or_none(data.get("city")),
            notes=_strip_or_none(data.get("notes")),
            source=data.get("source") or "Direct",
            birth_date=data.get("birth_date"),  # Phase 2a-ext
            is_active=True,
            total_stays=0,
            total_spent=0.0,
        )
        db.add(guest)
        db.commit()
        db.refresh(guest)
        logger.info(f"Created Guest #{guest.id} ({last}, {first}) for property {property_id}")
        return guest

    @staticmethod
    @with_db
    def get_guest(db: Session, guest_id: int) -> Optional[Guest]:
        """Fetch a single guest by id (or None if missing)."""
        return db.query(Guest).filter(Guest.id == guest_id).first()

    @staticmethod
    @with_db
    def update_guest(db: Session, guest_id: int, data: Dict[str, Any]) -> Optional[Guest]:
        """Partial update — only the keys present in `data` are written.

        Returns the updated guest, or None if not found.
        """
        guest = db.query(Guest).filter(Guest.id == guest_id).first()
        if not guest:
            return None

        # Apply each field if present (None = clear, missing key = leave alone)
        for col in (
            "first_name", "last_name", "document_type", "document_number",
            "email", "phone", "nationality", "country", "city", "notes",
            "source",
        ):
            if col in data:
                val = data[col]
                if isinstance(val, str):
                    val = val.strip() or None
                setattr(guest, col, val)

        if "birth_date" in data:
            # `None` is a valid clear; date stays as-is. No string trim needed.
            guest.birth_date = data["birth_date"]

        if "is_active" in data and data["is_active"] is not None:
            guest.is_active = bool(data["is_active"])

        guest.updated_at = datetime.now()
        db.commit()
        db.refresh(guest)
        return guest

    # ------------------------------------------------------------------
    # List + search
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def list_guests(
        db: Session,
        property_id: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
    ) -> List[Guest]:
        """Paginated list, ordered by last_name, first_name."""
        q = db.query(Guest).filter(Guest.property_id == property_id)
        if active_only:
            q = q.filter(Guest.is_active == True)  # noqa: E712 (Boolean column)
        return q.order_by(Guest.last_name, Guest.first_name).offset(skip).limit(limit).all()

    @staticmethod
    @with_db
    def count_guests(db: Session, property_id: str, active_only: bool = True) -> int:
        """Total guest count for the property (used by paginated list UI)."""
        q = db.query(Guest).filter(Guest.property_id == property_id)
        if active_only:
            q = q.filter(Guest.is_active == True)  # noqa: E712
        return q.count()

    @staticmethod
    @with_db
    def list_guests_for_dropdown(
        db: Session,
        property_id: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Compact list optimised for the reservation/checkin name dropdowns.

        Returns clean labels (NO embedded `(DocNumber)` clutter — that was the
        Phase 2a Bug #1 root cause). Each item carries the guest_id so the
        caller can pass it back as `ReservationCreate.guest_id` to skip the
        fuzzy find_or_create resolution.

        Sorted by total_stays DESC (frequent guests on top), then last_name.

        Result shape (per item):
            {
              "id": int,
              "label": "Apellido, Nombre" + " (CI doc)" if doc set,
              "first_name": str,
              "last_name": str,
              "document_number": Optional[str],
              "email": Optional[str],
              "phone": Optional[str],
              "total_stays": int,
            }
        """
        rows = (
            db.query(Guest)
            .filter(Guest.property_id == property_id)
            .filter(Guest.is_active == True)  # noqa: E712
            .order_by(Guest.total_stays.desc(), Guest.last_name, Guest.first_name)
            .limit(limit)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for g in rows:
            ln = (g.last_name or "").strip() or "(sin apellido)"
            fn = (g.first_name or "").strip() or "(sin nombre)"
            label = f"{ln}, {fn}"
            if g.document_number:
                label = f"{label} — Doc {g.document_number}"
            out.append({
                "id": g.id,
                "label": label,
                "first_name": g.first_name,
                "last_name": g.last_name,
                "document_number": g.document_number,
                "email": g.email,
                "phone": g.phone,
                "total_stays": g.total_stays or 0,
            })
        return out

    @staticmethod
    @with_db
    def search_guests(
        db: Session,
        property_id: str,
        query: str,
        limit: int = 25,
    ) -> List[Guest]:
        """Search by name, document, email, or phone (case-insensitive substring).

        Returns up to `limit` results, sorted by total_stays DESC then name.
        Empty/short query returns empty list (avoid scanning the full table
        for an accidental autocomplete trigger on first keystroke).
        """
        q = (query or "").strip()
        if len(q) < 2:
            return []

        like = f"%{q}%"
        results = (
            db.query(Guest)
            .filter(Guest.property_id == property_id)
            .filter(Guest.is_active == True)  # noqa: E712
            .filter(or_(
                Guest.last_name.ilike(like),
                Guest.first_name.ilike(like),
                Guest.document_number.ilike(like),
                Guest.email.ilike(like),
                Guest.phone.ilike(like),
            ))
            .order_by(Guest.total_stays.desc(), Guest.last_name, Guest.first_name)
            .limit(limit)
            .all()
        )
        return results

    # ------------------------------------------------------------------
    # Find-or-create — the smart-match entry point
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def find_or_create_guest(
        db: Session,
        property_id: str,
        first_name: str = "",
        last_name: str = "",
        document_number: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        nationality: Optional[str] = None,
        country: Optional[str] = None,
        guest_name: Optional[str] = None,  # legacy "Lastname, Firstname" or full
        source: Optional[str] = None,
        birth_date: Optional[date] = None,  # v1.10.0 Phase 2a-ext
    ) -> Optional[Guest]:
        """Smart match against existing Guest records, or create if new.

        Input parsing (v1.10.0 Phase 2a fix #1):
          - Embedded document numbers are extracted from any of `first_name`,
            `last_name`, or `guest_name` — patterns like `"Acosta, Rosa (2362693)"`
            yield `document_number="2362693"` and clean the name to
            `"Acosta, Rosa"`. The explicit `document_number` arg always wins
            if provided.
          - Whitespace is collapsed and trimmed (`"García  López "` → `"García López"`).

        Match priority (highest → lowest):
          1. `(property_id, document_number)` — STRONGEST. The same physical
             document across two records is unambiguously the same person.
          2. `(property_id, email)` — STRONG. Case-insensitive exact match.
             Skipped if email is invalid (no `@`).
          3. `(property_id, normalized_name)` — WEAK. Used only if no doc/email.
             Compares case-insensitive on first_name + last_name.

        Phone is intentionally NOT a matching tier: people share phones (couples,
        family members), and false-positive merges would corrupt history.
        Pre-fix this WAS tier 3 — it's been demoted because the dedup analysis
        of the dev DB showed phone collisions across distinct travellers.

        If multiple candidates exist at a tier, picks the one with most
        total_stays (likely the same person across stays).

        Side effect (when a guest IS found): if the caller supplied contact
        info (email / phone / nationality / country) that's missing on the
        existing guest, **fill the gaps** — never overwrite. Keeps the master
        record accreting useful info as the same guest returns.

        If no candidate found, creates a new Guest row using the cleaned inputs.

        Returns the Guest (existing or new), or None on any unrecoverable error
        (caller treats as "guest_id stays NULL"). Returns None when there's
        truly nothing to identify with (no name + no doc + no email).
        """
        try:
            # 1. Extract embedded doc numbers from any of the name fields, then
            #    normalize the name. The explicit `document_number` arg wins.
            cleaned_first, embedded_doc_first = _extract_embedded_doc(first_name)
            cleaned_last, embedded_doc_last = _extract_embedded_doc(last_name)
            cleaned_guest_name, embedded_doc_full = _extract_embedded_doc(guest_name)

            # Pick the first non-None document found in any field
            extracted_doc = (
                (document_number or "").strip()
                or embedded_doc_first
                or embedded_doc_last
                or embedded_doc_full
                or ""
            )

            first, last = _resolve_first_last(cleaned_first, cleaned_last, cleaned_guest_name)
            first = _norm_ws(first)
            last = _norm_ws(last)

            doc_norm = extracted_doc.strip() or None
            email_norm = (email or "").strip().lower() or None
            phone_norm = (phone or "").strip() or None

            # 2. Decide if we have ENOUGH to identify a person.
            # Pure-blank input → bail rather than create a placeholder ghost.
            if not first and not last and not doc_norm and not email_norm:
                return None

            base = (
                db.query(Guest)
                .filter(Guest.property_id == property_id)
                .filter(Guest.is_active == True)  # noqa: E712
            )

            hit: Optional[Guest] = None

            # Tier 1: document_number (STRONGEST — never share documents)
            if doc_norm:
                hit = (
                    base.filter(Guest.document_number == doc_norm)
                    .order_by(Guest.total_stays.desc())
                    .first()
                )

            # Tier 2: email
            if hit is None and email_norm and "@" in email_norm:
                hit = (
                    base.filter(Guest.email.ilike(email_norm))
                    .order_by(Guest.total_stays.desc())
                    .first()
                )

            # Tier 3: exact (case-insensitive) name match — only if no
            # stronger identifier was given. We do NOT name-match when a
            # document was provided but didn't hit, because that means the
            # caller is asserting "this is a NEW person with this doc".
            if hit is None and not doc_norm and (first or last):
                hit = (
                    base.filter(Guest.first_name.ilike(first or ""))
                    .filter(Guest.last_name.ilike(last or ""))
                    .order_by(Guest.total_stays.desc())
                    .first()
                )

            if hit is not None:
                # Backfill: never overwrite, only fill empty fields. This is
                # how the master record accretes useful info (e.g. first
                # booking has just name + doc; later booking adds email).
                _augment_guest_if_empty(
                    db, hit,
                    document_number=doc_norm,
                    email=email_norm,
                    phone=phone_norm,
                    nationality=(nationality or "").strip() or None,
                    country=(country or "").strip() or None,
                    birth_date=birth_date,  # v1.10.0 Phase 2a-ext
                )
                return hit

            # No match → create
            return GuestService.create_guest(
                db=db,
                property_id=property_id,
                data={
                    "first_name": first,
                    "last_name": last,
                    "document_number": doc_norm,
                    "email": email_norm,
                    "phone": phone_norm,
                    "nationality": (nationality or "").strip() or None,
                    "country": (country or "").strip() or None,
                    "source": source or "Direct",
                    "birth_date": birth_date,  # v1.10.0 Phase 2a-ext
                },
            )
        except Exception as e:
            logger.warning(f"find_or_create_guest failed: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # History + aggregates
    # ------------------------------------------------------------------

    @staticmethod
    @with_db
    def get_guest_history(db: Session, guest_id: int) -> Optional[Dict[str, Any]]:
        """Reservation history + aggregates for a single guest.

        Returns a dict shaped for `GuestHistoryDTO`:
            {
              "guest": Guest,
              "reservations": [ {id, check_in_date, check_out_date, ...}, ...],
              "total_stays": int,
              "total_spent": float,
              "last_visit_at": date | None,
              "avg_stay_length": float,
            }

        Returns None if the guest doesn't exist.
        """
        guest = db.query(Guest).filter(Guest.id == guest_id).first()
        if not guest:
            return None

        rows = (
            db.query(Reservation)
            .filter(Reservation.guest_id == guest_id)
            .order_by(Reservation.check_in_date.desc())
            .all()
        )

        # Build room_id → internal_code lookup
        room_ids = list({r.room_id for r in rows if r.room_id})
        room_codes = {}
        if room_ids:
            for r in db.query(Room).filter(Room.id.in_(room_ids)).all():
                room_codes[r.id] = r.internal_code or r.id

        reservations = []
        total_spent = 0.0
        total_nights = 0
        last_visit = None
        completed_stays = 0
        for r in rows:
            stay_days = r.stay_days or 1
            check_out = r.check_in_date + timedelta(days=stay_days) if r.check_in_date else None
            price = float(r.final_price or r.price or 0.0)
            reservations.append({
                "id": r.id,
                "check_in_date": r.check_in_date,
                "check_out_date": check_out,
                "stay_days": stay_days,
                "room_id": r.room_id or "",
                "room_internal_code": room_codes.get(r.room_id),
                "status": r.status or "",
                "price": price,
                "source": r.source or "Direct",
            })

            # Aggregates (only count realised stays — not cancelled)
            if (r.status or "").lower() not in ("cancelada", "cancelled"):
                total_spent += price
                total_nights += stay_days
                completed_stays += 1
                if r.check_in_date and (last_visit is None or r.check_in_date > last_visit):
                    last_visit = r.check_in_date

        avg_stay = (total_nights / completed_stays) if completed_stays else 0.0

        return {
            "guest": guest,
            "reservations": reservations,
            "total_stays": completed_stays,
            "total_spent": total_spent,
            "last_visit_at": last_visit,
            "avg_stay_length": round(avg_stay, 1),
        }

    @staticmethod
    @with_db
    def refresh_aggregates(db: Session, guest_id: int) -> Optional[Guest]:
        """Recompute and persist the cached aggregates on the guest row.

        Called opportunistically (after reservation create/cancel/complete).
        Failure is non-fatal — the aggregates are convenience, not load-bearing.
        """
        history = GuestService.get_guest_history(db=db, guest_id=guest_id)
        if not history:
            return None
        guest = history["guest"]
        guest.total_stays = history["total_stays"]
        guest.total_spent = history["total_spent"]
        guest.last_visit_at = history["last_visit_at"]
        guest.updated_at = datetime.now()
        db.commit()
        db.refresh(guest)
        return guest


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _strip_or_none(v: Any) -> Optional[str]:
    """Whitespace-trim a value; treat empty as None."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _digits_only(s: str) -> str:
    """Keep only digit characters (for normalised phone comparison)."""
    return "".join(c for c in (s or "") if c.isdigit())


# Embedded-doc regex: finds "(1234567)" or "(CI 4.567.890)" anywhere in a name
# string. Captures the inner content; downstream re-normalises to digits-only
# for comparison with the canonical document_number column.
_EMBEDDED_DOC_RE = re.compile(r"\s*\(([^)]+)\)\s*")


def _extract_embedded_doc(name: Optional[str]) -> Tuple[str, Optional[str]]:
    """Strip parenthetical content from a name and return the extracted token.

    Returns `(cleaned_name, extracted_doc_or_None)`.

    Examples:
        "Acosta, Rosa (2362693)"        → ("Acosta, Rosa", "2362693")
        "Aquino Gabriel (5859883)"      → ("Aquino Gabriel", "5859883")
        "García López"                  → ("García López", None)
        "(2362693)"                     → ("", "2362693")
        ""                              → ("", None)

    The extracted token is normalized to digits-only when it looks like a doc
    number (≥4 digit chars after stripping non-digits). Otherwise returned
    as the original parenthetical content (lets the caller decide).

    The cleanup is greedy on parens — if multiple parens exist, the FIRST
    one is treated as the doc; later ones are still stripped from the name
    but not extracted (rare in practice).
    """
    if not name:
        return "", None
    s = str(name)
    matches = list(_EMBEDDED_DOC_RE.finditer(s))
    if not matches:
        return s.strip(), None

    # Take the first paren as the doc candidate
    inner = matches[0].group(1).strip()
    cleaned = _EMBEDDED_DOC_RE.sub(" ", s).strip()
    cleaned = _norm_ws(cleaned)

    # Decide if `inner` looks like a document
    digits = _digits_only(inner)
    if len(digits) >= 4:
        # Use the digits-only form (so "CI 4.567.890" becomes "4567890")
        return cleaned, digits
    # Not a document — drop the paren content but don't extract
    return cleaned, None


def _norm_ws(s: Optional[str]) -> str:
    """Collapse multiple whitespace into single spaces and trim."""
    if not s:
        return ""
    return " ".join(str(s).split())


def _augment_guest_if_empty(
    db: Session,
    guest: Guest,
    *,
    document_number: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    nationality: Optional[str] = None,
    country: Optional[str] = None,
    birth_date: Optional[date] = None,
) -> bool:
    """Backfill empty fields on an existing guest. Never overwrite.

    Returns True if any field was filled (and committed), False otherwise.
    Used by `find_or_create_guest` so the master record progressively gains
    info as the same guest returns through different booking channels.
    """
    changed = False
    if document_number and not (guest.document_number or "").strip():
        guest.document_number = document_number
        changed = True
    if email and not (guest.email or "").strip():
        guest.email = email
        changed = True
    if phone and not (guest.phone or "").strip():
        guest.phone = phone
        changed = True
    if nationality and not (guest.nationality or "").strip():
        guest.nationality = nationality
        changed = True
    if country and not (guest.country or "").strip():
        guest.country = country
        changed = True
    if birth_date is not None and guest.birth_date is None:
        guest.birth_date = birth_date
        changed = True
    if changed:
        guest.updated_at = datetime.now()
        db.commit()
        db.refresh(guest)
    return changed


def _resolve_first_last(
    first_name: str,
    last_name: str,
    guest_name: Optional[str],
) -> tuple[str, str]:
    """Resolve (first, last) from raw inputs.

    If first_name + last_name are present, use them. Else parse `guest_name`.
    Heuristic for `guest_name`:
      - "Lastname, Firstname Middle"  → ("Firstname Middle", "Lastname")
      - "Firstname Lastname"           → ("Firstname", "Lastname")
      - Single token                   → ("", token)  (treat as last name)
      - Empty                          → ("", "")
    """
    f = (first_name or "").strip()
    l = (last_name or "").strip()
    if f or l:
        return f, l

    g = (guest_name or "").strip()
    if not g:
        return "", ""

    if "," in g:
        last_part, _, first_part = g.partition(",")
        return first_part.strip(), last_part.strip()

    parts = g.split()
    if len(parts) == 1:
        return "", parts[0]
    # Convention: first token is first_name, the rest is last_name.
    return parts[0], " ".join(parts[1:])
