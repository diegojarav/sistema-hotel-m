from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import CheckIn
from typing import List, Optional, Dict
from datetime import date, datetime

from logging_config import get_logger
from schemas import CheckInCreate
from services._base import with_db

logger = get_logger(__name__)


class GuestService:
    @staticmethod
    @with_db
    def register_checkin(db: Session, data: CheckInCreate) -> int:
        """
        Registers a new guest check-in (Ficha).

        FEAT-LINK-01: Prevents duplicates - if a CheckIn with the same
        document_number exists, updates it instead of creating a new one.
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
            billing_name=data.billing_name,
            billing_ruc=data.billing_ruc,
            vehicle_model=data.vehicle_model,
            vehicle_plate=data.vehicle_plate,
            digital_signature="Pendiente"
        )
        db.add(new_checkin)
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
    def get_checkin(db: Session, checkin_id: int) -> Optional[CheckInCreate]:
        c = db.query(CheckIn).filter(CheckIn.id == checkin_id).first()
        if not c: return None
        return CheckInCreate(
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
        c.billing_name = data.billing_name
        c.billing_ruc = data.billing_ruc
        c.vehicle_model = data.vehicle_model
        c.vehicle_plate = data.vehicle_plate

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
            ~Reservation.id.in_(linked_ids_subq)
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
