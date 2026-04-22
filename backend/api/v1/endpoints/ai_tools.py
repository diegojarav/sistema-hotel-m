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
from services import ReservationService, CajaService, TransaccionService, ProductService, ConsumoService, KitchenReportService, SettingsService, EmailService


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
# TOOL 7: Calculate Price
# ==========================================

def calculate_price(category_name: str, check_in_date: str, stay_days: int, client_type: str = "Particular") -> str:
    """
    Calculate the total price for a hotel stay based on room category, dates, and client type.
    Use this tool when the user asks how much a stay costs, wants a price quote,
    or asks about pricing for specific dates or room types.

    Args:
        category_name: Room category name (e.g., "Estandar", "Matrimonial", "Triple", "Familiar").
        check_in_date: Check-in date in YYYY-MM-DD format (e.g., "2026-03-15").
        stay_days: Number of nights to stay. Must be >= 1.
        client_type: Client type for pricing (e.g., "Particular", "Corporativo", "Agencia"). Defaults to "Particular".

    Returns:
        String with the calculated price breakdown including base price, modifiers, and total.

    Examples:
        - "¿Cuánto cuesta 3 noches en Matrimonial?" → calculate_price("Matrimonial", "2026-03-15", 3)
        - "Precio para una Familiar 5 noches tipo Corporativo" → calculate_price("Familiar", "2026-03-20", 5, "Corporativo")
        - "¿Cuánto sale una noche?" → calculate_price("Estandar", "2026-03-15", 1)
    """
    from services import PricingService, RoomService

    # Validate date
    try:
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
    except ValueError:
        return f"Fecha inválida: {check_in_date}. Usa formato YYYY-MM-DD."

    if stay_days < 1:
        return "La cantidad de noches debe ser al menos 1."

    # Resolve category_id from name
    categories = RoomService.get_all_categories()
    matching_cat = [c for c in categories if category_name.lower() in c["name"].lower()]
    if not matching_cat:
        avail = ", ".join([c["name"] for c in categories])
        return f"No encontré la categoría '{category_name}'. Categorías disponibles: {avail}"
    category = matching_cat[0]

    # Resolve client_type_id from name
    client_types = PricingService.get_client_types()
    matching_ct = [ct for ct in client_types if client_type.lower() in ct["name"].lower()]
    if not matching_ct:
        avail = ", ".join([ct["name"] for ct in client_types])
        return f"No encontré el tipo de cliente '{client_type}'. Tipos disponibles: {avail}"
    ct = matching_ct[0]

    try:
        result = PricingService.calculate_price(
            property_id="los-monges",
            category_id=category["id"],
            check_in=check_in,
            stay_days=stay_days,
            client_type_id=ct["id"],
        )
    except Exception as e:
        return f"Error al calcular precio: {str(e)}"

    # Format response
    bd = result.get("breakdown", {})
    base_unit = bd.get("base_unit_price", 0)
    final = result.get("final_price", 0)
    modifiers = bd.get("modifiers", [])

    lines = [
        f"Cotización para {category['name']} - {stay_days} noche(s) desde {check_in.strftime('%d/%m/%Y')}:",
        f"  - Tarifa base: {base_unit:,.0f} Gs/noche",
        f"  - Subtotal ({stay_days} noches): {bd.get('base_total', 0):,.0f} Gs",
    ]

    for mod in modifiers:
        sign = "+" if mod["percent"] > 0 else ""
        lines.append(f"  - {mod['name']}: {sign}{mod['percent']:.0f}% ({mod['amount']:,.0f} Gs)")

    lines.append(f"  - **TOTAL: {final:,.0f} Gs**")
    lines.append(f"  - Tipo de cliente: {ct['name']}")

    return "\n".join(lines)


# ==========================================
# TOOL 8: Get Occupancy for Month
# ==========================================

