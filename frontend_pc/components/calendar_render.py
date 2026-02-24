import streamlit as st
import streamlit.components.v1 as components
import calendar as cal_module
from datetime import date

from helpers.constants import DIAS_SEMANA
from services import ReservationService


def render_native_calendar(year: int, month: int, occupancy_map: dict):
    """
    Renderiza un calendario mensual visual con HTML/CSS optimizado para desktop.

    Args:
        year: Año a mostrar
        month: Mes a mostrar (1-12)
        occupancy_map: Dict de ocupación del servicio
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    # Obtener matriz del mes
    month_matrix = cal_module.monthcalendar(year, month)
    num_weeks = len(month_matrix)

    # CSS del calendario - DESKTOP OPTIMIZADO
    css = """
    <style>
        * {
            box-sizing: border-box;
        }
        .calendar-container {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            width: 100%;
            max-width: 100%;
            margin: 0 auto;
            padding: 8px;
        }
        .calendar-header {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            text-align: center;
            padding: 12px 0;
            font-weight: 700;
            color: #aaa;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 2px solid #444;
            margin-bottom: 12px;
        }
        .calendar-body {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .calendar-row {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 4px;
        }
        .day-cell {
            min-height: 80px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .day-cell:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 20px rgba(0,0,0,0.4);
            z-index: 10;
        }
        .day-empty {
            background: transparent;
        }
        .status-free {
            background: #1e1e1e;
            color: #888;
            border: 1px solid #333;
        }
        .status-medium {
            background: linear-gradient(135deg, #14532d, #166534);
            color: #86efac;
            border: 2px solid #22c55e;
        }
        .status-high {
            background: linear-gradient(135deg, #7f1d1d, #991b1b);
            color: #fca5a5;
            border: 2px solid #ef4444;
        }
        .day-today {
            box-shadow: 0 0 0 3px #3b82f6, 0 0 15px rgba(59, 130, 246, 0.4);
            font-weight: bold;
        }
        .legend {
            display: flex;
            justify-content: center;
            gap: clamp(10px, 2vw, 25px);
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #333;
            flex-wrap: wrap;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: clamp(10px, 1.2vw, 13px);
            color: #888;
        }
        .legend-dot {
            width: clamp(10px, 1.5vw, 14px);
            height: clamp(10px, 1.5vw, 14px);
            border-radius: 4px;
        }
        .dot-free { background: #1e1e1e; border: 1px solid #333; }
        .dot-medium { background: #166534; border: 2px solid #22c55e; }
        .dot-high { background: #991b1b; border: 2px solid #ef4444; }
    </style>
    """

    # Header días de semana
    header_html = '<div class="calendar-header">'
    for dia in DIAS_SEMANA:
        header_html += f'<span>{dia}</span>'
    header_html += '</div>'

    # Grid del calendario - cada semana es una fila
    grid_html = '<div class="calendar-body">'

    for week in month_matrix:
        grid_html += '<div class="calendar-row">'
        for day in week:
            if day == 0:
                grid_html += '<div class="day-cell day-empty"></div>'
            else:
                day_date = date(year, month, day)
                day_key = day_date.strftime("%Y-%m-%d")
                day_data = occupancy_map.get(day_key, {"status": "free", "count": 0})

                status = day_data['status']
                count = day_data['count']
                is_today = day_key == today_str

                status_class = f"status-{status}"
                today_class = "day-today" if is_today else ""

                tooltip = f"{count} reserva(s)" if count > 0 else "Libre"

                grid_html += f'<div class="day-cell {status_class} {today_class}" title="{tooltip}">{day}</div>'
        grid_html += '</div>'

    grid_html += '</div>'

    # Leyenda
    legend_html = """
    <div class="legend">
        <div class="legend-item"><div class="legend-dot dot-free"></div> Libre</div>
        <div class="legend-item"><div class="legend-dot dot-medium"></div> 1-5 reservas</div>
        <div class="legend-item"><div class="legend-dot dot-high"></div> +5 reservas</div>
    </div>
    """

    # HTML completo
    full_html = f"""
    <div class="calendar-container">
        {css}
        {header_html}
        {grid_html}
        {legend_html}
    </div>
    """

    # Altura dinámica para desktop: base + (semanas * altura por fila)
    base_height = 120  # header + legend + padding
    row_height = 90    # altura por semana (celdas más grandes para desktop)
    height = base_height + (num_weeks * row_height)

    components.html(full_html, height=height, scrolling=False)


def render_day_reservations(selected_date: date, occupancy_map: dict):
    """Renderiza las reservas de un día específico como tarjetas."""
    day_key = selected_date.strftime("%Y-%m-%d")
    day_data = occupancy_map.get(day_key, {"count": 0, "ids": [], "guests": []})

    if day_data["count"] == 0:
        st.success(f"✅ No hay reservas para {selected_date.strftime('%d/%m/%Y')}")
        return

    st.markdown(f"### 📅 Reservas del {selected_date.strftime('%d/%m/%Y')}")

    for i, (res_id, guest) in enumerate(zip(day_data["ids"], day_data["guests"])):
        with st.expander(f"🏠 {guest}", expanded=(i == 0)):
            st.write(f"**ID Reserva:** {res_id}")
            st.write(f"**Huésped:** {guest}")
            if st.button(f"❌ Cancelar", key=f"cancel_{res_id}_{day_key}"):
                if ReservationService.cancel_reservation(res_id, "Cancelación desde calendario", st.session_state.user.username):
                    st.success("Reserva cancelada")
                    st.rerun()
