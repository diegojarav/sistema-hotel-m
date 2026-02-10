from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from database import (
    Room, RoomCategory, Reservation, CheckIn,
    SessionLocal
)
from typing import List, Optional, Dict, Any
import json
from datetime import date, datetime, timedelta

from logging_config import get_logger
from schemas import (
    ReservationCreate,
    ReservationDTO,
    CalendarEventDTO,
    TodaySummaryDTO
)
from services._base import with_db

logger = get_logger(__name__)


class ReservationService:
    """Service for managing reservations."""

    @staticmethod
    @with_db
    def create_reservations(db: Session, data: ReservationCreate) -> List[str]:
        """
        Creates one or more reservations (one per room).
        Integrates PricingService for automatic calculation.
        """
        from services.pricing_service import PricingService
        from services.settings_service import SettingsService

        created_ids = []

        # Generate generic ID base
        last_res = db.query(Reservation).order_by(Reservation.id.desc()).first()
        try:
            next_id = int(last_res.id) + 1 if last_res else 1255
        except:
            next_id = 1255

        # Get default client type if not provided
        default_client_type = "los-monges-particular" # Fallback hardcoded or fetch from settings
        # Try to fetch from settings if needed
        if not data.client_type_id:
             try:
                 from database import SystemSetting
                 setting = db.query(SystemSetting).filter(SystemSetting.setting_key == "default_client_type").first()
                 if setting: default_client_type = setting.setting_value
             except: pass

        client_type_use = data.client_type_id or default_client_type

        # Enforce Parking Capacity (Check BEFORE creating reservations to avoid double counting)
        if data.parking_needed:
             # Check total parking slots
             parking_capacity = SettingsService.get_parking_capacity(db)

             # Overlap logic: (StartA <= EndB) and (EndA >= StartB)
             req_start = data.check_in_date
             req_end = data.check_in_date + timedelta(days=data.stay_days)

             existing_parking_count = db.query(Reservation).filter(
                 Reservation.status.in_(["Confirmada", "CheckIn"]),
                 Reservation.parking_needed == True,
                 Reservation.check_in_date < req_end,
             ).all()

             overlap_count = 0
             for r in existing_parking_count:
                 r_end = r.check_in_date + timedelta(days=r.stay_days)
                 if r.check_in_date < req_end and r_end > req_start:
                     overlap_count += 1

             new_spots_needed = len(data.room_ids)

             if overlap_count + new_spots_needed > parking_capacity:
                 raise Exception(f"Estacionamiento lleno. Capacidad: {parking_capacity}, Ocupados: {overlap_count}, Solicitados: {new_spots_needed}")

        # PERF-001 FIX: Batch fetch all rooms at once to avoid N+1 queries
        rooms_data = db.query(Room).filter(Room.id.in_(data.room_ids)).all()
        room_lookup = {r.id: r for r in rooms_data}

        for i, room_id in enumerate(data.room_ids):
            res_id = f"{next_id + i:07d}"

            # Fetch room details from pre-loaded lookup
            room = room_lookup.get(room_id)
            prop_id = room.property_id if room else "los-monges"
            cat_id = room.category_id if room else (data.category_id or "los-monges-estandar")

            # Calculate Price dynamically
            price_data = PricingService.calculate_price(
                db=db,
                property_id=prop_id,
                category_id=cat_id,
                check_in=data.check_in_date,
                stay_days=data.stay_days,
                client_type_id=client_type_use,
                room_id=room_id
            )

            final_price = price_data.get("final_price", data.price)
            breakdown = json.dumps(price_data.get("breakdown", {}))

            new_res = Reservation(
                id=res_id,
                created_at=datetime.now(),
                check_in_date=data.check_in_date,
                stay_days=data.stay_days,
                guest_name=data.guest_name,
                room_id=room_id,
                room_type=data.room_type, # Keeps text description for legacy compatibility

                # Pricing
                price=final_price,
                final_price=final_price,
                original_price=price_data.get("breakdown", {}).get("base_total", 0),
                discount_amount=0, # Calculated in breakdown, could extract if needed
                price_breakdown=breakdown,

                # Context
                property_id=prop_id,
                category_id=cat_id,
                client_type_id=client_type_use,
                contract_id=data.contract_id,

                arrival_time=data.arrival_time.time() if data.arrival_time else None,
                reserved_by=data.reserved_by,
                contact_phone=data.contact_phone,
                received_by=data.received_by,
                status="Confirmada",

                # Parking & Source
                parking_needed=data.parking_needed,
                vehicle_model=data.vehicle_model,
                vehicle_plate=data.vehicle_plate,
                source=data.source,
                external_id=data.external_id
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
        Returns a matrix {room_display_code: {date_str: guest_name}} for the week.
        Keys use internal_code (e.g. "DF-01") so the UI can match them directly.
        """
        end_date = start_date + timedelta(days=7)

        # Build room_id -> internal_code lookup
        rooms = db.query(Room).filter(Room.active == 1).all()
        code_map = {r.id: r.internal_code or r.id for r in rooms}

        # Fetch active reservations overlapping this week
        reservations = db.query(Reservation).filter(
            Reservation.status == "Confirmada",
            Reservation.check_in_date <= end_date,
        ).all()

        matrix = {}

        dates = [start_date + timedelta(days=i) for i in range(7)]

        for res in reservations:
            # Calculate actual end date
            res_end = res.check_in_date + timedelta(days=res.stay_days - 1)

            # Check overlap
            if res_end < start_date or res.check_in_date > end_date:
                continue

            display_code = code_map.get(res.room_id, res.room_id)
            if display_code not in matrix:
                matrix[display_code] = {}

            for d in dates:
                if res.check_in_date <= d <= res_end:
                    matrix[display_code][d.strftime("%Y-%m-%d")] = res.guest_name

        return matrix

    @staticmethod
    @with_db
    def get_daily_status(db: Session, specific_date: date) -> List[Dict]:
        """
        Returns status of all rooms for a specific day.
        """
        # Get all active rooms with their categories
        rooms = db.query(Room).filter(Room.active == 1).all()

        # Build category lookup for room type names
        categories = db.query(RoomCategory).all()
        cat_map = {c.id: c.name for c in categories}

        room_map = {}
        for r in rooms:
            # Get type from category or use internal_code
            room_type = cat_map.get(r.category_id, r.internal_code or "Sin Categoría")
            room_map[r.id] = {
                "status": "Libre", "huesped": "-", "type": room_type, "res_id": None,
                "internal_code": r.internal_code or r.id
            }

        # Get reservations active on that day
        # PERF-002 FIX: Add lower bound (max realistic stay = 365 days)
        max_stay_days = 365
        earliest_checkin = specific_date - timedelta(days=max_stay_days)
        reservations = db.query(Reservation).filter(
             Reservation.status == "Confirmada",
             Reservation.check_in_date <= specific_date,
             Reservation.check_in_date >= earliest_checkin  # Lower bound
        ).all()

        for res in reservations:
            res_end = res.check_in_date + timedelta(days=res.stay_days - 1)
            if res.check_in_date <= specific_date <= res_end:
                if res.room_id in room_map:
                    room_map[res.room_id]["status"] = "OCUPADA"
                    room_map[res.room_id]["huesped"] = res.guest_name
                    room_map[res.room_id]["res_id"] = res.id

        # Sort by room ID
        result = []
        for rid, info in room_map.items():
            info["room_id"] = rid
            result.append(info)

        return sorted(result, key=lambda x: x["room_id"])

    @staticmethod
    @with_db
    def get_range_status(db: Session, check_in: date, check_out: date) -> List[Dict]:
        """
        Returns status of all rooms considering the full date range.
        A room is marked OCUPADA if ANY confirmed reservation overlaps [check_in, check_out).
        """
        rooms = db.query(Room).filter(Room.active == 1).all()
        categories = db.query(RoomCategory).all()
        cat_map = {c.id: c.name for c in categories}

        room_map = {}
        for r in rooms:
            room_type = cat_map.get(r.category_id, r.internal_code or "Sin Categoría")
            room_map[r.id] = {"status": "Libre", "huesped": "-", "type": room_type, "res_id": None}

        # Find reservations that overlap with [check_in, check_out)
        # Overlap: res_start < check_out AND res_end >= check_in
        max_stay_days = 365
        earliest_checkin = check_in - timedelta(days=max_stay_days)
        reservations = db.query(Reservation).filter(
            Reservation.status == "Confirmada",
            Reservation.check_in_date >= earliest_checkin,
            Reservation.check_in_date < check_out,
        ).all()

        for res in reservations:
            res_end = res.check_in_date + timedelta(days=res.stay_days - 1)
            if res.check_in_date < check_out and res_end >= check_in:
                if res.room_id in room_map:
                    room_map[res.room_id]["status"] = "OCUPADA"
                    room_map[res.room_id]["huesped"] = res.guest_name
                    room_map[res.room_id]["res_id"] = res.id

        result = []
        for rid, info in room_map.items():
            info["room_id"] = rid
            result.append(info)

        return sorted(result, key=lambda x: x["room_id"])

    @staticmethod
    @with_db
    def get_all_reservations(db: Session) -> List[ReservationDTO]:
        res = db.query(Reservation).order_by(Reservation.created_at.desc()).all()

        # Build room lookup for internal codes
        room_ids = list({r.room_id for r in res})
        rooms_list = db.query(Room).filter(Room.id.in_(room_ids)).all() if room_ids else []
        room_code_map = {r.id: r.internal_code or r.id for r in rooms_list}

        return [
            ReservationDTO(
                id=r.id,
                room_id=r.room_id,
                room_internal_code=room_code_map.get(r.room_id, r.room_id),
                guest_name=r.guest_name,
                status=r.status,
                check_in=r.check_in_date,
                check_out=r.check_in_date + timedelta(days=r.stay_days),
                price=r.price or 0.0
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
    def search_reservations(db: Session, query: str) -> List[Dict]:
        """
        Search reservations by guest name, ID, or document number.
        V2-V3 FIX: Moved from ai_tools.py to service layer.
        """
        results = []
        query_clean = query.strip()

        # Check if query is numeric (could be reservation ID or document)
        is_numeric = query_clean.replace("-", "").replace(".", "").isdigit()

        if is_numeric:
            # Search by reservation ID
            padded_id = query_clean.zfill(7)  # "1255" -> "0001255"

            res_by_id = db.query(Reservation).filter(
                or_(
                    Reservation.id == query_clean,
                    Reservation.id == padded_id,
                    Reservation.id.like(f"%{query_clean}")
                ),
                Reservation.status.in_(["Confirmada", "CheckIn"])
            ).all()
            results.extend(res_by_id)

            # Also search by document in CheckIn records
            checkin_matches = db.query(CheckIn).filter(
                CheckIn.document_number.ilike(f"%{query_clean}%")
            ).limit(3).all()

            for ci in checkin_matches:
                res_by_name = db.query(Reservation).filter(
                    Reservation.guest_name.ilike(f"%{ci.last_name}%"),
                    Reservation.status.in_(["Confirmada", "CheckIn"])
                ).all()
                for r in res_by_name:
                    if r not in results:
                        results.append(r)

        # Search by name
        if not results or not is_numeric:
            words = [w.strip() for w in query_clean.replace(",", " ").split() if w.strip()]

            if words:
                conditions = []
                for word in words:
                    conditions.append(Reservation.guest_name.ilike(f"%{word}%"))

                res_by_name = db.query(Reservation).filter(
                    or_(*conditions),
                    Reservation.status.in_(["Confirmada", "CheckIn"])
                ).order_by(Reservation.check_in_date).limit(10).all()

                for r in res_by_name:
                    if r not in results:
                        results.append(r)

        # Sort by check-in date and convert to dict
        results = sorted(results, key=lambda x: x.check_in_date if x.check_in_date else date.max)[:5]

        return [{
            "id": r.id,
            "guest_name": r.guest_name,
            "room_id": r.room_id,
            "check_in_date": r.check_in_date,
            "stay_days": r.stay_days,
            "status": r.status,
            "price": r.price
        } for r in results]

    @staticmethod
    @with_db
    def get_reservations_in_range(db: Session, start_date: date, end_date: date, room_number: str = None) -> List[Dict]:
        """
        Get reservations that overlap with a date range.
        V2-V3 FIX: Moved from ai_tools.py to service layer.
        """
        query = db.query(Reservation).filter(
            Reservation.status.in_(["Confirmada", "CheckIn", "CheckOut"]),
            Reservation.check_in_date.isnot(None)
        )

        if room_number:
            query = query.filter(Reservation.room_id == room_number)

        all_reservations = query.order_by(Reservation.check_in_date).all()

        results = []
        for r in all_reservations:
            check_in = r.check_in_date
            check_out = check_in + timedelta(days=r.stay_days)

            # Check if reservation overlaps with the range
            if check_in <= end_date and check_out >= start_date:
                results.append({
                    "id": r.id,
                    "guest_name": r.guest_name,
                    "room_id": r.room_id,
                    "check_in_date": check_in,
                    "check_out_date": check_out,
                    "stay_days": r.stay_days,
                    "status": r.status,
                    "price": r.price
                })

        return results

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

        db.commit()
        return True

    @staticmethod
    @with_db
    def get_monthly_events(db: Session, year: int, month: int) -> List[CalendarEventDTO]:
        """
        Obtiene eventos de calendario para un mes específico.
        Compatible con FullCalendar y otras librerías JS.
        """
        from calendar import monthrange

        # Calcular rango del mes
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        # Buscar reservas que toquen este mes
        reservations = db.query(Reservation).filter(
            Reservation.status.in_(["Confirmada", "CheckIn"]),
            Reservation.check_in_date <= last_day
        ).all()

        events = []
        for res in reservations:
            # Calcular fecha de salida
            check_out = res.check_in_date + timedelta(days=res.stay_days)

            # Verificar que realmente toque el mes
            if check_out < first_day:
                continue

            # Determinar color según estado
            if res.status == "CheckIn":
                color = "#4CAF50"  # Verde - ya hizo check-in
            else:
                color = "#2196F3"  # Azul - confirmada pero no llegó

            # Crear evento
            event = CalendarEventDTO(
                title=res.guest_name or "Sin nombre",
                start=res.check_in_date.isoformat(),
                end=check_out.isoformat(),
                resourceId=res.room_id or "",
                color=color,
                extendedProps={
                    "reservation_id": res.id,
                    "status": res.status,
                    "room_type": res.room_type,
                    "phone": res.contact_phone
                }
            )
            events.append(event)

        logger.info(f"get_monthly_events: {len(events)} eventos para {year}-{month:02d}")
        return events

    @staticmethod
    @with_db
    def get_occupancy_map(db: Session, year: int, month: int) -> Dict[str, Dict]:
        """
        Obtiene mapa de ocupación para calendario nativo.

        Returns:
            Dict con formato:
            {
                "2024-12-20": {"count": 3, "status": "medium", "ids": ["001", "002", "003"]},
                ...
            }
        """
        from calendar import monthrange

        # Calcular rango del mes
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        # Inicializar mapa vacío para todos los días del mes
        occupancy_map = {}
        current = first_day
        while current <= last_day:
            occupancy_map[current.strftime("%Y-%m-%d")] = {
                "count": 0,
                "status": "free",
                "ids": [],
                "guests": []
            }
            current += timedelta(days=1)

        # PERF-003: Add lower bound filter so we don't scan all historical reservations
        # A reservation can only overlap this month if check_out > first_day,
        # i.e. check_in_date + stay_days > first_day.
        # Since SQLite can't do date arithmetic in filter, use a safe lower bound:
        # check_in_date must be >= first_day - max_stay_days
        max_stay_days = 365
        earliest_checkin = first_day - timedelta(days=max_stay_days)

        reservations = db.query(Reservation).filter(
            Reservation.status.in_(["Confirmada", "CheckIn"]),
            Reservation.check_in_date <= last_day,
            Reservation.check_in_date >= earliest_checkin
        ).all()

        for res in reservations:
            # Calcular fecha de salida
            check_out = res.check_in_date + timedelta(days=res.stay_days)

            # Verificar que la reserva toque el mes
            if check_out < first_day:
                continue

            # Marcar cada día ocupado
            day = max(res.check_in_date, first_day)
            end = min(check_out, last_day + timedelta(days=1))

            while day < end:
                day_key = day.strftime("%Y-%m-%d")
                if day_key in occupancy_map:
                    occupancy_map[day_key]["count"] += 1
                    occupancy_map[day_key]["ids"].append(res.id)
                    occupancy_map[day_key]["guests"].append(res.guest_name)
                day += timedelta(days=1)

        # Calcular status basado en count
        for day_key, data in occupancy_map.items():
            count = data["count"]
            if count == 0:
                data["status"] = "free"
            elif 1 <= count <= 5:
                data["status"] = "medium"
            else:
                data["status"] = "high"

        logger.info(f"get_occupancy_map: {year}-{month:02d} con {sum(1 for d in occupancy_map.values() if d['count'] > 0)} días ocupados")
        return occupancy_map

    @staticmethod
    @with_db
    def get_today_summary(db: Session) -> TodaySummaryDTO:
        """
        Obtiene resumen rápido de ocupación para vista móvil.
        Optimizado con consultas SQL eficientes.
        """
        today = date.today()

        # 1. Total de habitaciones
        total_rooms = db.query(func.count(Room.id)).scalar() or 0

        # 2. Llegadas hoy (reservas que inician hoy)
        llegadas = db.query(func.count(Reservation.id)).filter(
            Reservation.check_in_date == today,
            Reservation.status.in_(["Confirmada", "CheckIn"])
        ).scalar() or 0

        # 3. Salidas hoy (reservas que terminan hoy)
        # PERF-002 FIX: Add date bounds to avoid scanning all historical data
        max_stay_days = 365
        earliest_checkin = today - timedelta(days=max_stay_days)
        salidas = 0
        reservas_activas = db.query(Reservation).filter(
            Reservation.status.in_(["Confirmada", "CheckIn"]),
            Reservation.check_in_date >= earliest_checkin  # Lower bound
        ).all()

        for res in reservas_activas:
            check_out = res.check_in_date + timedelta(days=res.stay_days)
            if check_out == today:
                salidas += 1

        # 4. Habitaciones ocupadas hoy
        ocupadas = 0
        for res in reservas_activas:
            check_out = res.check_in_date + timedelta(days=res.stay_days)
            if res.check_in_date <= today < check_out:
                ocupadas += 1

        # 5. Habitaciones libres
        libres = total_rooms - ocupadas

        # 6. Porcentaje de ocupación
        porcentaje = (ocupadas / total_rooms * 100) if total_rooms > 0 else 0.0

        summary = TodaySummaryDTO(
            llegadas_hoy=llegadas,
            salidas_hoy=salidas,
            ocupadas=ocupadas,
            libres=libres,
            total_habitaciones=total_rooms,
            porcentaje_ocupacion=round(porcentaje, 1)
        )

        logger.info(f"get_today_summary: {ocupadas}/{total_rooms} ocupadas ({porcentaje:.1f}%)")
        return summary