def get_occupancy_for_month(year: int, month: int) -> str:
    """
    Get the monthly occupancy overview for a specific month.
    Use this tool when the user asks about how busy the hotel is/was in a month,
    occupancy trends, or monthly statistics.

    Args:
        year: Year number (e.g., 2026).
        month: Month number from 1 to 12 (e.g., 3 for March).

    Returns:
        String with average occupancy, busiest/quietest days, and daily breakdown summary.

    Examples:
        - "¿Cómo está la ocupación en marzo?" → get_occupancy_for_month(2026, 3)
        - "¿Cómo estuvo febrero?" → get_occupancy_for_month(2026, 2)
        - "Ocupación del mes pasado" → get_occupancy_for_month(2026, 2)
    """
    if month < 1 or month > 12:
        return f"Mes inválido: {month}. Debe ser entre 1 y 12."

    MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    try:
        occ_map = ReservationService.get_occupancy_map(year, month)
    except Exception as e:
        return f"Error al obtener datos de ocupación: {str(e)}"

    if not occ_map:
        return f"No hay datos de ocupación para {MESES[month-1]} {year}."

    total_rooms = 15  # Hotel capacity
    days_data = []
    for day_str, info in sorted(occ_map.items()):
        count = info.get("count", 0)
        pct = round(count / total_rooms * 100, 1)
        days_data.append({"date": day_str, "count": count, "pct": pct})

    if not days_data:
        return f"No hay datos de ocupación para {MESES[month-1]} {year}."

    avg_occ = round(sum(d["pct"] for d in days_data) / len(days_data), 1)
    busiest = max(days_data, key=lambda d: d["count"])
    quietest = min(days_data, key=lambda d: d["count"])
    high_days = sum(1 for d in days_data if d["pct"] >= 80)
    low_days = sum(1 for d in days_data if d["pct"] == 0)

    lines = [
        f"Ocupación de {MESES[month-1]} {year}:",
        f"  - Promedio: {avg_occ}%",
        f"  - Día más ocupado: {busiest['date']} ({busiest['count']}/{total_rooms} hab, {busiest['pct']}%)",
        f"  - Día más libre: {quietest['date']} ({quietest['count']}/{total_rooms} hab, {quietest['pct']}%)",
        f"  - Días con alta ocupación (≥80%): {high_days}",
        f"  - Días vacíos (0%): {low_days}",
        f"  - Total días: {len(days_data)}",
    ]

    return "\n".join(lines)


# ==========================================
# TOOL 9: Get Room Performance Report
# ==========================================

def get_room_performance(start_date: str, end_date: str, room_code: Optional[str] = None) -> str:
    """
    Get a performance report for one room or all rooms in a date range.
    Shows nights occupied, revenue, occupancy percentage, average nightly rate, and reservation count.
    Use this tool when the user asks about room performance, revenue per room, or room statistics.

    Args:
        start_date: Start of date range in YYYY-MM-DD format (e.g., "2026-03-01").
        end_date: End of date range in YYYY-MM-DD format (e.g., "2026-03-31").
        room_code: Optional room code to filter (e.g., "DE-01", "DM-01"). If not provided, shows all rooms.

    Returns:
        String with per-room performance metrics.

    Examples:
        - "¿Cómo rindió la habitación DE-01 este mes?" → get_room_performance("2026-03-01", "2026-03-31", "DE-01")
        - "Reporte de rendimiento de habitaciones del mes" → get_room_performance("2026-03-01", "2026-03-31")
        - "¿Cuál habitación genera más ingresos?" → get_room_performance("2026-01-01", "2026-03-31")
    """
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

    try:
        report = ReservationService.get_room_report(start, end, room_code)
    except Exception as e:
        return f"Error al obtener reporte: {str(e)}"

    if report.get("error"):
        return f"Error: {report['error']}"

    rooms = report.get("rooms", [])
    if not rooms:
        filter_text = f" para habitación {room_code}" if room_code else ""
        return f"No hay datos de rendimiento{filter_text} en el período {start_date} a {end_date}."

    period = report.get("period", {})
    header = f"Rendimiento de Habitaciones ({period.get('start', start_date)} al {period.get('end', end_date)}, {period.get('days', 0)} días)"

    lines = [header, ""]
    for rm in rooms:
        room_info = rm["room"]
        s = rm["summary"]
        lines.append(
            f"  {room_info['code']} ({room_info['category']}):\n"
            f"    Noches: {s['total_nights']} | Ocupación: {s['occupancy_pct']}% | "
            f"Ingresos: {s['total_revenue']:,.0f} Gs | "
            f"Tarifa prom: {s['avg_nightly_rate']:,.0f} Gs | "
            f"Reservas: {s['reservation_count']}"
        )

    # Add totals if showing all rooms
    if len(rooms) > 1:
        total_nights = sum(r["summary"]["total_nights"] for r in rooms)
        total_revenue = sum(r["summary"]["total_revenue"] for r in rooms)
        total_reservations = sum(r["summary"]["reservation_count"] for r in rooms)
        avg_occ = round(sum(r["summary"]["occupancy_pct"] for r in rooms) / len(rooms), 1)
        lines.append(f"\n  TOTALES: {total_nights} noches | {avg_occ}% ocupación promedio | {total_revenue:,.0f} Gs ingresos | {total_reservations} reservas")

    return "\n".join(lines)


# ==========================================
# TOOL 10: Get Booking Source Distribution
# ==========================================

