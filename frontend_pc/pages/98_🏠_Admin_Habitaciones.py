"""
Hotel Munich - Administracion de Habitaciones
==============================================

Panel para gestionar el inventario de habitaciones del hotel.
Permite agregar, modificar y consultar habitaciones por categoria.

Funcionalidades:
- Ver inventario de habitaciones por categoria
- Agregar nuevas habitaciones dinamicamente
- Cambiar estado de habitaciones (disponible, mantenimiento, etc.)
- Resumen estadistico por categoria

V8 FIX: Refactored to use API calls instead of direct sqlite3 access.
"""

import streamlit as st
import requests
from datetime import datetime, date, timedelta
import io
import csv
import pandas as pd

# Import logging and shared session (PERF-10)
from logging_config import get_logger
from api_client import get_session

_s = get_session()

logger = get_logger(__name__)

# ==========================================
# CONFIGURATION
# ==========================================

# API Base URL
API_BASE_URL = "http://localhost:8000/api/v1"

# Room status options
ROOM_STATUSES = {
    "available": "Disponible",
    "occupied": "Ocupada",
    "maintenance": "Mantenimiento",
    "cleaning": "Limpieza",
    "out_of_service": "Fuera de Servicio"
}

STATUS_COLORS = {
    "available": "green",
    "occupied": "red",
    "maintenance": "orange",
    "cleaning": "blue",
    "out_of_service": "gray"
}

# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="Admin - Habitaciones",
    page_icon="🏠",
    layout="wide"
)


# ==========================================
# SECURITY CHECK
# ==========================================

def check_admin_access():
    """Verify user is logged in and has appropriate role."""
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.error("Debe iniciar sesion para acceder a esta pagina")
        st.stop()

    user = st.session_state.get('user')
    if not user:
        st.error("Sesion invalida")
        st.stop()

    # Allow admin and supervisor roles
    if hasattr(user, 'role') and user.role:
        if user.role.lower() in ['admin', 'supervisor', 'gerencia']:
            return True

    st.warning("**Area Restringida** - Esta seccion esta destinada a administradores.")
    return True


# ==========================================
# API HELPER FUNCTIONS
# ==========================================

def get_auth_headers():
    """Get authorization headers from session."""
    token = st.session_state.get('api_token')
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def get_all_categories():
    """Fetch all room categories via API."""
    try:
        response = _s.get(f"{API_BASE_URL}/rooms/categories", timeout=10)
        if response.ok:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return []


def get_all_rooms():
    """Fetch all rooms with category information via API."""
    try:
        response = _s.get(f"{API_BASE_URL}/rooms", timeout=10)
        if response.ok:
            rooms = response.json()
            # Map API response to expected format
            return [{
                'id': r['id'],
                'internal_code': r.get('internal_code'),
                'floor': r.get('floor'),
                'status': r.get('status', 'available'),
                'notes': None,  # Not in API response
                'active': 1,  # API only returns active rooms
                'category_id': r.get('category_id'),
                'category_name': r.get('category_name', 'Sin Categoria'),
                'base_price': r.get('base_price')
            } for r in rooms]
        return []
    except Exception as e:
        logger.error(f"Error fetching rooms: {e}")
        return []


def get_room_count_by_category(category_id: str) -> int:
    """Get current room count for a category via API."""
    try:
        response = _s.get(
            f"{API_BASE_URL}/rooms/count/{category_id}",
            timeout=10
        )
        if response.ok:
            return response.json().get('count', 0)
        return 0
    except Exception as e:
        logger.error(f"Error fetching room count: {e}")
        return 0


