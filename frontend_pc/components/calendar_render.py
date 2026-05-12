import streamlit as st
import streamlit.components.v1 as components
import calendar as cal_module
import pandas as pd
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


def render_monthly_room_grid(data: dict, year: int, month: int):
    """
    Renderiza la ficha mensual de habitaciones: rows=rooms, columns=days.
    Gantt-style planning board rendered via HTML in an iframe.
    """
    today = date.today()
    rooms = data.get("rooms", [])
    days = data.get("days", [])
    matrix = data.get("matrix", {})
    num_days = len(days)

    if not rooms:
        st.warning("No hay habitaciones activas.")
        return

    # Color mapping by status (supports legacy + v1.4.0 new values)
    status_colors = {
        "Confirmada": {"bg": "#dcfce7", "text": "#166534"},
        "CONFIRMADA": {"bg": "#dcfce7", "text": "#166534"},
        "Pendiente": {"bg": "#fef9c3", "text": "#854d0e"},
        "RESERVADA": {"bg": "#e5e7eb", "text": "#374151"},
        "SEÑADA": {"bg": "#fef9c3", "text": "#854d0e"},
        "Completada": {"bg": "#dbeafe", "text": "#1e40af"},
        "COMPLETADA": {"bg": "#dbeafe", "text": "#1e40af"},
        "Cancelada": {"bg": "#fee2e2", "text": "#991b1b"},
        "CANCELADA": {"bg": "#fee2e2", "text": "#991b1b"},
    }
    default_color = {"bg": "#f3f4f6", "text": "#374151"}

    # Build CSS
    css = """
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .grid-wrapper {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            overflow-x: auto;
            max-width: 100%;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
        }
        table.room-grid {
            border-collapse: collapse;
            min-width: 100%;
            font-size: 11px;
        }
        table.room-grid th, table.room-grid td {
            border: 1px solid #e5e7eb;
            padding: 4px 6px;
            text-align: center;
            white-space: nowrap;
        }
        table.room-grid thead th {
            background: #f9fafb;
            color: #6b7280;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 2;
        }
        /* Sticky first 2 columns */
        table.room-grid th:nth-child(1),
        table.room-grid td:nth-child(1) {
            position: sticky;
            left: 0;
            z-index: 3;
            background: #f9fafb;
            font-weight: 600;
            color: #111827;
            min-width: 60px;
        }
        table.room-grid th:nth-child(2),
        table.room-grid td:nth-child(2) {
            position: sticky;
            left: 60px;
            z-index: 3;
            background: #f9fafb;
            color: #6b7280;
            font-size: 10px;
            min-width: 70px;
        }
        /* Sticky header corners */
        table.room-grid thead th:nth-child(1),
        table.room-grid thead th:nth-child(2) {
            z-index: 4;
        }
        .cell-occupied {
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 10px;
            font-weight: 500;
            max-width: 70px;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .cell-checkin { border-left: 3px solid #3b82f6 !important; }
        .cell-checkout { border-right: 3px solid #ef4444 !important; }
        .cell-cancelled .cell-occupied { text-decoration: line-through; opacity: 0.6; }
        .col-today { background: #fef3c7 !important; border-bottom: 2px solid #f59e0b; }
        .col-weekend { background: #f9fafb; }
        .legend-bar {
            display: flex; gap: 16px; padding: 8px 12px;
            border-top: 1px solid #e5e7eb; font-size: 11px; color: #6b7280;
            flex-wrap: wrap;
        }
        .legend-bar span {
            display: inline-flex; align-items: center; gap: 4px;
        }
        .legend-swatch {
            display: inline-block; width: 12px; height: 12px;
            border-radius: 3px;
        }
    </style>
    """

    # Build header row
    header = '<tr><th>Hab.</th><th>Categoría</th>'
    for d in days:
        day_date = date(year, month, d)
        is_today = day_date == today
        is_weekend = day_date.weekday() >= 5
        cls = "col-today" if is_today else ("col-weekend" if is_weekend else "")
        dow = ["L", "M", "X", "J", "V", "S", "D"][day_date.weekday()]
        header += f'<th class="{cls}">{dow}<br>{d}</th>'
    header += '</tr>'

    # Build body rows
    body = ''
    for room in rooms:
        code = room["code"]
        cat = room["category"]
        room_data = matrix.get(code, {})
        body += f'<tr><td>{code}</td><td>{cat[:8]}</td>'
        for d in days:
            day_str = str(d)
            cell = room_data.get(day_str)
            day_date = date(year, month, d)
            is_today = day_date == today
            is_weekend = day_date.weekday() >= 5
            td_cls = "col-today" if is_today else ("col-weekend" if is_weekend else "")

            if cell:
                guest = cell.get("guest", "")[:10]
                st_name = cell.get("status", "")
                colors = status_colors.get(st_name, default_color)
                extra_cls = ""
                if cell.get("is_checkin"):
                    extra_cls += " cell-checkin"
                if cell.get("is_checkout"):
                    extra_cls += " cell-checkout"
                if st_name == "Cancelada":
                    extra_cls += " cell-cancelled"
                res_id = cell.get("res_id", "")
                body += (
                    f'<td class="{td_cls}{extra_cls}" title="{cell.get("guest", "")} | {st_name} | #{res_id}">'
                    f'<div class="cell-occupied" style="background:{colors["bg"]};color:{colors["text"]}">'
                    f'{guest}</div></td>'
                )
            else:
                body += f'<td class="{td_cls}"></td>'
        body += '</tr>'

    # Legend
    legend = """
    <div class="legend-bar">
        <span><span class="legend-swatch" style="background:#dcfce7;border:1px solid #166534"></span> Confirmada</span>
        <span><span class="legend-swatch" style="background:#dbeafe;border:1px solid #1e40af"></span> CheckIn</span>
        <span><span class="legend-swatch" style="background:#fef3c7;border:1px solid #92400e"></span> CheckOut</span>
        <span><span class="legend-swatch" style="background:#fee2e2;border:1px solid #991b1b"></span> Cancelada</span>
        <span><span class="legend-swatch" style="border-left:3px solid #3b82f6;width:6px"></span> Día entrada</span>
        <span><span class="legend-swatch" style="border-right:3px solid #ef4444;width:6px"></span> Día salida</span>
        <span><span class="legend-swatch" style="background:#fef3c7;border:1px solid #f59e0b"></span> Hoy</span>
    </div>
    """

    full_html = f"""
    <div class="grid-wrapper">
        {css}
        <table class="room-grid">
            <thead>{header}</thead>
            <tbody>{body}</tbody>
        </table>
        {legend}
    </div>
    """

    # Height: header(40) + rows(28 each) + legend(40) + padding(20)
    height = 40 + len(rooms) * 28 + 40 + 20
    components.html(full_html, height=height, scrolling=True)


