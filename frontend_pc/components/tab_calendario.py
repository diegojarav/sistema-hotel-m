import streamlit as st
import pandas as pd
from datetime import date, timedelta

from helpers.constants import MESES_ES
from helpers.data_fetchers import get_all_rooms_list, get_room_categories
from components.calendar_render import render_native_calendar, render_day_reservations
from services import ReservationService


def render_tab_calendario():
    """Renders the Calendar & Status tab with monthly, weekly, and daily views."""
    st.header("📅 Planilla de Ocupación")

    # Selectores de año y mes
    col_year, col_month, col_view = st.columns([1, 1, 2])
    with col_year:
        selected_year = st.selectbox(
            "Año",
            options=list(range(2024, 2030)),
            index=list(range(2024, 2030)).index(date.today().year),
            key="desk_year"
        )
    with col_month:
        selected_month = st.selectbox(
            "Mes",
            options=list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda x: MESES_ES[x-1],
            key="desk_month"
        )

    # Sub-tabs
    tab_mensual, tab_semanal, tab_diaria = st.tabs([
        "📆 Vista Mensual",
        "🗓️ Vista Semanal",
        "📝 Vista Diaria"
    ])

    with tab_mensual:
        st.markdown(f"### 📆 {MESES_ES[selected_month-1]} {selected_year}")

        # Obtener mapa de ocupación
        occupancy_map = ReservationService.get_occupancy_map(selected_year, selected_month)

        # Renderizar calendario nativo
        render_native_calendar(selected_year, selected_month, occupancy_map)

        st.divider()

        # Selector de día para ver detalle
        col_day_sel, col_day_info = st.columns([1, 3])
        with col_day_sel:
            dia_detalle = st.date_input(
                "Ver detalle del día:",
                value=date.today(),
                key="detail_day"
            )
        with col_day_info:
            render_day_reservations(dia_detalle, occupancy_map)

        # === LISTADO CRONOLÓGICO DE RESERVAS ===
        st.divider()
        st.subheader("📋 Listado Cronológico de Reservas")

        # Obtener todas las reservas activas
        all_reservations = ReservationService.get_all_reservations()

        if all_reservations:
            # Convertir a DataFrame
            df_reservas = pd.DataFrame([{
                "ID": r.id,
                "Huésped": r.guest_name or "Sin nombre",
                "Habitación": r.room_internal_code or r.room_id or "-",
                "Check-in": r.check_in.strftime("%Y-%m-%d") if r.check_in else "-",
                "Check-out": r.check_out.strftime("%Y-%m-%d") if r.check_out else "-",
                "Noches": (r.check_out - r.check_in).days if r.check_in and r.check_out else 0,
                "Estado": r.status or "Pendiente"
            } for r in all_reservations])

            # Ordenar por Check-in (ascendente)
            df_reservas = df_reservas.sort_values("Check-in", ascending=True)

            # Función para colorear filas según estado
            def color_by_status(row):
                status = row["Estado"]
                if status == "Cancelada":
                    return ["background-color: #ffcdd2; color: #b71c1c"] * len(row)
                elif status == "Confirmada":
                    return ["background-color: #c8e6c9; color: #1b5e20"] * len(row)
                elif status == "CheckIn":
                    return ["background-color: #bbdefb; color: #0d47a1"] * len(row)
                elif status == "CheckOut":
                    return ["background-color: #e1bee7; color: #4a148c"] * len(row)
                else:
                    return [""] * len(row)

            # Aplicar estilos y mostrar
            styled_df = df_reservas.style.apply(color_by_status, axis=1)
            st.dataframe(
                styled_df,
                hide_index=True,
                height=400
            )

            st.caption(f"📊 Total: {len(df_reservas)} reservas | 🔴 Cancelada | 🟢 Confirmada | 🔵 CheckIn | 🟣 CheckOut")
        else:
            st.info("No hay reservas registradas para este período.")

    with tab_semanal:
        fecha_referencia = st.date_input("Ver situación al día:", value=date.today(), key="week_ref")
        st.caption(f"Semana del: {fecha_referencia.strftime('%d/%m/%Y')}")

        matrix_data = ReservationService.get_weekly_view(fecha_referencia)

        fechas_cols = [fecha_referencia + timedelta(days=i) for i in range(7)]
        col_names = [f.strftime("%A %d/%m") for f in fechas_cols]
        date_keys = [f.strftime("%Y-%m-%d") for f in fechas_cols]

        rows = []
        # Obtener lista de habitaciones dinámicamente
        all_rooms_data = get_all_rooms_list()
        # Sort rooms by internal code or ID
        all_rooms_data.sort(key=lambda x: x.get('internal_code', x['id']))
        # Extract just the IDs or Codes for the display, ensuring uniqueness
        seen_codes = set()
        lista_habitaciones = []
        for r in all_rooms_data:
            code = r['internal_code'] or r['id']
            if code not in seen_codes:
                lista_habitaciones.append(code)
                seen_codes.add(code)

        for hab in lista_habitaciones:
            row_data = {"Habitación": hab}
            hab_data = matrix_data.get(hab, {})
            for i, d_key in enumerate(date_keys):
                row_data[col_names[i]] = hab_data.get(d_key, "")
            rows.append(row_data)

        df_semanal = pd.DataFrame(rows).set_index("Habitación")

        st.dataframe(
            df_semanal.style.map(lambda x: "background-color: #ffcdd2; color: black; font-weight: bold" if x != "" else ""),
            height=600
        )

    with tab_diaria:
        fecha_diaria = st.date_input("Estado del día:", value=date.today(), key="daily_ref")
        st.caption(f"Estado: {fecha_diaria}")

        status_list = ReservationService.get_daily_status(fecha_diaria)

        # Build category description lookup (by name)
        all_cats = get_room_categories()
        cat_desc_map = {c["name"]: c.get("description", "") for c in all_cats} if all_cats else {}

        for info in status_list:
            with st.container():
                c1, c2, c3, c4 = st.columns([1, 2, 4, 2])
                c1.subheader(f"🚪{info.get('internal_code', info['room_id'])}")
                # Show category name and description
                room_type = info.get('type', '')
                if room_type:
                    c1.caption(room_type)
                    cat_desc = cat_desc_map.get(room_type, "")
                    if cat_desc:
                        c1.caption(cat_desc)
                if info['status'] == "OCUPADA":
                    c2.markdown(":red[**OCUPADA**]")
                    c3.write(f"👤 {info['huesped']}")
                    if info['res_id']:
                        c3.caption(f"🆔 {info['res_id']}")
                        with st.expander(f"❌ Cancelar"):
                            motivo = st.text_input("Motivo", key=f"m_{info['res_id']}")
                            if st.button("Confirmar", key=f"b_{info['res_id']}"):
                                if ReservationService.cancel_reservation(info['res_id'], motivo, st.session_state.user.username):
                                    st.success("Cancelada")
                                    st.rerun()
                else:
                    c2.markdown(":green[**LIBRE**]")
                st.divider()