def get_booking_sources(start_date: str, end_date: str) -> str:
    """
    Get the distribution of reservation sources (where bookings come from) in a date range.
    Use this tool when the user asks about booking channels, where reservations come from,
    or wants to compare sources like Booking.com vs direct reservations.

    Args:
        start_date: Start of date range in YYYY-MM-DD format (e.g., "2026-03-01").
        end_date: End of date range in YYYY-MM-DD format (e.g., "2026-03-31").

    Returns:
        String with reservation count and revenue per booking source.

    Examples:
        - "¿De dónde vienen las reservas este mes?" → get_booking_sources("2026-03-01", "2026-03-31")
        - "¿Cuántas reservas de Booking.com tenemos?" → get_booking_sources("2026-01-01", "2026-03-31")
        - "Distribución de canales de reserva" → get_booking_sources("2026-01-01", "2026-12-31")
    """
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

    try:
        sources = ReservationService.get_source_distribution(start, end)
    except Exception as e:
        return f"Error al obtener distribución de fuentes: {str(e)}"

    if not sources:
        return f"No hay reservas en el período {start_date} a {end_date}."

    total_count = sum(s["count"] for s in sources)
    total_revenue = sum(s["revenue"] for s in sources)

    lines = [
        f"Distribución de fuentes de reserva ({start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}):",
        f"Total: {total_count} reservas | {total_revenue:,.0f} Gs\n",
    ]

    for s in sources:
        pct = round(s["count"] / total_count * 100, 1) if total_count > 0 else 0
        lines.append(f"  - {s['source']}: {s['count']} reservas ({pct}%) | {s['revenue']:,.0f} Gs")

    return "\n".join(lines)


# ==========================================
# TOOL 11: Get Parking Usage
# ==========================================

def get_parking_status(start_date: str, end_date: str) -> str:
    """
    Get parking lot usage for a date range showing daily utilization.
    Use this tool when the user asks about parking availability, parking usage,
    or how full the parking lot is.

    Args:
        start_date: Start of date range in YYYY-MM-DD format (e.g., "2026-03-10").
        end_date: End of date range in YYYY-MM-DD format (e.g., "2026-03-16").

    Returns:
        String with parking usage summary and daily breakdown.

    Examples:
        - "¿Cómo está el estacionamiento?" → get_parking_status with today's date range
        - "Uso del parking esta semana" → get_parking_status("2026-03-10", "2026-03-16")
        - "¿Hay lugar en el estacionamiento mañana?" → get_parking_status with tomorrow's date
    """
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

    try:
        usage = ReservationService.get_parking_usage(start, end)
    except Exception as e:
        return f"Error al obtener uso de estacionamiento: {str(e)}"

    if not usage:
        return f"No hay datos de estacionamiento para el período {start_date} a {end_date}."

    capacity = usage[0].get("capacity", 0) if usage else 0
    avg_pct = round(sum(d["pct"] for d in usage) / len(usage), 1) if usage else 0
    peak = max(usage, key=lambda d: d["used"])
    today_str = date.today().strftime("%Y-%m-%d")
    today_data = next((d for d in usage if d["date"] == today_str), None)

    lines = [
        f"Uso del Estacionamiento ({start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}):",
        f"  - Capacidad total: {capacity} lugares",
        f"  - Uso promedio: {avg_pct}%",
        f"  - Día pico: {peak['date']} ({peak['used']}/{capacity}, {peak['pct']}%)",
    ]

    if today_data:
        free = capacity - today_data["used"]
        lines.append(f"  - HOY: {today_data['used']}/{capacity} ocupados ({today_data['pct']}%) - {free} libres")

    return "\n".join(lines)


# ==========================================
# TOOL 12: Get Revenue Summary
# ==========================================