def render_day_reservations(selected_date: date, occupancy_map: dict):
    """Renderiza las reservas de un día específico como tarjetas."""
    day_key = selected_date.strftime("%Y-%m-%d")
    day_data = occupancy_map.get(day_key, {"count": 0, "ids": [], "guests": []})

    if day_data["count"] == 0:
        st.success(f"✅ No hay reservas para {selected_date.strftime('%d/%m/%Y')}")
        return

    st.markdown(f"### 📅 Reservas del {selected_date.strftime('%d/%m/%Y')}")

    statuses = day_data.get("statuses", [])
    # Emoji mapping supports both legacy (Pendiente/Confirmada) and new v1.4.0 (RESERVADA/SEÑADA/CONFIRMADA)
    status_emoji_map = {
        "Pendiente": "🟡", "RESERVADA": "⚪", "SEÑADA": "🟡",
        "Confirmada": "🟢", "CONFIRMADA": "🟢",
        "Completada": "🔵", "COMPLETADA": "🔵",
        "Cancelada": "🔴", "CANCELADA": "🔴",
    }
    active_states = ("Pendiente", "Confirmada", "RESERVADA", "SEÑADA", "CONFIRMADA")

    for i, (res_id, guest) in enumerate(zip(day_data["ids"], day_data["guests"])):
        res_status = statuses[i] if i < len(statuses) else "Confirmada"
        status_emoji = status_emoji_map.get(res_status, "⚪")
        with st.expander(f"🏠 {guest} {status_emoji} {res_status}", expanded=(i == 0)):
            st.write(f"**ID Reserva:** {res_id}")
            st.write(f"**Huésped:** {guest}")
            st.write(f"**Estado:** {status_emoji} {res_status}")

            # Show saldo (uses backend /saldo endpoint via TransaccionService)
            try:
                from services import TransaccionService
                saldo = TransaccionService.get_saldo(reserva_id=res_id)
                if saldo:
                    col_t, col_p, col_s = st.columns(3)
                    col_t.metric("Total", f"{saldo['total']:,.0f} Gs".replace(",", "."))
                    col_p.metric("Pagado", f"{saldo['paid']:,.0f} Gs".replace(",", "."))
                    col_s.metric("Saldo", f"{saldo['pending']:,.0f} Gs".replace(",", "."))
            except Exception:
                pass

            # ==========================================================
            # CONSUMOS — daily view entry point (v1.10.0)
            # ==========================================================
            # Receptionist UX: charging a Coca-Cola needs to be 2-3 clicks
            # from the calendar tab. Before v1.10.0 this section lived ONLY in
            # tab_reserva.py edit mode — buried 5+ clicks deep. Now it's
            # alongside Registrar Pago, where the natural workflow is:
            # see saldo → charge consumos → collect payment.
            #
            # The edit-mode section in tab_reserva.py stays as the
            # detailed audit view (voided rows, void buttons, folio PDF).
            # ==========================================================
            if res_status in active_states:
                st.markdown("---")
                try:
                    from services import ConsumoService, ConsumoError, ProductService
                    _consumos_active = ConsumoService.list_by_reserva(
                        reserva_id=res_id, include_voided=False
                    )
                except Exception:
                    _consumos_active = []
                    ConsumoError = Exception  # noqa: F811

                _consumo_total = sum(float(c.total or 0) for c in _consumos_active)
                _consumo_count_lbl = f"{len(_consumos_active)} producto(s)"
                _consumo_total_lbl = f"{_consumo_total:,.0f} Gs".replace(",", ".")
                st.markdown(
                    f"**🧾 Consumos** ({_consumo_count_lbl} · {_consumo_total_lbl})"
                )

                if _consumos_active:
                    _rows = []
                    for c in _consumos_active:
                        _rows.append({
                            "Producto": c.producto_name,
                            "Cant.": int(c.quantity or 0),
                            "Total (Gs)": f"{float(c.total or 0):,.0f}".replace(",", "."),
                            "Fecha": (
                                c.created_at.strftime("%d/%m %H:%M")
                                if c.created_at else "-"
                            ),
                        })
                    st.dataframe(pd.DataFrame(_rows), hide_index=True, width="stretch")
                else:
                    st.caption("Sin consumos registrados en esta reserva.")

                # --- Cargar Producto form (expander) ---
                with st.expander("➕ Cargar Producto", expanded=False):
                    try:
                        _all_products = ProductService.list_products(active_only=True)
                    except Exception:
                        _all_products = []

                    if not _all_products:
                        st.warning(
                            "No hay productos activos en el catálogo. "
                            "Agregalos desde **📦 Inventario** antes de cargar consumos."
                        )
                    else:
                        # Build product picker — name + price + stock label;
                        # skip out-of-stock items (mobile parity).
                        _opt_to_p = {}
                        for _p in _all_products:
                            if _p.is_stocked and (_p.stock_current or 0) <= 0:
                                continue
                            _stock_str = (
                                f" · stock {_p.stock_current}"
                                if _p.is_stocked else ""
                            )
                            _price_str = f"{float(_p.price or 0):,.0f}".replace(",", ".")
                            _label = f"{_p.name} — {_price_str} Gs{_stock_str}"
                            _opt_to_p[_label] = _p
                        _opt_labels = list(_opt_to_p.keys())

                        if not _opt_labels:
                            st.warning(
                                "Todos los productos del catálogo están sin stock. "
                                "Reponé desde **📦 Inventario**."
                            )
                        else:
                            _col_prod, _col_qty = st.columns([3, 1])
                            with _col_prod:
                                _pick_label = st.selectbox(
                                    "Producto",
                                    options=_opt_labels,
                                    key=f"daily_cons_prod_{res_id}_{day_key}",
                                )
                            _picked = _opt_to_p.get(_pick_label)
                            with _col_qty:
                                _max_q = (
                                    int(_picked.stock_current or 1)
                                    if (_picked and _picked.is_stocked)
                                    else 99
                                )
                                _qty = st.number_input(
                                    "Cantidad",
                                    min_value=1,
                                    max_value=max(_max_q, 1),
                                    value=1,
                                    step=1,
                                    key=f"daily_cons_qty_{res_id}_{day_key}",
                                )

                            _note = st.text_input(
                                "Nota (opcional)",
                                placeholder="Ej: consumido en la cena",
                                key=f"daily_cons_note_{res_id}_{day_key}",
                            )

                            if _picked:
                                _running = float(_picked.price or 0) * int(_qty)
                                _running_lbl = (
                                    f"{_running:,.0f} Gs".replace(",", ".")
                                )
                                st.info(
                                    f"💵 **Total: {_running_lbl}** "
                                    f"({_picked.name} × {int(_qty)})"
                                )

                            if st.button(
                                "🧾 Registrar Consumo",
                                type="primary",
                                disabled=not _picked,
                                key=f"daily_cons_submit_{res_id}_{day_key}",
                                use_container_width=True,
                            ):
                                try:
                                    _username = (
                                        st.session_state.user.username
                                        if hasattr(st.session_state, "user")
                                        else "pc-user"
                                    )
                                    ConsumoService.registrar_consumo(
                                        reserva_id=res_id,
                                        producto_id=_picked.id,
                                        quantity=int(_qty),
                                        description=(_note or "").strip() or None,
                                        created_by=_username,
                                    )
                                    _success_lbl = (
                                        f"{float(_picked.price or 0) * int(_qty):,.0f} Gs"
                                        .replace(",", ".")
                                    )
                                    st.success(
                                        f"✓ {_picked.name} × {int(_qty)} registrado "
                                        f"— {_success_lbl}"
                                    )
                                    from frontend_services.cache_service import force_refresh
                                    force_refresh()
                                    st.rerun()
                                except ConsumoError as _e:
                                    st.error(f"❌ {_e}")
                                except Exception as _e:
                                    st.error(f"❌ Error inesperado: {_e}")

            # Registrar Pago form (only for active reservations with pending balance)
            if res_status in active_states and saldo and saldo["pending"] > 0:
                st.markdown("---")
                st.markdown("**💰 Registrar Pago**")
                pay_col1, pay_col2, pay_col3 = st.columns([1, 1, 1])
                with pay_col1:
                    metodo = st.selectbox(
                        "Método", ["TRANSFERENCIA", "EFECTIVO", "POS"],
                        key=f"metodo_{res_id}_{day_key}"
                    )
                with pay_col2:
                    monto = st.number_input(
                        "Monto (Gs)", min_value=0.0, value=float(saldo["pending"]),
                        step=1000.0, format="%.0f",
                        key=f"monto_{res_id}_{day_key}"
                    )
                with pay_col3:
                    ref = st.text_input(
                        "Referencia", key=f"ref_{res_id}_{day_key}",
                        placeholder="Nro. transferencia/voucher"
                    )
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button(f"✅ Registrar Pago", key=f"pagar_{res_id}_{day_key}"):
                        try:
                            from services import TransaccionService
                            user = st.session_state.user
                            TransaccionService.registrar_pago(
                                reserva_id=res_id,
                                amount=monto,
                                payment_method=metodo,
                                reference_number=ref or None,
                                created_by=user.username,
                                user_id=user.id if metodo == "EFECTIVO" else None,
                            )
                            from frontend_services.cache_service import force_refresh
                            force_refresh()
                            st.success(f"Pago de {monto:,.0f} Gs registrado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                with btn_col2:
                    if res_status in active_states:
                        if st.button(f"❌ Cancelar Reserva", key=f"cancel_{res_id}_{day_key}"):
                            if ReservationService.cancel_reservation(res_id, "Cancelación desde calendario", st.session_state.user.username):
                                from frontend_services.cache_service import force_refresh
                                force_refresh()
                                st.success("Reserva cancelada")
                                st.rerun()
            elif res_status in active_states:
                if st.button(f"❌ Cancelar Reserva", key=f"cancel_{res_id}_{day_key}"):
                    if ReservationService.cancel_reservation(res_id, "Cancelación desde calendario", st.session_state.user.username):
                        from frontend_services.cache_service import force_refresh
                        force_refresh()
                        st.success("Reserva cancelada")
                        st.rerun()