def create_rooms(category_id: str, quantity: int, floor: int, category_name: str) -> tuple:
    """Create new rooms for a category via API."""
    try:
        response = _s.post(
            f"{API_BASE_URL}/rooms",
            json={
                "category_id": category_id,
                "quantity": quantity,
                "floor": floor
            },
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            result = response.json()
            logger.info(f"Creadas {result.get('count', quantity)} habitaciones para categoria {category_name}")
            return True, result.get('message', f"Se crearon {quantity} habitaciones exitosamente")
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error creando habitaciones: {e}")
        return False, str(e)


def update_room_status(room_id: str, new_status: str, reason: str = None) -> tuple:
    """Update room status via API."""
    try:
        response = _s.patch(
            f"{API_BASE_URL}/rooms/{room_id}/status",
            json={
                "status": new_status,
                "reason": reason
            },
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            logger.info(f"Estado de habitacion {room_id} cambiado a {new_status}")
            return True, "Estado actualizado correctamente"
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error actualizando estado: {e}")
        return False, str(e)


def toggle_room_active(room_id: str, active: bool) -> tuple:
    """Activate or deactivate a room via API."""
    try:
        response = _s.patch(
            f"{API_BASE_URL}/rooms/{room_id}/active",
            params={"active": active},
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            status_text = "activada" if active else "desactivada"
            logger.info(f"Habitacion {room_id} {status_text}")
            return True, f"Habitacion {status_text}"
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error cambiando estado activo: {e}")
        return False, str(e)


def delete_room(room_id: str) -> tuple:
    """Delete a room via API."""
    try:
        response = _s.delete(
            f"{API_BASE_URL}/rooms/{room_id}",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            logger.info(f"Habitacion {room_id} eliminada")
            return True, "Habitacion eliminada"
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error eliminando habitacion: {e}")
        return False, str(e)


def get_room_statistics():
    """Get room count statistics by category and status via API."""
    try:
        response = _s.get(
            f"{API_BASE_URL}/rooms/statistics/by-category",
            timeout=10
        )
        if response.ok:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        return []


# ==========================================
# MAIN PAGE
# ==========================================

# Check access
check_admin_access()

# Header
st.title("🏠 Administracion de Habitaciones")
st.caption(f"Gestion del inventario de habitaciones - {st.session_state.get('hotel_name', 'Hotel')}")

st.divider()

# ==========================================
# TAB LAYOUT
# ==========================================

tab_inventory, tab_add, tab_manage, tab_summary, tab_ficha, tab_room_detail = st.tabs([
    "📋 Inventario",
    "➕ Agregar Habitaciones",
    "🔧 Gestionar Habitaciones",
    "📊 Resumen por Categoria",
    "📅 Ficha Mensual",
    "🏠 Resumen por Habitacion"
])


# ------------------------------------------
# TAB 1: Inventory
# ------------------------------------------
with tab_inventory:
    st.subheader("📋 Inventario de Habitaciones")

    col_filter, col_refresh = st.columns([3, 1])

    with col_filter:
        categories = get_all_categories()
        category_options = ["Todas"] + [c['name'] for c in categories]
        selected_category = st.selectbox(
            "Filtrar por categoria",
            options=category_options,
            key="inventory_filter"
        )

    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄 Actualizar", key="refresh_inventory"):
            st.rerun()

    rooms = get_all_rooms()

    if rooms:
        # Filter by category if selected
        if selected_category != "Todas":
            rooms = [r for r in rooms if r.get('category_name') == selected_category]

        # Sort by floor then code
        rooms = sorted(rooms, key=lambda r: (r.get('floor') or 0, r.get('internal_code') or ''))

        if rooms:
            # Create display dataframe
            room_data = []
            for r in rooms:
                status_emoji = {
                    'available': '🟢',
                    'occupied': '🔴',
                    'maintenance': '🟠',
                    'cleaning': '🔵',
                    'out_of_service': '⚫'
                }.get(r['status'], '⚪')

                room_data.append({
                    "Codigo": r['internal_code'] or "—",
                    "Categoria": r['category_name'] or "Sin categoria",
                    "Piso": r['floor'] or "—",
                    "Estado": f"{status_emoji} {ROOM_STATUSES.get(r['status'], r['status'])}",
                    "Activa": "Si" if r['active'] else "No",
                    "Precio Base": f"{r['base_price']:,.0f} Gs" if r['base_price'] else "—",
                    "Notas": r['notes'] or "—"
                })

            st.dataframe(
                room_data,
                width="stretch",
                hide_index=True,
                column_config={
                    "Codigo": st.column_config.TextColumn("Codigo", width="small"),
                    "Categoria": st.column_config.TextColumn("Categoria", width="medium"),
                    "Piso": st.column_config.NumberColumn("Piso", width="small"),
                    "Estado": st.column_config.TextColumn("Estado", width="medium"),
                    "Activa": st.column_config.TextColumn("Activa", width="small"),
                    "Precio Base": st.column_config.TextColumn("Precio", width="medium"),
                    "Notas": st.column_config.TextColumn("Notas", width="large"),
                }
            )

            # Summary
            total = len(rooms)
            active = sum(1 for r in rooms if r['active'])
            available = sum(1 for r in rooms if r['status'] == 'available' and r['active'])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📊 Total", total)
            col2.metric("✅ Activas", active)
            col3.metric("🟢 Disponibles", available)
            col4.metric("🔴 Ocupadas", sum(1 for r in rooms if r['status'] == 'occupied'))

            # Download buttons
            dl_data = []
            for r in rooms:
                dl_data.append({
                    "Codigo": r['internal_code'] or "",
                    "Categoria": r['category_name'] or "",
                    "Piso": r['floor'] or "",
                    "Estado": ROOM_STATUSES.get(r['status'], r['status']),
                    "Precio Base": r['base_price'] or 0,
                })
            dl_col1, dl_col2 = st.columns(2)
            inv_csv = io.StringIO()
            inv_writer = csv.DictWriter(inv_csv, fieldnames=list(dl_data[0].keys()))
            inv_writer.writeheader()
            for row in dl_data:
                inv_writer.writerow(row)
            dl_col1.download_button(
                "📥 Descargar CSV",
                data=inv_csv.getvalue(),
                file_name=f"inventario_habitaciones_{date.today()}.csv",
                mime="text/csv",
                width="stretch"
            )
            inv_df = pd.DataFrame(dl_data)
            inv_buf = io.BytesIO()
            with pd.ExcelWriter(inv_buf, engine="openpyxl") as writer:
                inv_df.to_excel(writer, index=False, sheet_name="Inventario")
            dl_col2.download_button(
                "📥 Descargar Excel",
                data=inv_buf.getvalue(),
                file_name=f"inventario_habitaciones_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )
        else:
            st.info(f"No hay habitaciones en la categoria '{selected_category}'")
    else:
        st.warning("No hay habitaciones registradas. Use la pestana 'Agregar Habitaciones' para crear el inventario inicial.")
        st.info("💡 **Tip:** Primero ejecute el script `seed_monges.py` para crear las categorias, o agregue habitaciones manualmente.")


# ------------------------------------------
# TAB 2: Add Rooms
# ------------------------------------------
with tab_add:
    st.subheader("➕ Agregar Nuevas Habitaciones")
    st.caption("Agregue habitaciones a una categoria existente")

    categories = get_all_categories()

    if categories:
        with st.form("add_rooms_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                # Category selector with price info
                category_options = {
                    f"{c['name']} ({c['base_price']:,.0f} Gs/noche)": c
                    for c in categories
                }
                selected_cat_label = st.selectbox(
                    "Categoria *",
                    options=list(category_options.keys()),
                    help="Seleccione la categoria para las nuevas habitaciones"
                )

                quantity = st.number_input(
                    "Cantidad de Habitaciones *",
                    min_value=1,
                    max_value=20,
                    value=1,
                    help="Cuantas habitaciones desea agregar"
                )

            with col2:
                floor = st.selectbox(
                    "Piso *",
                    options=[1, 2],
                    help="Piso donde se ubican las habitaciones"
                )

                # Show current count
                selected_cat = category_options[selected_cat_label]
                current_count = get_room_count_by_category(selected_cat['id'])
                st.info(f"📊 Habitaciones actuales en esta categoria: **{current_count}**")

            # Bed configuration display
            import json as _json
            bed_config = selected_cat.get('bed_configuration', '[]')
            max_cap = selected_cat.get('max_capacity', 0)
            description = selected_cat.get('description', '')
            try:
                beds = _json.loads(bed_config) if bed_config else []
                bed_str = ", ".join(f"{b['qty']} {b['type']}" for b in beds) if beds else "No configurado"
            except Exception:
                bed_str = "No configurado"

            st.markdown(f"""
> **{selected_cat['name']}**
> {description}
>
> 👥 max {max_cap} pers. • 🛏️ {bed_str}
""")

            st.divider()

            # Preview
            st.markdown("**Vista previa de codigos a generar:**")
            words = selected_cat['name'].split()[:2]
            prefix = ''.join(word[0].upper() for word in words if word)
            preview_codes = [f"{prefix}-{current_count + i + 1:02d}" for i in range(min(quantity, 5))]
            if quantity > 5:
                preview_codes.append("...")
            st.code(", ".join(preview_codes))

            submitted = st.form_submit_button("➕ Crear Habitaciones", type="primary", width="stretch")

            if submitted:
                success, message = create_rooms(
                    selected_cat['id'],
                    quantity,
                    floor,
                    selected_cat['name']
                )
                if success:
                    st.success(f"✅ {message}")
                    st.balloons()
                else:
                    st.error(f"❌ Error: {message}")
    else:
        st.warning("No hay categorias de habitacion configuradas.")
        st.info("💡 Ejecute primero `seed_monges.py` para crear las categorias.")


# ------------------------------------------
# TAB 3: Manage Rooms
# ------------------------------------------
with tab_manage:
    st.subheader("🔧 Gestionar Habitaciones")

    rooms = get_all_rooms()

    if rooms:
        # Room selector
        room_options = {
            f"{r['internal_code']} - {r['category_name']} (Piso {r['floor']})": r
            for r in rooms
        }

        selected_room_label = st.selectbox(
            "Seleccionar Habitacion",
            options=list(room_options.keys()),
            key="manage_room_select"
        )

        selected_room = room_options[selected_room_label]

        # Quick status info
        current_status = selected_room['status']
        status_emoji = {'available': '🟢', 'occupied': '🔴', 'maintenance': '🟠', 'cleaning': '🔵', 'out_of_service': '⚫'}.get(current_status, '⚪')
        st.info(f"Estado actual: {status_emoji} **{ROOM_STATUSES.get(current_status, current_status)}**")

        # Quick action buttons
        st.markdown("#### Acciones Rapidas")
        qcol1, qcol2, qcol3, qcol4 = st.columns(4)
        with qcol1:
            if st.button("🟢 Disponible", key="quick_available", width="stretch", disabled=(current_status == "available")):
                success, msg = update_room_status(selected_room['id'], "available")
                if success:
                    st.rerun()
        with qcol2:
            if st.button("🔵 Limpieza", key="quick_cleaning", width="stretch", disabled=(current_status == "cleaning")):
                success, msg = update_room_status(selected_room['id'], "cleaning")
                if success:
                    st.rerun()
        with qcol3:
            if st.button("🟠 Mantenimiento", key="quick_maint", width="stretch", disabled=(current_status == "maintenance")):
                success, msg = update_room_status(selected_room['id'], "maintenance")
                if success:
                    st.rerun()
        with qcol4:
            if st.button("⚫ Fuera de Servicio", key="quick_oos", width="stretch", disabled=(current_status == "out_of_service")):
                success, msg = update_room_status(selected_room['id'], "out_of_service")
                if success:
                    st.rerun()

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Cambiar Estado (con motivo)")

            with st.form("change_status_form"):
                st.caption("Use este formulario si necesita registrar un motivo del cambio")

                new_status = st.selectbox(
                    "Nuevo Estado",
                    options=list(ROOM_STATUSES.keys()),
                    format_func=lambda x: ROOM_STATUSES[x],
                    index=list(ROOM_STATUSES.keys()).index(current_status) if current_status in ROOM_STATUSES else 0
                )

                reason = st.text_input(
                    "Motivo del cambio",
                    placeholder="Ej: Reparacion de aire acondicionado",
                    help="Opcional - se registra en el historial"
                )

                if st.form_submit_button("💾 Guardar Estado", width="stretch"):
                    if new_status != current_status:
                        success, message = update_room_status(selected_room['id'], new_status, reason)
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                    else:
                        st.info("El estado no ha cambiado")

        with col2:
            st.markdown("### Activar / Desactivar")

            is_active = selected_room['active']

            if is_active:
                st.success("🟢 Esta habitacion esta **ACTIVA**")
                if st.button("⛔ Desactivar Habitacion", type="secondary", width="stretch"):
                    success, message = toggle_room_active(selected_room['id'], False)
                    if success:
                        st.warning(f"⚠️ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
            else:
                st.warning("⚫ Esta habitacion esta **INACTIVA**")
                if st.button("✅ Activar Habitacion", type="primary", width="stretch"):
                    success, message = toggle_room_active(selected_room['id'], True)
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")

            st.markdown("---")
            st.markdown("### Eliminar Habitacion")
            st.warning("⚠️ Esta accion es permanente")

            confirm_delete = st.checkbox("Confirmo que deseo eliminar esta habitacion", key="confirm_delete")

            if st.button("🗑️ Eliminar", type="secondary", disabled=not confirm_delete, width="stretch"):
                success, message = delete_room(selected_room['id'])
                if success:
                    st.success(f"✅ {message}")
                    st.rerun()
                else:
                    st.error(f"❌ {message}")

        # ------------------------------------------
        # Historial de cambios de estado (Feature 3 — RoomStatusLog)
        # ------------------------------------------
        st.markdown("---")
        with st.expander("📋 Historial de cambios de estado", expanded=False):
            try:
                resp = _s.get(
                    f"{API_BASE_URL}/rooms/{selected_room['id']}/status-log?limit=50",
                    headers=get_auth_headers(),
                    timeout=5
                )
                if resp.status_code == 200:
                    entries = resp.json()
                    if not entries:
                        st.info("Sin cambios registrados para esta habitación.")
                    else:
                        history_df = pd.DataFrame([
                            {
                                "Fecha": datetime.fromisoformat(e["changed_at"]).strftime("%Y-%m-%d %H:%M"),
                                "Estado anterior": ROOM_STATUSES.get(e["previous_status"], e["previous_status"] or "—"),
                                "Estado nuevo": ROOM_STATUSES.get(e["new_status"], e["new_status"]),
                                "Usuario": e["changed_by"] or "—",
                                "Motivo": e["reason"] or "—",
                            }
                            for e in entries
                        ])
                        st.dataframe(history_df, hide_index=True, width="stretch")
                        st.caption(f"Mostrando los últimos {len(entries)} cambios.")
                else:
                    st.warning(f"No se pudo cargar el historial (HTTP {resp.status_code}).")
            except Exception as e:
                st.error(f"Error consultando historial: {e}")
    else:
        st.info("No hay habitaciones para gestionar")


# ------------------------------------------
# TAB 4: Summary
# ------------------------------------------
with tab_summary:
    st.subheader("📊 Resumen por Categoria")

    if st.button("🔄 Actualizar Resumen", key="refresh_summary"):
        st.rerun()

    stats = get_room_statistics()

    if stats:
        # Create summary table
        summary_data = []
        total_rooms = 0
        total_available = 0
        total_occupied = 0

        for s in stats:
            total_rooms += s['total_rooms'] or 0
            total_available += s['available'] or 0
            total_occupied += s['occupied'] or 0

            summary_data.append({
                "Categoria": s['category_name'],
                "Precio Base": f"{s['base_price']:,.0f} Gs" if s['base_price'] else "—",
                "Total": s['total_rooms'] or 0,
                "Activas": s['active_rooms'] or 0,
                "🟢 Disponibles": s['available'] or 0,
                "🔴 Ocupadas": s['occupied'] or 0,
                "🟠 Mantenimiento": s['maintenance'] or 0,
                "🔵 Limpieza": s['cleaning'] or 0,
            })

        st.dataframe(
            summary_data,
            width="stretch",
            hide_index=True
        )

        st.divider()

        # Totals
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📊 Total Habitaciones", total_rooms)
        col2.metric("🟢 Disponibles", total_available)
        col3.metric("🔴 Ocupadas", total_occupied)

        if total_rooms > 0:
            occupancy = (total_occupied / total_rooms) * 100
            col4.metric("📈 Ocupacion", f"{occupancy:.1f}%")
        else:
            col4.metric("📈 Ocupacion", "0%")

        # Chart
        if total_rooms > 0:
            st.markdown("### Distribucion por Categoria")
            chart_data = pd.DataFrame([
                {"Categoria": s['category_name'], "Habitaciones": s['total_rooms'] or 0}
                for s in stats
            ])
            st.bar_chart(chart_data.set_index("Categoria"))

        # Download buttons for summary
        st.divider()
        dl_summary = []
        for s in stats:
            dl_summary.append({
                "Categoria": s['category_name'],
                "Precio Base": s['base_price'] or 0,
                "Total": s['total_rooms'] or 0,
                "Activas": s['active_rooms'] or 0,
                "Disponibles": s['available'] or 0,
                "Ocupadas": s['occupied'] or 0,
                "Mantenimiento": s['maintenance'] or 0,
                "Limpieza": s['cleaning'] or 0,
            })
        dl_summary.append({
            "Categoria": "TOTAL",
            "Precio Base": "",
            "Total": total_rooms,
            "Activas": sum(s['active_rooms'] or 0 for s in stats),
            "Disponibles": total_available,
            "Ocupadas": total_occupied,
            "Mantenimiento": sum(s['maintenance'] or 0 for s in stats),
            "Limpieza": sum(s['cleaning'] or 0 for s in stats),
        })
        sc1, sc2 = st.columns(2)
        sc_csv = io.StringIO()
        sc_writer = csv.DictWriter(sc_csv, fieldnames=list(dl_summary[0].keys()))
        sc_writer.writeheader()
        for row in dl_summary:
            sc_writer.writerow(row)
        sc1.download_button(
            "📥 Descargar CSV (Resumen)",
            data=sc_csv.getvalue(),
            file_name=f"resumen_categorias_{date.today()}.csv",
            mime="text/csv",
            width="stretch"
        )
        sc_df = pd.DataFrame(dl_summary)
        sc_buf = io.BytesIO()
        with pd.ExcelWriter(sc_buf, engine="openpyxl") as writer:
            sc_df.to_excel(writer, index=False, sheet_name="Resumen")
        sc2.download_button(
            "📥 Descargar Excel (Resumen)",
            data=sc_buf.getvalue(),
            file_name=f"resumen_categorias_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )
    else:
        st.info("No hay datos de habitaciones disponibles")
        st.warning("💡 Ejecute las migraciones y el seed para crear el inventario inicial:")
        st.code("""
python scripts/run_migrations.py
python scripts/seed_monges.py
        """)

    # Revenue Heatmap
    st.divider()
    st.markdown("### 💰 Mapa de Ingresos por Habitacion")

    rev_year = st.selectbox(
        "Año",
        options=list(range(date.today().year - 1, date.today().year + 2)),
        index=1,
        key="revenue_year"
    )

    try:
        rev_resp = _s.get(
            f"{API_BASE_URL}/reservations/revenue-matrix",
            params={"year": rev_year},
            headers=get_auth_headers(),
            timeout=15
        )
        if rev_resp.ok:
            rev_data = rev_resp.json()
            rev_rooms = rev_data.get("rooms", [])
            rev_matrix = rev_data.get("matrix", {})

            if rev_rooms:
                from helpers.constants import MESES_ES

                all_vals = [
                    v for room_data in rev_matrix.values()
                    for v in room_data.values() if v > 0
                ]
                max_rev = max(all_vals) if all_vals else 1

                import streamlit.components.v1 as components

                hm_css = """
                <style>
                    .rev-grid { font-family: sans-serif; font-size: 11px; border-collapse: collapse; width: 100%; }
                    .rev-grid th, .rev-grid td { border: 1px solid #e5e7eb; padding: 4px 6px; text-align: center; }
                    .rev-grid th { background: #f9fafb; color: #6b7280; font-weight: 600; }
                    .rev-grid td:first-child { font-weight: 600; text-align: left; background: #f9fafb; }
                </style>
                """

                hm_header = '<tr><th>Habitacion</th>'
                for m in range(1, 13):
                    hm_header += f'<th>{MESES_ES[m-1][:3]}</th>'
                hm_header += '<th>Total</th></tr>'

                hm_body = ''
                for room in rev_rooms:
                    code = room["code"]
                    room_rev = rev_matrix.get(code, {})
                    hm_body += f'<tr><td>{code}</td>'
                    row_total = 0
                    for m in range(1, 13):
                        val = room_rev.get(str(m), 0)
                        row_total += val
                        if val > 0:
                            intensity = min(val / max_rev, 1.0)
                            r_c = int(220 - intensity * 100)
                            g_c = int(252 - intensity * 50)
                            b_c = int(231 - intensity * 100)
                            bg = f"rgb({r_c},{g_c},{b_c})"
                            hm_body += f'<td style="background:{bg}" title="{val:,.0f} Gs">{val/1000:.0f}k</td>'
                        else:
                            hm_body += '<td style="color:#d1d5db">—</td>'
                    hm_body += f'<td style="font-weight:bold;background:#f0fdf4">{row_total/1000:.0f}k</td></tr>'

                hm_html = f"""
                <div style="overflow-x:auto;border:1px solid #e5e7eb;border-radius:8px">
                    {hm_css}
                    <table class="rev-grid">
                        <thead>{hm_header}</thead>
                        <tbody>{hm_body}</tbody>
                    </table>
                </div>
                """

                height = 40 + len(rev_rooms) * 28 + 20
                components.html(hm_html, height=height, scrolling=True)

                # Excel download for revenue heatmap
                hm_rows = []
                for room in rev_rooms:
                    code = room["code"]
                    room_rev = rev_matrix.get(code, {})
                    row = {"Habitacion": code}
                    row_total = 0
                    for m in range(1, 13):
                        val = room_rev.get(str(m), 0)
                        row_total += val
                        row[MESES_ES[m-1][:3]] = val
                    row["Total"] = row_total
                    hm_rows.append(row)

                hm_df = pd.DataFrame(hm_rows)
                hm_buf = io.BytesIO()
                with pd.ExcelWriter(hm_buf, engine="openpyxl") as writer:
                    hm_df.to_excel(writer, index=False, sheet_name="Ingresos")
                st.download_button(
                    "📥 Descargar Excel (Mapa de Ingresos)",
                    data=hm_buf.getvalue(),
                    file_name=f"ingresos_habitacion_{rev_year}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )
            else:
                st.info("Sin habitaciones registradas")
        else:
            st.warning("No se pudo cargar el mapa de ingresos")
    except Exception as e:
        st.error(f"Error: {e}")



# ------------------------------------------
# TAB 5: Ficha Mensual
# ------------------------------------------
with tab_ficha:
    from helpers.constants import MESES_ES
    from components.calendar_render import render_monthly_room_grid
    from calendar import monthrange

    st.subheader("📅 Ficha Mensual de Habitaciones")

    today = date.today()
    col_year, col_month, col_refresh = st.columns([1, 2, 1])

    with col_year:
        ficha_year = st.selectbox(
            "Año",
            options=list(range(today.year - 1, today.year + 2)),
            index=1,
            key="ficha_year"
        )
    with col_month:
        ficha_month = st.selectbox(
            "Mes",
            options=list(range(1, 13)),
            format_func=lambda x: MESES_ES[x - 1],
            index=today.month - 1,
            key="ficha_month"
        )
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄 Actualizar", key="refresh_ficha"):
            st.rerun()

    try:
        resp = _s.get(
            f"{API_BASE_URL}/reservations/monthly-view",
            params={"year": ficha_year, "month": ficha_month},
            headers=get_auth_headers(),
            timeout=15
        )
        if resp.ok:
            grid_data = resp.json()
            render_monthly_room_grid(grid_data, ficha_year, ficha_month)
        else:
            st.error(f"Error al cargar ficha mensual: {resp.status_code}")
    except Exception as e:
        st.error(f"Error de conexion: {e}")

    st.divider()
    st.subheader("📊 Indicadores del Mes")

    _, num_days = monthrange(ficha_year, ficha_month)
    month_start = date(ficha_year, ficha_month, 1)
    month_end = date(ficha_year, ficha_month, num_days)

    source_data = None
    trend_data = None
    parking_data = None
    month_revenue = 0
    month_reservations = 0

    try:
        r1 = _s.get(
            f"{API_BASE_URL}/reservations/source-stats",
            params={"start_date": str(month_start), "end_date": str(month_end)},
            headers=get_auth_headers(),
            timeout=10
        )
        if r1.ok:
            source_data = r1.json()
            for s in source_data:
                month_revenue += s.get("revenue", 0)
                month_reservations += s.get("count", 0)
    except Exception:
        pass

    try:
        r2 = _s.get(
            f"{API_BASE_URL}/calendar/occupancy-trend",
            params={"year": ficha_year, "month": ficha_month},
            timeout=10
        )
        if r2.ok:
            trend_data = r2.json()
    except Exception:
        pass

    try:
        r3 = _s.get(
            f"{API_BASE_URL}/reservations/parking-usage",
            params={"start_date": str(month_start), "end_date": str(month_end)},
            headers=get_auth_headers(),
            timeout=10
        )
        if r3.ok:
            parking_data = r3.json()
    except Exception:
        pass

    # Revenue summary metrics
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("💰 Ingresos del Mes", f"{month_revenue:,.0f} Gs")
    m_col2.metric("📋 Total Reservas", month_reservations)
    m_col3.metric("📈 Promedio/Reserva", f"{month_revenue / month_reservations:,.0f} Gs" if month_reservations > 0 else "—")

    st.divider()
    col_src, col_trend = st.columns(2)

    with col_src:
        st.markdown("#### Reservas por Canal")
        if source_data:
            src_df = pd.DataFrame(source_data)
            if not src_df.empty:
                st.bar_chart(src_df.set_index("source")["count"])
                total_res = src_df["count"].sum()
                total_rev = src_df["revenue"].sum()
                c1, c2 = st.columns(2)
                c1.metric("Total Reservas", int(total_res))
                c2.metric("Ingresos", f"{total_rev:,.0f} Gs")
            else:
                st.info("Sin reservas en este periodo")
        else:
            st.info("Sin datos disponibles")

    with col_trend:
        st.markdown("#### Tendencia de Ocupacion")
        if trend_data:
            trend_df = pd.DataFrame(trend_data)
            if not trend_df.empty:
                trend_df = trend_df.rename(columns={"date": "Fecha", "occupancy_pct": "Ocupacion %"})
                st.area_chart(trend_df.set_index("Fecha")["Ocupacion %"])
                avg_occ = trend_df["Ocupacion %"].mean()
                max_occ = trend_df["Ocupacion %"].max()
                c1, c2 = st.columns(2)
                c1.metric("Promedio", f"{avg_occ:.1f}%")
                c2.metric("Maximo", f"{max_occ:.1f}%")
            else:
                st.info("Sin datos de ocupacion")
        else:
            st.info("Sin datos disponibles")

    st.markdown("#### 🚗 Uso de Estacionamiento")
    if parking_data:
        park_df = pd.DataFrame(parking_data)
        if not park_df.empty:
            display_days = park_df
            for _, row in display_days.iterrows():
                pct = row.get("pct", 0)
                cap = row.get("capacity", 0)
                used = row.get("used", 0)
                label = row.get("date", "")
                st.markdown(f"**{label}** — {used}/{cap} lugares")
                st.progress(min(pct / 100, 1.0))
        else:
            st.info("Sin datos de estacionamiento")
    else:
        st.info("Sin datos disponibles")


# ------------------------------------------
# TAB 6: Resumen por Habitacion
# ------------------------------------------
with tab_room_detail:
    from calendar import monthrange as _monthrange

    st.subheader("🏠 Resumen por Habitacion")

    all_rooms = get_all_rooms()

    if all_rooms:
        room_labels = {f"{r['internal_code']} - {r['category_name']}": r['internal_code'] for r in all_rooms}
        room_options_list = ["📊 Todas las habitaciones"] + list(room_labels.keys())

        selected_room_label_rd = st.selectbox(
            "Seleccionar Habitacion",
            options=room_options_list,
            key="room_detail_select"
        )

        is_all_rooms = selected_room_label_rd == "📊 Todas las habitaciones"
        selected_room_code = None if is_all_rooms else room_labels[selected_room_label_rd]

        col_y, col_m, col_period = st.columns([1, 2, 2])

        with col_y:
            rd_year = st.selectbox(
                "Año",
                options=list(range(date.today().year - 1, date.today().year + 2)),
                index=1,
                key="rd_year"
            )
        with col_m:
            from helpers.constants import MESES_ES as _MESES
            rd_month = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                format_func=lambda x: _MESES[x - 1],
                index=date.today().month - 1,
                key="rd_month"
            )
        with col_period:
            rd_period = st.radio(
                "Periodo",
                options=["Mensual", "Semanal", "Diario"],
                horizontal=True,
                key="rd_period"
            )

        _, rd_num_days = _monthrange(rd_year, rd_month)

        if rd_period == "Mensual":
            rd_start = date(rd_year, rd_month, 1)
            rd_end = date(rd_year, rd_month, rd_num_days)
        elif rd_period == "Semanal":
            _today = date.today()
            rd_start = _today - timedelta(days=_today.weekday())  # Monday
            rd_end = rd_start + timedelta(days=6)  # Sunday
        else:  # Diario
            rd_start = date.today()
            rd_end = date.today()

        st.caption(f"Periodo: {rd_start.isoformat()} a {rd_end.isoformat()}")

        try:
            params = {"start_date": str(rd_start), "end_date": str(rd_end)}
            if selected_room_code:
                params["room_id"] = selected_room_code

            report_resp = _s.get(
                f"{API_BASE_URL}/reservations/room-report",
                params=params,
                headers=get_auth_headers(),
                timeout=15
            )

            if report_resp.ok:
                report = report_resp.json()
                report_rooms = report.get("rooms", [])

                if is_all_rooms:
                    st.markdown("### 📊 Resumen General de Todas las Habitaciones")

                    if report_rooms:
                        summary_rows = []
                        for rr in report_rooms:
                            rm = rr["room"]
                            s = rr["summary"]
                            summary_rows.append({
                                "Codigo": rm["code"],
                                "Categoria": rm["category"],
                                "Piso": rm["floor"],
                                "Noches Ocupadas": s["total_nights"],
                                "Ingresos (Gs)": f"{s['total_revenue']:,.0f}",
                                "% Ocupacion": f"{s['occupancy_pct']:.1f}%",
                                "Tarifa Promedio": f"{s['avg_nightly_rate']:,.0f}",
                                "Reservas": s["reservation_count"],
                            })

                        st.dataframe(summary_rows, width="stretch", hide_index=True)

                        total_nights_all = sum(rr["summary"]["total_nights"] for rr in report_rooms)
                        total_revenue_all = sum(rr["summary"]["total_revenue"] for rr in report_rooms)
                        avg_occ_all = sum(rr["summary"]["occupancy_pct"] for rr in report_rooms) / len(report_rooms) if report_rooms else 0

                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total Noches Ocupadas", total_nights_all)
                        c2.metric("Ingresos Totales", f"{total_revenue_all:,.0f} Gs")
                        c3.metric("Ocupacion Promedio", f"{avg_occ_all:.1f}%")

                        # Build data for downloads
                        dl_rows = []
                        for rr in report_rooms:
                            rm = rr["room"]
                            s = rr["summary"]
                            dl_rows.append({
                                "Codigo": rm["code"],
                                "Categoria": rm["category"],
                                "Piso": rm["floor"],
                                "Noches Ocupadas": s["total_nights"],
                                "Ingresos (Gs)": s["total_revenue"],
                                "% Ocupacion": round(s["occupancy_pct"], 1),
                                "Tarifa Promedio (Gs)": round(s["avg_nightly_rate"]),
                                "Reservas": s["reservation_count"],
                            })
                        # Add totals row
                        dl_rows.append({
                            "Codigo": "TOTAL",
                            "Categoria": "",
                            "Piso": "",
                            "Noches Ocupadas": total_nights_all,
                            "Ingresos (Gs)": total_revenue_all,
                            "% Ocupacion": round(avg_occ_all, 1),
                            "Tarifa Promedio (Gs)": "",
                            "Reservas": sum(rr["summary"]["reservation_count"] for rr in report_rooms),
                        })

                        dl_col1, dl_col2 = st.columns(2)

                        # CSV download
                        csv_buf = io.StringIO()
                        writer = csv.DictWriter(csv_buf, fieldnames=list(dl_rows[0].keys()))
                        writer.writeheader()
                        for row in dl_rows:
                            writer.writerow(row)
                        dl_col1.download_button(
                            "📥 Descargar CSV",
                            data=csv_buf.getvalue(),
                            file_name=f"resumen_habitaciones_{rd_start}_{rd_end}.csv",
                            mime="text/csv",
                            width="stretch"
                        )

                        # Excel download
                        xl_df = pd.DataFrame(dl_rows)
                        xl_buf = io.BytesIO()
                        with pd.ExcelWriter(xl_buf, engine="openpyxl") as writer:
                            xl_df.to_excel(writer, index=False, sheet_name="Resumen")
                        dl_col2.download_button(
                            "📥 Descargar Excel",
                            data=xl_buf.getvalue(),
                            file_name=f"resumen_habitaciones_{rd_start}_{rd_end}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            width="stretch"
                        )
                    else:
                        st.info("Sin datos para el periodo seleccionado")

                else:
                    if report_rooms:
                        room_data = report_rooms[0]
                        rm = room_data["room"]
                        s = room_data["summary"]
                        reservations_list = room_data["reservations"]

                        st.markdown(f"### Habitacion {rm['code']} — {rm['category']} (Piso {rm['floor']})")

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("🛏️ Noches Ocupadas", s["total_nights"])
                        c2.metric("💰 Ingresos", f"{s['total_revenue']:,.0f} Gs")
                        c3.metric("📈 % Ocupacion", f"{s['occupancy_pct']:.1f}%")
                        c4.metric("💵 Tarifa Promedio", f"{s['avg_nightly_rate']:,.0f} Gs")

                        if reservations_list:
                            st.markdown("#### Detalle de Reservas")
                            table_data = []
                            for res in reservations_list:
                                table_data.append({
                                    "Huesped": res["guest_name"],
                                    "Check-in": res["check_in"],
                                    "Check-out": res["check_out"],
                                    "Noches": res["nights"],
                                    "Precio (Gs)": f"{res['price']:,.0f}",
                                    "Canal": res["source"],
                                    "Estado": res["status"],
                                })
                            st.dataframe(table_data, width="stretch", hide_index=True)

                            csv_buf = io.StringIO()
                            writer = csv.DictWriter(csv_buf, fieldnames=["Huesped", "Check-in", "Check-out", "Noches", "Precio", "Canal", "Estado"])
                            writer.writeheader()
                            for res in reservations_list:
                                writer.writerow({
                                    "Huesped": res["guest_name"],
                                    "Check-in": res["check_in"],
                                    "Check-out": res["check_out"],
                                    "Noches": res["nights"],
                                    "Precio": res["price"],
                                    "Canal": res["source"],
                                    "Estado": res["status"],
                                })
                            st.download_button(
                                f"📥 Descargar CSV ({rm['code']})",
                                data=csv_buf.getvalue(),
                                file_name=f"resumen_{rm['code']}_{rd_start}_{rd_end}.csv",
                                mime="text/csv",
                                width="stretch"
                            )
                        else:
                            st.info("Sin reservas en este periodo para esta habitacion")
                    else:
                        st.info("Sin datos para esta habitacion")
            else:
                st.error(f"Error al cargar reporte: {report_resp.status_code}")
        except Exception as e:
            st.error(f"Error de conexion: {e}")
    else:
        st.warning("No hay habitaciones registradas")


# ==========================================
# FOOTER
# ==========================================
st.divider()

st.caption("🏠 Administracion de Habitaciones - Los cambios se registran en el historial del sistema")
st.caption("💡 Use esta interfaz para ajustar las cantidades de habitaciones antes de la demostracion")
