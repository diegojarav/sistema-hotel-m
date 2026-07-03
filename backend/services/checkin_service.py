"""
CheckInService — per-stay registration (ficha) records.
========================================================

Manages the `checkins` table: one row per guest registration at the front desk
(name + document + vehicle + billing). Distinct from `GuestService` (in
`guest_service.py`) which manages the master `guests` table — the *person*
who stays across multiple visits.

Historical note
---------------
Up to v1.10.0 this class was called `GuestService` and lived in
`guest_service.py`. Phase 2a introduced the master `Guest` entity, freeing the
`GuestService` name for the proper concept. The rename is mechanical — the
methods (register_checkin, get_checkin, search_checkins, etc.) keep their
signatures verbatim.

Cross-link with Guest master
----------------------------
`CheckIn.guest_id` (added in Phase 2a) optionally links this stay to the
master Guest record. `register_checkin` resolves and writes that link via
`GuestService.find_or_create_guest`. Existing code paths that pre-date
Phase 2a still work — `guest_id` is nullable.
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import CheckIn
from typing import List, Optional, Dict
from datetime import date, datetime

from logging_config import get_logger
from schemas import CheckInCreate, CheckInDetail
from services._base import with_db

logger = get_logger(__name__)


class CheckInService:
    @staticmethod
    @with_db
    def register_checkin(db: Session, data: CheckInCreate) -> int:
        """
        Registers a new guest check-in (Ficha).

        FEAT-LINK-01: Prevents duplicates - if a CheckIn with the same
        document_number exists, updates it instead of creating a new one.

        Phase 2a: Also resolves/creates the master Guest record and links it
        via `checkin.guest_id`. The guest link is best-effort — if the guest
        resolution fails for any reason (validation, race), the check-in
        still succeeds with `guest_id=None`.
        """
        # Check for duplicate by document_number
        if data.document_number and data.document_number.strip():
            existing = db.query(CheckIn).filter(
                CheckIn.document_number == data.document_number.strip()
            ).first()

            if existing:
                # Update existing instead of creating duplicate
                logger.info(f"Updating existing CheckIn #{existing.id} for doc {data.document_number[:5]}...")
                existing.room_id = data.room_id or existing.room_id
                existing.reservation_id = data.reservation_id or existing.reservation_id
                if data.check_in_time:
                    existing.check_in_time = data.check_in_time.time()
                existing.last_name = data.last_name or existing.last_name
                existing.first_name = data.first_name or existing.first_name
                existing.nationality = data.nationality or existing.nationality
                existing.birth_date = data.birth_date or existing.birth_date
                existing.origin = data.origin or existing.origin
                existing.destination = data.destination or existing.destination
                existing.civil_status = data.civil_status or existing.civil_status
                existing.country = data.country or existing.country
                existing.billing_name = data.billing_name or existing.billing_name
                existing.billing_ruc = data.billing_ruc or existing.billing_ruc
                existing.vehicle_model = data.vehicle_model or existing.vehicle_model
                existing.vehicle_plate = data.vehicle_plate or existing.vehicle_plate

                # Phase 2a: refresh guest link if missing, then propagate any
                # newly-captured field values to the master Guest (Bug #2 Fix C).
                # Also persist contact fields (phone/email) before propagating.
                existing.contact_phone = (
                    getattr(data, 'contact_phone', None) or existing.contact_phone
                )
                existing.contact_email = (
                    getattr(data, 'contact_email', None) or existing.contact_email
                )
                if not existing.guest_id:
                    existing.guest_id = _try_link_guest(db, existing)
                _augment_guest_from_checkin(db, existing)
                # Phase 2a-ext: auto-create BillingProfile + GuestVehicle from
                # the snapshot fields so the master domain stays in sync.
                _propagate_billing_to_profile(db, existing)
                _propagate_vehicle_to_master(
                    db, existing, color=getattr(data, 'vehicle_color', None),
                )
                db.commit()
                return existing.id

        # Create new CheckIn
        new_checkin = CheckIn(
            created_at=datetime.now().date(),
            room_id=data.room_id,
            reservation_id=data.reservation_id,
            check_in_time=data.check_in_time.time() if data.check_in_time else None,
            last_name=data.last_name,
            first_name=data.first_name,
            nationality=data.nationality,
            birth_date=data.birth_date,
            origin=data.origin,
            destination=data.destination,
            civil_status=data.civil_status,
            document_number=data.document_number,
            country=data.country,
            contact_phone=getattr(data, 'contact_phone', '') or '',
            contact_email=getattr(data, 'contact_email', '') or '',
            billing_name=data.billing_name,
            billing_ruc=data.billing_ruc,
            vehicle_model=data.vehicle_model,
            vehicle_plate=data.vehicle_plate,
            digital_signature="Pendiente"
        )
        db.add(new_checkin)
        db.flush()  # need ID before committing for guest link

        # Phase 2a: link to master Guest (best-effort)
        new_checkin.guest_id = _try_link_guest(db, new_checkin)

        # Phase 2a-ext: auto-propagate to BillingProfile + GuestVehicle
        # (does nothing if guest_id couldn't be resolved or fields are blank).
        _propagate_billing_to_profile(db, new_checkin)
        _propagate_vehicle_to_master(
            db, new_checkin, color=getattr(data, 'vehicle_color', None),
        )

        db.commit()
        db.refresh(new_checkin)
        logger.info(f"Created new CheckIn #{new_checkin.id}")
        return new_checkin.id

    @staticmethod
    @with_db
    def get_billing_history(db: Session, doc_number: str) -> List[Dict]:
        """Finds previous billing info for this document."""
        # Query distinct billing info
        results = db.query(CheckIn.billing_name, CheckIn.billing_ruc)\
            .filter(CheckIn.document_number == doc_number)\
            .group_by(CheckIn.billing_name, CheckIn.billing_ruc).all()

        return [{"Facturacion_Nombre": r[0], "Facturacion_RUC": r[1]} for r in results if r[0]]

    @staticmethod
    @with_db
    def get_all_guest_names(db: Session) -> List[str]:
        """Returns a list of 'Lastname, Firstname' for all guests."""
        guests = db.query(CheckIn.last_name, CheckIn.first_name, CheckIn.document_number).distinct().all()

        formatted_names = []
        for g in guests:
            l = g.last_name or ""
            f = g.first_name or ""
            d = g.document_number or ""

            # Skip only if absolutely no name info
            if not l and not f:
                continue

            full_name = f"{l}, {f}".strip(", ")
            if d:
                full_name += f" ({d})"

            formatted_names.append(full_name)

        return sorted(list(set(formatted_names)))

    @staticmethod
    @with_db
    def get_all_billing_profiles(db: Session) -> List[Dict[str, str]]:
        """Returns unique billing profiles {name, ruc}."""
        results = db.query(CheckIn.billing_name, CheckIn.billing_ruc)\
            .filter(CheckIn.billing_name != "").distinct().all()

        # Return unique combos
        profiles = []
        seen = set()
        for r in results:
            if r.billing_name and (r.billing_name, r.billing_ruc) not in seen:
                profiles.append({"name": r.billing_name, "ruc": r.billing_ruc})
                seen.add((r.billing_name, r.billing_ruc))
        return sorted(profiles, key=lambda x: x['name'])

    @staticmethod
    @with_db
    def get_checkin(db: Session, checkin_id: int) -> Optional[CheckInDetail]:
        c = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if not c: return None
        return CheckInDetail(
            id=c.id,
            guest_id=c.guest_id,
            billing_profile_id=c.billing_profile_id,
            reservation_id=c.reservation_id,
            room_id=c.room_id,
            check_in_time=datetime.combine(date.today(), c.check_in_time) if c.check_in_time else None,
            last_name=c.last_name or "",
            first_name=c.first_name or "",
            nationality=c.nationality or "",
            birth_date=c.birth_date,
            origin=c.origin or "",
            destination=c.destination or "",
            civil_status=c.civil_status or "",
            document_number=c.document_number or "",
            country=c.country or "",
            contact_phone=c.contact_phone or "",
            contact_email=c.contact_email or "",
            billing_name=c.billing_name or "",
            billing_ruc=c.billing_ruc or "",
            vehicle_model=c.vehicle_model or "",
            vehicle_plate=c.vehicle_plate or ""
        )

    @staticmethod
    @with_db
    def update_checkin(db: Session, checkin_id: int, data: CheckInCreate) -> bool:
        c = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if not c: return False

        c.room_id = data.room_id
        if data.check_in_time: c.check_in_time = data.check_in_time.time()
        c.last_name = data.last_name
        c.first_name = data.first_name
        c.nationality = data.nationality
        c.birth_date = data.birth_date
        c.origin = data.origin
        c.destination = data.destination
        c.civil_status = data.civil_status
        c.document_number = data.document_number
        c.country = data.country
        # Contact fields are also editable from the ficha form (FEAT-LINK-01).
        # Persist them so Fix C can later propagate to the master Guest.
        c.contact_phone = getattr(data, 'contact_phone', None) or c.contact_phone
        c.contact_email = getattr(data, 'contact_email', None) or c.contact_email
        c.billing_name = data.billing_name
        c.billing_ruc = data.billing_ruc
        c.vehicle_model = data.vehicle_model
        c.vehicle_plate = data.vehicle_plate

        # Phase 2a Bug #2 Fix C: ensure the master Guest link exists, then
        # propagate any NEW field values to the Guest (fill empty, never
        # overwrite). This is how the master record accretes useful info as
        # the recepcionist iterates on the ficha during/after a stay.
        if not c.guest_id:
            c.guest_id = _try_link_guest(db, c)
        _augment_guest_from_checkin(db, c)

        # Phase 2a-ext: keep BillingProfile + GuestVehicle in sync with edits.
        _propagate_billing_to_profile(db, c)
        _propagate_vehicle_to_master(
            db, c, color=getattr(data, 'vehicle_color', None),
        )

        db.commit()
        return True

    @staticmethod
    @with_db
    def search_checkins(db: Session, query: str) -> List[Dict]:
        """Search checkins by name or document."""
        from database import Room

        q = f"%{query}%"
        results = db.query(CheckIn).filter(
            or_(
                CheckIn.last_name.ilike(q),
                CheckIn.first_name.ilike(q),
                CheckIn.document_number.ilike(q),
                CheckIn.billing_name.ilike(q)
            )
        ).order_by(CheckIn.created_at.desc()).limit(20).all()

        # Build room_id -> internal_code lookup
        room_ids = list({c.room_id for c in results if c.room_id})
        rooms_list = db.query(Room).filter(Room.id.in_(room_ids)).all() if room_ids else []
        code_map = {r.id: r.internal_code or r.id for r in rooms_list}

        return [
            {
                "id": c.id,
                "last_name": c.last_name or "",
                "first_name": c.first_name or "",
                "document_number": c.document_number or "",
                "room_id": c.room_id or "",
                "room_code": code_map.get(c.room_id, c.room_id or ""),
                "label": f"{c.last_name}, {c.first_name} ({c.document_number}) - {c.created_at}"
            }
            for c in results
        ]

    @staticmethod
    @with_db
    def get_unlinked_reservations(db: Session) -> List[Dict]:
        """
        Returns reservations that have no linked check-in.

        FEAT-LINK-01: Used in check-in form to show dropdown of reservations
        that can be linked to the current guest.
        """
        from database import Reservation

        # Find reservation IDs that already have a linked checkin
        linked_ids_subq = db.query(CheckIn.reservation_id).filter(
            CheckIn.reservation_id.isnot(None)
        ).subquery()

        # Query unlinked reservations
        unlinked = db.query(Reservation).filter(
            Reservation.status.in_(["Confirmada", "CheckIn"]),
            ~Reservation.id.in_(linked_ids_subq.select())
        ).order_by(Reservation.check_in_date.desc()).limit(50).all()

        return [
            {
                "id": r.id,
                "guest_name": r.guest_name,
                "check_in_date": r.check_in_date.isoformat(),
                "room_id": r.room_id,
                "label": f"{r.guest_name} | {r.check_in_date.strftime('%d/%m/%Y')} | Hab. {r.room_id}"
            }
            for r in unlinked
        ]


def _try_link_guest(db: Session, checkin: CheckIn) -> Optional[int]:
    """Best-effort link to the master Guest entity.

    Returns the guest_id or None on any error. Imported lazily to avoid the
    circular dependency between checkin_service ↔ guest_service.
    """
    try:
        from services.guest_service import GuestService
        from api.core.config import DEFAULT_PROPERTY_ID
        property_id = DEFAULT_PROPERTY_ID  # single-tenant; configurable via env var (v1.10.0)
        if checkin.room_id:
            from database import Room
            room = db.query(Room).filter(Room.id == checkin.room_id).first()
            if room and room.property_id:
                property_id = room.property_id

        guest = GuestService.find_or_create_guest(
            db=db,
            property_id=property_id,
            first_name=checkin.first_name or "",
            last_name=checkin.last_name or "",
            document_number=checkin.document_number,
            email=checkin.contact_email,
            phone=checkin.contact_phone,
            nationality=checkin.nationality,
            country=checkin.country,
            birth_date=checkin.birth_date,  # Phase 2a-ext
        )
        return guest.id if guest else None
    except Exception as e:
        logger.warning(f"Failed to link CheckIn #{checkin.id} to master Guest: {e}")
        return None


def _augment_guest_from_checkin(db: Session, checkin: CheckIn) -> bool:
    """Phase 2a Bug #2 Fix C — propagate ficha edits to the master Guest.

    Walks the contact-and-origin fields. For each field where the master
    Guest is empty AND the checkin has a value, fills the Guest. Never
    overwrites existing data — that would erase recepcionist corrections.

    Returns True if any field was filled. False if guest not found or no
    fields needed filling. Best-effort: any exception is logged and
    swallowed (the checkin update itself is the load-bearing operation).
    """
    if not checkin.guest_id:
        return False
    try:
        from database import Guest
        from services.guest_service import _augment_guest_if_empty
        guest = db.query(Guest).filter(Guest.id == checkin.guest_id).first()
        if guest is None:
            return False
        return _augment_guest_if_empty(
            db, guest,
            document_number=(checkin.document_number or "").strip() or None,
            email=(checkin.contact_email or "").strip() or None,
            phone=(checkin.contact_phone or "").strip() or None,
            nationality=(checkin.nationality or "").strip() or None,
            country=(checkin.country or "").strip() or None,
            birth_date=checkin.birth_date,  # Phase 2a-ext
        )
    except Exception as e:
        logger.warning(f"_augment_guest_from_checkin failed for CheckIn #{checkin.id}: {e}")
        return False


def _propagate_billing_to_profile(db: Session, checkin: CheckIn) -> None:
    """Phase 2a-ext: ensure the checkin's billing data also exists as a
    BillingProfile under the linked guest, and that `checkin.billing_profile_id`
    points at it.

    No-op when:
      - checkin has no guest_id (can't attach a profile)
      - billing_name AND billing_ruc are both blank
      - checkin.billing_profile_id is already set (recepcionist explicitly
        picked an existing profile via the dropdown — respect that choice)
    """
    if not checkin.guest_id or checkin.billing_profile_id:
        return
    name = (checkin.billing_name or "").strip()
    ruc = (checkin.billing_ruc or "").strip()
    if not name and not ruc:
        return
    try:
        from database import Guest
        from services.billing_profile_service import BillingProfileService
        guest = db.query(Guest).filter(Guest.id == checkin.guest_id).first()
        if guest is None:
            return
        prof = BillingProfileService.find_or_create_from_checkin(
            db=db, guest_id=checkin.guest_id, property_id=guest.property_id,
            razon_social=name, ruc=ruc,
        )
        if prof is not None:
            checkin.billing_profile_id = prof.id
    except Exception as e:
        logger.warning(f"_propagate_billing_to_profile failed for CheckIn #{checkin.id}: {e}")


def _propagate_vehicle_to_master(
    db: Session,
    checkin: CheckIn,
    color: Optional[str] = None,
) -> None:
    """Phase 2a-ext: ensure the checkin's vehicle data exists as a
    GuestVehicle, and that there's a CheckinVehicle link for this stay.

    `color` is a separate kwarg (not stored on the CheckIn row — see
    schemas.py CheckInCreate.vehicle_color comment). Passed through to the
    master GuestVehicle, which is the canonical home for color metadata.

    No-op when:
      - checkin has no guest_id
      - vehicle_plate is blank (model alone is not enough — plate is the key)
    """
    if not checkin.guest_id:
        return
    plate = (checkin.vehicle_plate or "").strip().upper()
    if not plate:
        return
    try:
        from database import Guest
        from services.guest_vehicle_service import (
            GuestVehicleError,
            GuestVehicleService,
        )
        guest = db.query(Guest).filter(Guest.id == checkin.guest_id).first()
        if guest is None:
            return
        # Create-or-find vehicle (create_vehicle is idempotent on plate per guest)
        try:
            v = GuestVehicleService.create_vehicle(
                db=db, guest_id=checkin.guest_id, property_id=guest.property_id,
                data={
                    "plate_number": plate,
                    "model": (checkin.vehicle_model or "").strip() or None,
                    "color": (color or "").strip() or None,
                },
            )
        except GuestVehicleError as e:
            # 5-vehicle limit — log + skip the link (data still saved on the snapshot)
            logger.warning(
                f"Vehicle auto-register skipped for CheckIn #{checkin.id} "
                f"(guest #{checkin.guest_id}): {e}"
            )
            return
        # Backfill color on existing vehicle if it was blank (fill empty, never overwrite).
        if color and color.strip() and not (v.color or "").strip():
            v.color = color.strip()
            db.commit()
        # Link to this checkin (idempotent)
        try:
            GuestVehicleService.link_to_checkin(
                db=db, checkin_id=checkin.id, vehicle_id=v.id,
            )
        except GuestVehicleError as e:
            logger.warning(f"link_to_checkin failed for CheckIn #{checkin.id}: {e}")
    except Exception as e:
        logger.warning(f"_propagate_vehicle_to_master failed for CheckIn #{checkin.id}: {e}")
