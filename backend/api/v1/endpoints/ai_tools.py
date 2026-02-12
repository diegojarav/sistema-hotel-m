"""
Hotel PMS - AI Tools for Gemini Function Calling
====================================================

Plain Python functions with Google-style docstrings.
Gemini reads these docstrings to understand tool usage.

Architecture: Hybrid Cloud-Local
- Gemini selects which tool to call
- Backend executes Python function against local SQLite
- Result returned to Gemini for natural language response
"""

from datetime import date, datetime, timedelta
from typing import Optional

# Import services from root (Hybrid Monolith)
from services import ReservationService


# ==========================================
# TOOL 1: Check Availability
# ==========================================

def check_availability(check_date: str, stay_days: int = 1) -> str:
    """
    Check room availability for a specific date and stay duration.
    Use this tool when the user asks about available rooms, wants to make
    a new reservation, or asks if there are rooms free on a specific date.
    
    Args:
        check_date: Date to check in YYYY-MM-DD format (e.g., "2026-01-25").
        stay_days: Number of nights to stay. Defaults to 1.
    
    Returns:
        A string describing available rooms or if fully booked.
    
    Examples:
        - "¿Hay habitaciones para el 25 de enero?" → check_availability("2026-01-25", 1)
        - "¿Tienen disponibilidad para 3 noches desde el 10 de febrero?" → check_availability("2026-02-10", 3)
    """
    try:
        target_date = datetime.strptime(check_date, "%Y-%m-%d").date()
    except ValueError:
        return f"Fecha inválida: {check_date}. Usa formato YYYY-MM-DD."
    
    # Reject past dates
    today = date.today()
    if target_date < today:
        return f"La fecha {check_date} ya pasó. Solo puedo verificar disponibilidad para fechas futuras (desde {today.strftime('%d/%m/%Y')})."
    
    # Get room status for each day of the stay
    all_free_rooms = None
    
    for day_offset in range(stay_days):
        current_day = target_date + timedelta(days=day_offset)
        daily_status = ReservationService.get_daily_status(current_day)
        free_rooms_today = {s.get("internal_code", s["room_id"]) for s in daily_status if s["status"] == "Libre"}

        if all_free_rooms is None:
            all_free_rooms = free_rooms_today
        else:
            all_free_rooms = all_free_rooms.intersection(free_rooms_today)

    if not all_free_rooms:
        return f"No hay habitaciones disponibles del {check_date} por {stay_days} noche(s). Hotel completo."

    room_list = sorted(all_free_rooms)
    return (
        f"Disponibilidad para {check_date} ({stay_days} noche(s)): "
        f"{len(room_list)} habitaciones libres: {', '.join(room_list)}. "
        f"Total de 14 habitaciones en el hotel."
    )


# ==========================================
# TOOL 2: Get Hotel Rates
# ==========================================

def get_hotel_rates(room_type: Optional[str] = None) -> str:
    """
    Get current hotel room rates and prices.
    Use this tool when the user asks about prices, costs, or rates.
    
    Args:
        room_type: Optional filter for room type ("Standard", "Matrimonial", "Triple").
                   If not provided, returns all rates.
    
    Returns:
        String with room prices in Guaraníes (Gs).
    
    Examples:
        - "¿Cuánto cuesta una habitación?" → get_hotel_rates()
        - "¿Precio de habitación matrimonial?" → get_hotel_rates("Matrimonial")
    """
    from services import RoomService
    
    # Fetch real categories from database
    categories = RoomService.get_all_categories()
    
    if not categories:
        return "No hay categorías de habitaciones configuradas en el sistema."

    if room_type:
        # Filter by name (fuzzy match)
        matching = [c for c in categories if room_type.lower() in c["name"].lower()]
        
        if matching:
            lines = []
            for c in matching:
                price = f"{c['base_price']:,.0f} Gs"
                lines.append(f"{c['name']} (Capacidad: {c['max_capacity']}): {price}/noche")
            return f"Tarifas encontradas para '{room_type}':\n" + "\n".join(lines)
        
        # If no match, list available types
        avail_names = ", ".join([c["name"] for c in categories])
        return f"No encontré tarifas para '{room_type}'. Tipos disponibles: {avail_names}"
    
    # List all rates
    lines = []
    for c in categories:
        price = f"{c['base_price']:,.0f} Gs"
        lines.append(f"  - {c['name']} (x{c['max_capacity']}): {price}/noche")
    
    return f"Tarifas Base del Hotel (pueden variar según fecha/temporada):\n" + "\n".join(lines)


# ==========================================
# TOOL 3: Get Today Summary
# ==========================================

def get_today_summary() -> str:
    """
    Get today's hotel occupancy summary including arrivals, departures, and occupancy.
    Use this tool when the user asks for a summary, status, or overview of the hotel today.
    
    Returns:
        String with today's arrivals, departures, occupied rooms, and occupancy percentage.
    
    Examples:
        - "Dame un resumen del hotel" → get_today_summary()
        - "¿Cuál es el estado del hotel?" → get_today_summary()
        - "¿Cuántas habitaciones están ocupadas?" → get_today_summary()
    """
    summary = ReservationService.get_today_summary()
    today_str = date.today().strftime("%d/%m/%Y")
    
    return (
        f"Resumen de hoy ({today_str}):\n"
        f"  - Habitaciones ocupadas: {summary.ocupadas} de 14\n"
        f"  - Habitaciones libres: {summary.libres}\n"
        f"  - Llegadas hoy: {summary.llegadas_hoy}\n"
        f"  - Salidas hoy: {summary.salidas_hoy}\n"
        f"  - Ocupación: {summary.porcentaje_ocupacion}%"
    )


# ==========================================
# TOOL 4: Search Guest (Check-in Records)
# ==========================================

