from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from database import SessionLocal, User, Room, Reservation, CheckIn
from typing import List, Optional, Dict
from datetime import date, datetime, timedelta

# Importar logging centralizado
from logging_config import get_logger

# Importar schemas con validaciones estrictas
from schemas import (
    UserDTO, 
    ReservationCreate, 
    ReservationDTO, 
    CheckInCreate
)

# Logger para este módulo
logger = get_logger(__name__)

# ==========================================
# SERVICES
# ==========================================

def get_db():
    """
    Context manager para obtener sesión thread-safe.
    Uso: with get_db() as db: ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        SessionLocal.remove()


# Helper for direct usage (non-dependency injection style for Streamlit)
# THREAD-SAFE: Usa scoped_session con remove() para limpiar
def with_db(func):
    """
    Decorador que maneja el ciclo de vida de la sesión de forma segura.
    Usa scoped_session, garantizando aislamiento por hilo.
    """
    def wrapper(*args, **kwargs):
        # scoped_session() retorna la sesión del hilo actual
        # Si no existe, la crea automáticamente
        db = SessionLocal()
        try:
            result = func(db, *args, **kwargs)
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"Error in {func.__name__}: {e}")
            raise e
        finally:
            # CRÍTICO: Limpiar la sesión del registry del hilo
            SessionLocal.remove()
    return wrapper


class AuthService:
    """Service for user authentication."""
    
    @staticmethod
    @with_db
    def authenticate(db: Session, username: str, password: str) -> Optional[UserDTO]:
        """
        Verifies user credentials.
        
        Args:
            username: The username.
            password: The password (plain text for now).
            
        Returns:
            UserDTO if successful, None otherwise.
        """
        user = db.query(User).filter(User.username == username).first()
        if user and str(user.password) == str(password):
            return UserDTO(username=user.username, role=user.role, real_name=user.real_name)
        return None

class ReservationService:
    """Service for managing reservations."""

    @staticmethod
    @with_db
    def create_reservations(db: Session, data: ReservationCreate) -> List[str]:
        """
        Creates one or more reservations (one per room).
        """
        created_ids = []
        
        # Generate generic ID base (mimicking old logic or new logic)
        # Using timestamp + random or just sequential if manageable?
        # Let's keep sequential style compatible with strings if possible or just UUID.
        # For compatibility with string ID '0001255', we check max.
        last_res = db.query(Reservation).order_by(Reservation.id.desc()).first()
        try:
            next_id = int(last_res.id) + 1 if last_res else 1255
        except:
            next_id = 1255

        for i, room_id in enumerate(data.room_ids):
            res_id = f"{next_id + i:07d}"
            
            # Helper to calculate check_out
            check_out = data.check_in_date + timedelta(days=data.stay_days) # Logic check only
            
            new_res = Reservation(
                id=res_id,
                created_at=datetime.now(),
                check_in_date=data.check_in_date,
                stay_days=data.stay_days,
                guest_name=data.guest_name,
                room_id=room_id,
                room_type=data.room_type,
                price=data.price,
                arrival_time=data.arrival_time.time() if data.arrival_time else None,
                reserved_by=data.reserved_by,
                contact_phone=data.contact_phone,
                received_by=data.received_by,
                status="Confirmada"
            )
            db.add(new_res)
            created_ids.append(res_id)
        
        db.commit()
        return created_ids

    @staticmethod
    @with_db
    def cancel_reservation(db: Session, res_id: str, reason: str, user: str) -> bool:
        """Cancels a reservation."""
        res = db.query(Reservation).filter(Reservation.id == res_id).first()
        if res:
            res.status = "Cancelada"
            res.cancellation_reason = reason
            res.cancelled_by = user
            db.commit()
            return True
        return False

    @staticmethod
    @with_db
    def get_weekly_view(db: Session, start_date: date) -> Dict[str, Dict[str, str]]:
        """
        Returns a matrix {room_id: {date_str: guest_name}} for the week.
        """
        end_date = start_date + timedelta(days=7)
        
        # Fetch active reservations overlapping this week
        reservations = db.query(Reservation).filter(
            Reservation.status == "Confirmada",
            Reservation.check_in_date <= end_date,
            # Simple overlap logic: start <= end_of_period AND end >= start_of_period
            # Here: res.start + days >= start_date
        ).all()
        
        matrix = {}
        # Pre-fill rooms? handled by UI usually, but let's return data.
        
        dates = [start_date + timedelta(days=i) for i in range(7)]
        
        for res in reservations:
            # Calculate actual end date
            res_end = res.check_in_date + timedelta(days=res.stay_days - 1)
            
            # Check overlap
            if res_end < start_date or res.check_in_date > end_date:
                continue
                
            if res.room_id not in matrix:
                matrix[res.room_id] = {}
                
            for d in dates:
                if res.check_in_date <= d <= res_end:
                    matrix[res.room_id][d.strftime("%Y-%m-%d")] = res.guest_name
                    
        return matrix

    @staticmethod
    @with_db
    def get_daily_status(db: Session, specific_date: date) -> List[Dict]:
        """
        Returns status of all rooms for a specific day.
        """
        # Get all rooms
        rooms = db.query(Room).all()
        room_map = {r.id: {"status": "Libre", "huesped": "-", "type": r.type, "res_id": None} for r in rooms}
        
        # Get reservations active on that day
        reservations = db.query(Reservation).filter(
             Reservation.status == "Confirmada",
             Reservation.check_in_date <= specific_date
        ).all()
        
        for res in reservations:
            res_end = res.check_in_date + timedelta(days=res.stay_days - 1)
            if res.check_in_date <= specific_date <= res_end:
                if res.room_id in room_map:
                    room_map[res.room_id]["status"] = "OCUPADA"
                    room_map[res.room_id]["huesped"] = res.guest_name
                    room_map[res.room_id]["res_id"] = res.id
        
        # Sort by room ID? numeric sort if possible
        result = []
        for rid, info in room_map.items():
            info["room_id"] = rid
            result.append(info)
            
        return sorted(result, key=lambda x: x["room_id"])
    
    @staticmethod
    @with_db
    def get_all_reservations(db: Session) -> List[ReservationDTO]:
        res = db.query(Reservation).order_by(Reservation.created_at.desc()).all()
        return [
            ReservationDTO(
                id=r.id,
                room_id=r.room_id,
                guest_name=r.guest_name,
                status=r.status,
                check_in=r.check_in_date,
                check_out=r.check_in_date + timedelta(days=r.stay_days)
            )
            for r in res
        ]

    @staticmethod
    @with_db
    def get_reservation(db: Session, res_id: str) -> Optional[ReservationCreate]:
        r = db.query(Reservation).filter(Reservation.id == res_id).first()
        if not r: return None
        return ReservationCreate(
            check_in_date=r.check_in_date,
            stay_days=r.stay_days,
            guest_name=r.guest_name,
            room_ids=[r.room_id], # Original stored single, but DTO expects list
            room_type=r.room_type or "",
            price=r.price,
            arrival_time=datetime.combine(date.today(), r.arrival_time) if r.arrival_time else None,
            reserved_by=r.reserved_by or "",
            contact_phone=r.contact_phone or "",
            received_by=r.received_by or ""
        )

    @staticmethod
    @with_db
    def update_reservation(db: Session, res_id: str, data: ReservationCreate) -> bool:
        r = db.query(Reservation).filter(Reservation.id == res_id).first()
        if not r: return False
        
        r.check_in_date = data.check_in_date
        r.stay_days = data.stay_days
        r.guest_name = data.guest_name
        r.room_id = data.room_ids[0] if data.room_ids else r.room_id # Only update if provided
        r.room_type = data.room_type
        r.price = data.price
        r.arrival_time = data.arrival_time.time() if data.arrival_time else None
        r.reserved_by = data.reserved_by
        r.contact_phone = data.contact_phone
        # Received_by usually doesn't change or maybe it does? leaving as is for trace or update
        
        db.commit()
        return True

class GuestService:
    @staticmethod
    @with_db
    def register_checkin(db: Session, data: CheckInCreate) -> int:
        """Registers a new guest check-in (Ficha)."""
        
        new_checkin = CheckIn(
            created_at=datetime.now().date(),
            room_id=data.room_id,
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
        # Distinct guests by document to avoid duplicates in list? 
        # Or just distinct names? Let's try distinct names+doc to be safe or just names.
        # User asked for searchable by first/last.
        # Let's return formatted strings.
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
        q = f"%{query}%"
        results = db.query(CheckIn).filter(
            or_(
                CheckIn.last_name.ilike(q),
                CheckIn.first_name.ilike(q),
                CheckIn.document_number.ilike(q),
                CheckIn.billing_name.ilike(q)
            )
        ).order_by(CheckIn.created_at.desc()).limit(20).all()
        
        return [
            {"id": c.id, "label": f"{c.last_name}, {c.first_name} ({c.document_number}) - {c.created_at}"}
            for c in results
        ]