def get_revenue_summary(period: str = "month", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> str:
    """
    Get total income/revenue for a time period.
    Use this tool when the user asks about money, income, revenue, earnings,
    how much the hotel made, daily/weekly/monthly sales, or financial summaries.

    Args:
        period: One of "today", "week", "month", "year", or "custom".
                - "today": revenue for today only
                - "week": revenue for the current week (Monday to Sunday)
                - "month": revenue for the current month
                - "year": revenue for the current year
                - "custom": uses custom_start and custom_end dates
        custom_start: Start date in YYYY-MM-DD format. Required only when period="custom".
        custom_end: End date in YYYY-MM-DD format. Required only when period="custom".

    Returns:
        String with total revenue, reservation count, and breakdown by status.

    Examples:
        - "¿Cuánto ganamos hoy?" → get_revenue_summary("today")
        - "¿Cuánto hicimos esta semana?" → get_revenue_summary("week")
        - "Ingresos del mes" → get_revenue_summary("month")
        - "¿Cuánto facturamos este año?" → get_revenue_summary("year")
        - "Ingresos de enero a marzo" → get_revenue_summary("custom", "2026-01-01", "2026-03-31")
        - "¿Cuánta plata entró hoy?" → get_revenue_summary("today")
    """
    today = date.today()

    if period == "today":
        start = today
        end = today
        period_label = f"Hoy ({today.strftime('%d/%m/%Y')})"
    elif period == "week":
        start = today - timedelta(days=today.weekday())  # Monday
        end = start + timedelta(days=6)  # Sunday
        period_label = f"Esta semana ({start.strftime('%d/%m')} al {end.strftime('%d/%m/%Y')})"
    elif period == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        period_label = f"{today.strftime('%B %Y')}"
    elif period == "year":
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        period_label = f"Año {today.year}"
    elif period == "custom":
        if not custom_start or not custom_end:
            return "Error: Para período 'custom' se requieren custom_start y custom_end en formato YYYY-MM-DD."
        try:
            start = datetime.strptime(custom_start, "%Y-%m-%d").date()
            end = datetime.strptime(custom_end, "%Y-%m-%d").date()
        except ValueError:
            return "Error: Formato de fecha inválido. Usa YYYY-MM-DD."
        period_label = f"{start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}"
    else:
        return f"Período inválido: '{period}'. Usa: today, week, month, year, o custom."

    # Get all reservations in the period
    results = ReservationService.get_reservations_in_range(start, end)

    if not results:
        return f"Ingresos {period_label}: No hay reservas en este período."

    # Calculate totals
    total_revenue = 0
    confirmed_revenue = 0
    cancelled_count = 0
    confirmed_count = 0

    for r in results:
        price = r.get("price", 0) or 0
        status = (r.get("status", "") or "").lower()
        if status == "cancelada":
            cancelled_count += 1
        else:
            total_revenue += price
            confirmed_count += 1
            if status in ("confirmada", "checkin"):
                confirmed_revenue += price

    # Format output
    def fmt(amount):
        return f"{amount:,.0f} Gs"

    lines = [
        f"💰 Ingresos — {period_label}",
        f"",
        f"Total: {fmt(total_revenue)}",
        f"Reservas activas: {confirmed_count}",
    ]

    if cancelled_count > 0:
        lines.append(f"Canceladas: {cancelled_count} (no incluidas en el total)")

    # Breakdown by source if there are multiple
    sources = {}
    for r in results:
        if (r.get("status", "") or "").lower() == "cancelada":
            continue
        source = r.get("source", "Direct") or "Direct"
        price = r.get("price", 0) or 0
        if source not in sources:
            sources[source] = {"count": 0, "revenue": 0}
        sources[source]["count"] += 1
        sources[source]["revenue"] += price

    if len(sources) > 1:
        lines.append("")
        lines.append("Por canal:")
        for src, data in sorted(sources.items(), key=lambda x: x[1]["revenue"], reverse=True):
            pct = (data["revenue"] / total_revenue * 100) if total_revenue > 0 else 0
            lines.append(f"  • {src}: {data['count']} reservas — {fmt(data['revenue'])} ({pct:.0f}%)")

    # Average per reservation
    if confirmed_count > 0:
        avg = total_revenue / confirmed_count
        lines.append(f"")
        lines.append(f"Promedio por reserva: {fmt(avg)}")

    return "\n".join(lines)


# ==========================================
# TOOL 13: Consultar Caja (Cash Register Status)
# ==========================================

def consultar_caja() -> str:
    """
    Consultar el estado de las sesiones de caja abiertas del hotel.
    Use cuando el usuario pregunte cuanto hay en caja, el balance actual,
    cuanto entro hoy en efectivo, o informacion sobre sesiones de caja en curso.

    Returns:
        String describiendo sesiones abiertas, balance inicial, movimientos de
        efectivo y total esperado en caja. Si no hay sesiones abiertas lo indica.

    Examples:
        - "¿Cuanto hay en caja?" → consultar_caja()
        - "¿Cuanto entro hoy en efectivo?" → consultar_caja()
        - "¿Esta abierta la caja?" → consultar_caja()
        - "Estado de la caja actual" → consultar_caja()
    """
    try:
        open_sessions = CajaService.list_open_sessions()

        if not open_sessions:
            # Fallback: show today's closed sessions summary
            recent = CajaService.list_sessions(limit=100)
            today_start = datetime.combine(date.today(), datetime.min.time())
            closed_today = [
                s for s in recent
                if s.status == "CERRADA" and s.closed_at and s.closed_at >= today_start
            ]

            if not closed_today:
                return "No hay ninguna sesion de caja abierta en este momento, y no se cerro ninguna caja hoy."

            lines = ["No hay sesiones de caja abiertas ahora."]
            lines.append(f"Sesiones cerradas hoy: {len(closed_today)}")
            for s in closed_today:
                summary = CajaService.get_session_summary(s.id) or {}
                uname = summary.get("user_name", "?")
                diff = s.difference if s.difference is not None else 0
                diff_label = "✓ cuadrada" if abs(diff) < 1 else (
                    f"faltante {abs(diff):,.0f} Gs" if diff < 0 else f"sobrante {diff:,.0f} Gs"
                )
                lines.append(
                    f"  • {uname}: abrio {(s.opening_balance or 0):,.0f} Gs → "
                    f"cerro {(s.closing_balance_declared or 0):,.0f} Gs ({diff_label})"
                )
            return "\n".join(lines)

        lines = [f"💰 Caja — {len(open_sessions)} sesion(es) abierta(s)", ""]
        total_efectivo_en_caja = 0.0

        for s in open_sessions:
            summary = CajaService.get_session_summary(s.id) or {}
            uname = summary.get("user_name", "?")
            opening = summary.get("opening_balance", 0) or 0
            total_efectivo = summary.get("total_efectivo", 0) or 0
            num_trans = len([
                t for t in summary.get("transactions", [])
                if t.payment_method == "EFECTIVO" and not t.voided
            ])
            expected = opening + total_efectivo
            total_efectivo_en_caja += expected

            opened_at_str = s.opened_at.strftime("%d/%m %H:%M") if s.opened_at else "?"
            lines.append(f"Sesion #{s.id} — {uname} (abierta {opened_at_str})")
            lines.append(f"  Balance inicial: {opening:,.0f} Gs")
            lines.append(f"  Movimientos efectivo: {num_trans} transaccion(es) = {total_efectivo:,.0f} Gs")
            lines.append(f"  Total esperado en caja: {expected:,.0f} Gs")
            if s.notes:
                lines.append(f"  Notas: {s.notes}")
            lines.append("")

        if len(open_sessions) > 1:
            lines.append(f"TOTAL esperado entre todas las cajas: {total_efectivo_en_caja:,.0f} Gs")

        return "\n".join(lines).rstrip()
    except Exception as e:
        return f"Error al consultar el estado de caja: {e}"


# ==========================================
# TOOL 14: Resumen Ingresos Por Metodo
# ==========================================

def resumen_ingresos_por_metodo(period: str = "month", custom_start: Optional[str] = None, custom_end: Optional[str] = None) -> str:
    """
    Resumen de ingresos agrupado por metodo de pago (efectivo, transferencia, POS).
    Use cuando el usuario pregunte cuanto se cobro por un metodo especifico,
    comparacion entre metodos, o distribucion de pagos.

    Args:
        period: Uno de "today", "week", "month", "year", o "custom".
                - "today": ingresos de hoy
                - "week": semana actual (lunes a domingo)
                - "month": mes actual
                - "year": año actual
                - "custom": usa custom_start y custom_end
        custom_start: Fecha inicio YYYY-MM-DD. Requerido si period="custom".
        custom_end: Fecha fin YYYY-MM-DD. Requerido si period="custom".

    Returns:
        String con totales por metodo (EFECTIVO, TRANSFERENCIA, POS) con conteos
        y porcentajes.

    Examples:
        - "¿Cuanto se cobro esta semana por transferencia?" → resumen_ingresos_por_metodo("week")
        - "Ingresos en efectivo de marzo" → resumen_ingresos_por_metodo("custom", "2026-03-01", "2026-03-31")
        - "¿Como se distribuyeron los pagos hoy?" → resumen_ingresos_por_metodo("today")
        - "Cobros del año por metodo de pago" → resumen_ingresos_por_metodo("year")
    """
    today = date.today()

    if period == "today":
        start = today
        end = today
        period_label = f"Hoy ({today.strftime('%d/%m/%Y')})"
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        period_label = f"Esta semana ({start.strftime('%d/%m')} al {end.strftime('%d/%m/%Y')})"
    elif period == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        period_label = f"{today.strftime('%B %Y')}"
    elif period == "year":
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        period_label = f"Año {today.year}"
    elif period == "custom":
        if not custom_start or not custom_end:
            return "Error: Para período 'custom' se requieren custom_start y custom_end en formato YYYY-MM-DD."
        try:
            start = datetime.strptime(custom_start, "%Y-%m-%d").date()
            end = datetime.strptime(custom_end, "%Y-%m-%d").date()
        except ValueError:
            return "Error: Formato de fecha inválido. Usa YYYY-MM-DD."
        period_label = f"{start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}"
    else:
        return f"Período inválido: '{period}'. Usa: today, week, month, year, o custom."

    try:
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        transactions = TransaccionService.list_transactions(
            date_from=start_dt,
            date_to=end_dt,
            include_voided=False,
            limit=10000,
        )

        if not transactions:
            return f"Ingresos por metodo — {period_label}: No hay transacciones registradas en este periodo."

        totales = {"EFECTIVO": 0.0, "TRANSFERENCIA": 0.0, "POS": 0.0}
        conteos = {"EFECTIVO": 0, "TRANSFERENCIA": 0, "POS": 0}

        for t in transactions:
            if t.payment_method in totales:
                totales[t.payment_method] += t.amount
                conteos[t.payment_method] += 1

        total_general = sum(totales.values())
        total_count = sum(conteos.values())

        lines = [
            f"💰 Ingresos por metodo — {period_label}",
            "",
            f"Total general: {total_general:,.0f} Gs ({total_count} transaccion(es))",
            "",
        ]

        emoji_map = {"EFECTIVO": "💵", "TRANSFERENCIA": "🏦", "POS": "💳"}
        for metodo in ("EFECTIVO", "TRANSFERENCIA", "POS"):
            pct = (totales[metodo] / total_general * 100) if total_general > 0 else 0
            emoji = emoji_map[metodo]
            lines.append(
                f"{emoji} {metodo}: {totales[metodo]:,.0f} Gs "
                f"({conteos[metodo]} transaccion(es), {pct:.0f}%)"
            )

        if total_count > 0:
            promedio = total_general / total_count
            lines.append("")
            lines.append(f"Promedio por transaccion: {promedio:,.0f} Gs")

        return "\n".join(lines)
    except Exception as e:
        return f"Error al consultar ingresos por metodo: {e}"


# ==========================================
# TOOL 15: Consultar Inventario (v1.6.0 — Phase 3)
# ==========================================

def consultar_inventario(nombre_producto: Optional[str] = None) -> str:
    """
    Consultar stock de productos del minibar/snacks/servicios del hotel.

    Use cuando el usuario pregunte por stock, inventario, o productos
    disponibles. Sin argumentos lista los productos con stock bajo.
    Con nombre_producto busca un producto especifico.

    Args:
        nombre_producto: Nombre parcial del producto a buscar (opcional).
                         Si es None, muestra productos con stock bajo.

    Returns:
        String con stock actual, alertas de bajo stock, y estado general.

    Examples:
        - "¿Cuanta agua queda?" → consultar_inventario("agua")
        - "¿Que productos estan por agotarse?" → consultar_inventario()
        - "Stock de cerveza" → consultar_inventario("cerveza")
        - "Hay snacks?" → consultar_inventario("snack")
    """
    try:
        if nombre_producto and nombre_producto.strip():
            # Filter products by name substring
            all_products = ProductService.list_products(active_only=True)
            query = nombre_producto.strip().lower()
            matches = [
                p for p in all_products
                if query in (p.name or "").lower()
                or query in (p.category or "").lower()
            ]
            if not matches:
                return f"No se encontraron productos que coincidan con '{nombre_producto}'."

            lines = [f"🛒 Productos que coinciden con '{nombre_producto}':", ""]
            for p in matches:
                if p.is_stocked:
                    stock = p.stock_current if p.stock_current is not None else 0
                    min_s = p.stock_minimum or 0
                    low_flag = " ⚠️ BAJO" if min_s and stock <= min_s else ""
                    lines.append(
                        f"  • {p.name} ({p.category}): {stock} unidad(es)"
                        f" — precio {p.price:,.0f} Gs{low_flag}"
                    )
                else:
                    lines.append(
                        f"  • {p.name} ({p.category}): servicio "
                        f"— precio {p.price:,.0f} Gs"
                    )
            return "\n".join(lines)

        # No filter — list low-stock products
        low = ProductService.get_low_stock_products()
        if not low:
            return "✓ Todos los productos tienen stock suficiente. Ningun producto por debajo del minimo."

        lines = [f"⚠️ {len(low)} producto(s) con stock bajo:", ""]
        for p in low:
            stock = p.stock_current if p.stock_current is not None else 0
            min_s = p.stock_minimum or 0
            lines.append(
                f"  • {p.name} ({p.category}): {stock}/{min_s} unidades — reponer pronto"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error al consultar inventario: {e}"


# ==========================================
# TOOL 16: Consumos por Habitacion (v1.6.0 — Phase 3)
# ==========================================

def consumos_habitacion(query: Optional[str] = None) -> str:
    """
    Listar los consumos (minibar, servicios) de una reserva o habitacion.

    Acepta: numero de reserva, nombre del huesped, o codigo de habitacion.
    Muestra cada consumo con cantidad, precio unitario y total.

    Args:
        query: ID de reserva (ej "0001103"), nombre del huesped, o codigo
               de habitacion (ej "DD-01"). Requerido.

    Returns:
        String con la lista itemizada de consumos + total.

    Examples:
        - "¿Que consumio la habitacion DD-01?" → consumos_habitacion("DD-01")
        - "Consumos de la reserva 1103" → consumos_habitacion("1103")
        - "¿Cuanto gasto Perez en consumos?" → consumos_habitacion("Perez")
    """
    try:
        q = (query or "").strip()
        if not q:
            return "Por favor indique una reserva, nombre o habitacion."

        # Try search_reservation first — reuses existing fuzzy logic
        results = ReservationService.search_reservations(q)
        if not results:
            return f"No se encontro ninguna reserva que coincida con '{query}'."

        # If multiple hits, prefer active reservations (not cancelled/completed)
        active = [
            r for r in results
            if (r.get("status") or "").strip() not in ("CANCELADA", "Cancelada", "COMPLETADA", "Completada")
        ]
        pool = active or results
        target = pool[0]
        reserva_id = target.get("id")
        guest = target.get("guest_name") or "-"
        room_code = target.get("room_internal_code") or target.get("room_id") or "-"

        consumos = ConsumoService.list_by_reserva(
            reserva_id=reserva_id, include_voided=False
        )
        if not consumos:
            return (
                f"Reserva {reserva_id} ({guest}, {room_code}): sin consumos registrados."
            )

        total = sum(float(c.total or 0.0) for c in consumos)
        lines = [
            f"🛒 Consumos de reserva {reserva_id} — {guest} ({room_code})",
            "",
        ]
        for c in consumos:
            fecha = c.created_at.strftime("%d/%m") if c.created_at else "-"
            lines.append(
                f"  • {fecha} · {c.producto_name} x{c.quantity} "
                f"@ {c.unit_price:,.0f} Gs = {c.total:,.0f} Gs"
            )
        lines.append("")
        lines.append(f"Total consumos: {total:,.0f} Gs")

        if len(pool) > 1:
            lines.append(f"\n(Se encontraron {len(pool)} reservas — mostrando la primera activa.)")

        return "\n".join(lines)
    except Exception as e:
        return f"Error al consultar consumos: {e}"


# ==========================================
# TOOL 17: Reporte diario de cocina (Phase 4 — v1.7.0)
# ==========================================

def reporte_cocina(fecha: Optional[str] = None) -> str:
    """
    Reporte diario de cocina con detalle completo por habitación.

    **USA ESTA HERRAMIENTA PARA CUALQUIER pregunta sobre desayunos, comidas,
    cocina, pensión o plan alimenticio** — incluso cuando la pregunta es sobre
    una persona o habitación específica. El reporte incluye TODAS las habitaciones
    activas con nombre del huésped, número de habitación, plan de comidas y
    cantidad de desayunos por habitación. Si necesitas saber si un huésped o
    habitación específica tiene desayuno, llama a esta herramienta y luego busca
    la respuesta en el reporte que retorna.

    Si el hotel no tiene habilitado el servicio de comidas, retorna
    "Servicio de comidas no habilitado" — responde eso mismo al usuario.

    Args:
        fecha: Fecha en formato YYYY-MM-DD. Si no se pasa, usa mañana (planificación).

    Returns:
        String multi-línea con:
          - Total de desayunos del día
          - Modalidad (INCLUIDO / OPCIONAL_PERSONA / OPCIONAL_HABITACION)
          - Lista de habitaciones: "Hab <código> — <huésped>: <desayunos>/<pax> · <plan>"
          - Total de huéspedes sin desayuno (si aplica)

    Examples:
        - "¿Cuántos desayunos hay mañana?" → reporte_cocina()
        - "¿Quiénes desayunan el 20/04?" → reporte_cocina("2026-04-20")
        - "Juan Pérez tiene desayuno mañana?" → reporte_cocina() y busca "Juan Pérez" en el resultado
        - "La habitación DF-01 tiene desayuno?" → reporte_cocina() y busca "DF-01" en el resultado
        - "Qué plan tiene Maria García?" → reporte_cocina() y busca "Maria García"
        - "Reporte de cocina hoy" → reporte_cocina(date.today().isoformat())
    """
    try:
        config = SettingsService.get_meals_config()
        if not config.get("meals_enabled"):
            return "Servicio de comidas no habilitado en este hotel."

        if fecha:
            try:
                target = datetime.strptime(fecha, "%Y-%m-%d").date()
            except ValueError:
                return f"Fecha inválida: {fecha}. Usa formato YYYY-MM-DD."
        else:
            target = date.today() + timedelta(days=1)

        report = KitchenReportService.get_daily_report(fecha=target)
        rooms = report.get("rooms", [])
        total_bf = report.get("total_with_breakfast", 0)
        total_without = report.get("total_without", 0)
        mode = report.get("mode") or "-"

        lines = [
            f"Reporte de cocina — {target.strftime('%d/%m/%Y')}",
            f"Modalidad: {mode}",
            f"Total desayunos: {total_bf}",
        ]
        if total_without > 0:
            lines.append(f"Sin desayuno: {total_without} huéspedes")
        if not rooms:
            lines.append("\nSin reservas activas para esta fecha.")
            return "\n".join(lines)

        lines.append("\nDetalle por habitación:")
        for row in rooms:
            marker = " (hoy sale)" if row.get("checkout_today") else ""
            plan_label = row.get("plan_name") or row.get("plan_code") or "-"
            lines.append(
                f"  Hab {row['internal_code']} — {row['guest_name']}: "
                f"{row['breakfast_guests']}/{row['guests_count']} pax · {plan_label}{marker}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error al generar reporte de cocina: {e}"


# ==========================================
# TOOL 18: Estado del email de una reserva (Phase 5 — v1.8.0)
# ==========================================

def estado_email_reserva(query: Optional[str] = None) -> str:
    """
    Consulta si se envió el correo de confirmación a una reserva y cuándo.

    Úsala para preguntas como:
      - "¿Se le mandó el correo a la reserva 1234?"
      - "¿Cuándo se envió el email a Juan Pérez?"
      - "¿El correo de la reserva 45 fue enviado?"
      - "¿Se envió el correo de la reserva de García?"

    Args:
        query: ID de reserva (ej "0001234") o nombre del huésped (parcial OK).
               Si es None o vacío, devuelve instrucciones.

    Returns:
        String descriptivo con:
          - Nombre del huésped + ID de reserva
          - Último envío (fecha, hora, email destino, estado)
          - Total de envíos exitosos e intentos fallidos
          - O "No se ha enviado ningún correo" si no hay registros.
    """
    try:
        if not query or not query.strip():
            return (
                "Uso: pasá el ID de la reserva (ej. '0001234') o el nombre del huésped. "
                "Ejemplo: estado_email_reserva('Juan Pérez')."
            )

        q = query.strip()
        reservations = ReservationService.search_reservations(q)
        if not reservations:
            return f"No se encontraron reservas para '{q}'."

        # Pick the most recent match (search returns list of dicts with id/guest_name/check_in)
        reservation = reservations[0]
        reserva_id = reservation.get("id") or reservation.get("reservation_id")
        guest_name = reservation.get("guest_name") or "Sin nombre"

        logs = EmailService.get_email_log(reserva_id=reserva_id, limit=50)
        if not logs:
            extra = f" (se encontraron {len(reservations)} reservas, mostrando la primera)" if len(reservations) > 1 else ""
            return (
                f"Reserva {reserva_id} — {guest_name}{extra}.\n"
                f"No se ha enviado ningún correo a esta reserva."
            )

        ultimo = logs[0]
        fecha_ref = ultimo.sent_at or ultimo.created_at
        fecha_txt = fecha_ref.strftime("%d/%m/%Y %H:%M") if fecha_ref else "-"
        enviados = sum(1 for l in logs if l.status == "ENVIADO")
        fallidos = sum(1 for l in logs if l.status == "FALLIDO")
        pendientes = sum(1 for l in logs if l.status == "PENDIENTE")

        lines = [
            f"Reserva {reserva_id} — {guest_name}",
            f"Último intento: {fecha_txt} a {ultimo.recipient_email} ({ultimo.status})",
        ]
        if ultimo.status == "FALLIDO" and ultimo.error_message:
            lines.append(f"  Error: {ultimo.error_message[:120]}")
        lines.append(f"Total: {enviados} enviado(s), {fallidos} fallido(s), {pendientes} pendiente(s)")
        if len(reservations) > 1:
            lines.append(f"\n(Se encontraron {len(reservations)} reservas — mostrando la primera.)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error al consultar estado del email: {e}"


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
    calculate_price,
    get_occupancy_for_month,
    get_room_performance,
    get_booking_sources,
    get_parking_status,
    get_revenue_summary,
    consultar_caja,
    resumen_ingresos_por_metodo,
    consultar_inventario,
    consumos_habitacion,
    reporte_cocina,
    estado_email_reserva,
]
