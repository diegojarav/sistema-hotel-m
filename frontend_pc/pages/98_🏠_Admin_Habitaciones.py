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
from datetime import datetime
import pandas as pd

# Import logging
from logging_config import get_logger

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
    token = st.session_state.get('access_token')
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def get_all_categories():
    """Fetch all room categories via API."""
    try:
        response = requests.get(f"{API_BASE_URL}/rooms/categories", timeout=10)
        if response.ok:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return []


def get_all_rooms():
    """Fetch all rooms with category information via API."""
    try:
        response = requests.get(f"{API_BASE_URL}/rooms", timeout=10)
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
        response = requests.get(
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
        response = requests.post(
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
        response = requests.patch(
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
        response = requests.patch(
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
        response = requests.delete(
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
        response = requests.get(
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

tab_inventory, tab_add, tab_manage, tab_summary = st.tabs([
    "📋 Inventario",
    "➕ Agregar Habitaciones",
    "🔧 Gestionar Habitaciones",
    "📊 Resumen por Categoria"
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
                use_container_width=True,
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
                    options=[1, 2, 3, 4, 5],
                    help="Piso donde se ubican las habitaciones"
                )

                # Show current count
                selected_cat = category_options[selected_cat_label]
                current_count = get_room_count_by_category(selected_cat['id'])
                st.info(f"📊 Habitaciones actuales en esta categoria: **{current_count}**")

            st.divider()

            # Preview
            st.markdown("**Vista previa de codigos a generar:**")
            words = selected_cat['name'].split()[:2]
            prefix = ''.join(word[0].upper() for word in words if word)
            preview_codes = [f"{prefix}-{current_count + i + 1:02d}" for i in range(min(quantity, 5))]
            if quantity > 5:
                preview_codes.append("...")
            st.code(", ".join(preview_codes))

            submitted = st.form_submit_button("➕ Crear Habitaciones", type="primary", use_container_width=True)

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

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Cambiar Estado")

            with st.form("change_status_form"):
                current_status = selected_room['status']
                st.info(f"Estado actual: **{ROOM_STATUSES.get(current_status, current_status)}**")

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

                if st.form_submit_button("💾 Guardar Estado", use_container_width=True):
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
                if st.button("⛔ Desactivar Habitacion", type="secondary", use_container_width=True):
                    success, message = toggle_room_active(selected_room['id'], False)
                    if success:
                        st.warning(f"⚠️ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
            else:
                st.warning("⚫ Esta habitacion esta **INACTIVA**")
                if st.button("✅ Activar Habitacion", type="primary", use_container_width=True):
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

            if st.button("🗑️ Eliminar", type="secondary", disabled=not confirm_delete, use_container_width=True):
                success, message = delete_room(selected_room['id'])
                if success:
                    st.success(f"✅ {message}")
                    st.rerun()
                else:
                    st.error(f"❌ {message}")
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
            use_container_width=True,
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
    else:
        st.info("No hay datos de habitaciones disponibles")
        st.warning("💡 Ejecute el script de migracion y seed para crear el inventario inicial:")
        st.code("""
python scripts/migrate_monges.py
python scripts/seed_monges.py
        """)


# ==========================================
# FOOTER
# ==========================================
st.divider()

st.caption("🏠 Administracion de Habitaciones - Los cambios se registran en el historial del sistema")
st.caption("💡 Use esta interfaz para ajustar las cantidades de habitaciones antes de la demostracion")