def search_guest(query: str) -> str:
    """
    Search for a guest in the check-in records (fichas) by name or document number.
    Use this tool to find guests who have ALREADY checked in (historical records).
    For FUTURE arrivals/reservations, use search_reservation instead.
    
    Args:
        query: Guest name or document number to search for.
    
    Returns:
        String with matching guest check-in records or "not found".
    
    Examples:
        - "Buscar ficha de Pedro López" → search_guest("Pedro López")
        - "Buscar huésped con documento 1234567" → search_guest("1234567")
    """
    from services import GuestService
    
    results = GuestService.search_checkins(query)
    
    if not results:
        return f"No encontré huéspedes con '{query}' en los registros de check-in."
    
    lines = []
    for r in results[:5]:
        lines.append(
            f"  - {r['last_name']}, {r['first_name']} | "
            f"Doc: {r['document_number']} | Hab: {r['room_code']}"
        )
    
    result_str = "\n".join(lines)
    total = len(results)
    shown = min(5, total)
    
    return f"Encontré {total} registro(s) de check-in para '{query}' (mostrando {shown}):\n{result_str}"


# ==========================================
# TOOL 5: Search Reservation (Omni-Search)
# ==========================================

def search_reservation(query: str) -> str:
    """
    Search for a specific reservation by Guest Name, Reservation ID, or Document Number.
    Use this tool when someone asks about arrival dates, existing bookings,
    confirmation of reservations, or when they ask "when does X arrive?".

    Args:
        query: Search term - can be guest name (partial), reservation ID, or document number.

    Returns:
        String with matching reservations including ID, arrival/departure dates, room, and status.

    Examples:
        - "¿Cuándo llega Juan Pérez?" → search_reservation("Juan Pérez")
        - "¿Tiene reserva María García?" → search_reservation("María García")
        - "Buscar reserva 1255" → search_reservation("1255")
        - "Buscar reserva con documento 4567890" → search_reservation("4567890")
    """
    # V2-V3 FIX: Use service layer instead of direct database access
    results = ReservationService.search_reservations(query)

    if not results:
        return f"No encontré reservas para '{query}'."

    lines = []
    for r in results:
        check_in = r["check_in_date"]
        check_out = check_in + timedelta(days=r["stay_days"]) if check_in else None
        check_in_str = check_in.strftime('%d/%m/%Y') if check_in else "N/A"
        check_out_str = check_out.strftime('%d/%m/%Y') if check_out else "N/A"

        lines.append(
            f"  - ID: {r['id']} | {r['guest_name']} | Hab: {r['room_code']} | "
            f"Llegada: {check_in_str} | Salida: {check_out_str} | Estado: {r['status']}"
        )

    return f"Encontré {len(results)} reserva(s) para '{query}':\n" + "\n".join(lines)


# ==========================================
# TOOL 6: Get Reservations Report (Date Range)
# ==========================================

def get_reservations_report(start_date: str, end_date: str, room_number: Optional[str] = None) -> str:
    """
    Get a detailed list of reservations within a date range. Optional: filter by room number.
    Use this tool for queries like "reservations this week", "who is in room 31 next month",
    "list all reservations for February", or "show me the bookings for next week".

    Args:
        start_date: Start of date range in YYYY-MM-DD format (e.g., "2026-01-20").
        end_date: End of date range in YYYY-MM-DD format (e.g., "2026-01-27").
        room_number: Optional room number to filter (e.g., "31", "32"). If not provided, shows all rooms.

    Returns:
        Formatted report string with all reservations in the period, or "no reservations found".

    Examples:
        - "¿Qué reservas hay esta semana?" → get_reservations_report("2026-01-20", "2026-01-27")
        - "Reservas de febrero" → get_reservations_report("2026-02-01", "2026-02-28")
        - "¿Quién estuvo en la habitación 31 el mes pasado?" → get_reservations_report("2025-12-01", "2025-12-31", "31")
        - "Lista de reservas para la próxima semana" → get_reservations_report("2026-01-27", "2026-02-03")
    """
    # Parse dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return f"Fecha de inicio inválida: {start_date}. Usa formato YYYY-MM-DD."

    try:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return f"Fecha de fin inválida: {end_date}. Usa formato YYYY-MM-DD."

    if end < start:
        return f"Error: La fecha de fin ({end_date}) debe ser posterior a la de inicio ({start_date})."

    # V2-V3 FIX: Use service layer instead of direct database access
    results = ReservationService.get_reservations_in_range(start, end, room_number)

    # Build header
    room_filter_text = f"Hab: {room_number}" if room_number else "Todas las habitaciones"
    header = f"Reporte del {start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')} ({room_filter_text})"

    if not results:
        return f"{header}\n\nNo se encontraron reservas en ese período."

    # Build report
    lines = [header, f"Total: {len(results)} reserva(s)\n"]

    for i, r in enumerate(results, 1):
        check_in_str = r["check_in_date"].strftime('%d/%m/%Y')
        check_out_str = r["check_out_date"].strftime('%d/%m/%Y')
        nights = r["stay_days"]
        price_str = f"{r['price']:,.0f} Gs" if r.get("price") else "N/A"

        lines.append(
            f"{i}. **{r['guest_name'] or 'Sin nombre'}**\n"
            f"   - Hab: {r['room_code']} | {check_in_str} -> {check_out_str} ({nights} noche{'s' if nights > 1 else ''})\n"
            f"   - Estado: {r['status']} | Total: {price_str}"
        )

    return "\n".join(lines)


# ==========================================
# TOOLS LIST (for Gemini automatic function calling)
# ==========================================

TOOLS_LIST = [
    check_availability,
    get_hotel_rates,
    get_today_summary,
    search_guest,
    search_reservation,
    get_reservations_report,
]
