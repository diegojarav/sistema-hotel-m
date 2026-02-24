import streamlit as st
import sys
import os

# Add backend to path for direct imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))

from services import SettingsService, AuthService
from database import SessionLocal

st.set_page_config(page_title="Configuración", page_icon="🔧", layout="centered")

# ==========================================
# AUTH CHECK
# ==========================================
if 'user' not in st.session_state or not st.session_state.user:
    st.error("⚠️ Acceso Restringido. Inicie sesión.")
    st.stop()

if st.session_state.user.role not in ['admin', 'supervisor']:
    st.error("🛑 No tiene permisos para ver esta página.")
    st.stop()

st.title("🔧 Configuración del Sistema")
st.markdown("---")

# ==========================================
# PARKING CONFIGURATION
# ==========================================
st.subheader("🚗 Estacionamiento")

with SessionLocal() as db:
    current_capacity = SettingsService.get_parking_capacity(db)
    
    with st.form("parking_config_form"):
        new_capacity = st.number_input(
            "Capacidad Total de Estacionamiento", 
            min_value=0, 
            max_value=100, 
            value=current_capacity,
            help="Número máximo de vehículos permitidos simultáneamente."
        )
        
        submitted = st.form_submit_button("Guardar Cambios")
        
        if submitted:
            success = SettingsService.set_parking_capacity(db, int(new_capacity))
            if success:
                st.success(f"✅ Capacidad actualizada a {new_capacity} vehículos.")
                # Force reload to show new value if logic needed, though session handles it
            else:
                st.error("❌ Error al guardar la configuración.")

st.markdown("---")

# ==========================================
# iCAL SYNC CONFIGURATION
# ==========================================
st.subheader("📅 Sincronización iCal (Booking.com / Airbnb)")

from api_client import get_session

_s = get_session()
API_BASE_URL = "http://localhost:8000/api/v1"

def _get_auth_headers():
    token = st.session_state.get("api_token", "")
    return {"Authorization": f"Bearer {token}"}

# Fetch current feeds
try:
    feeds_resp = _s.get(f"{API_BASE_URL}/ical/feeds", headers=_get_auth_headers(), timeout=5)
    feeds = feeds_resp.json() if feeds_resp.ok else []
except Exception:
    feeds = []
    st.warning("No se pudo conectar con la API para obtener feeds iCal.")

# Display existing feeds
if feeds:
    st.markdown("**Feeds configurados:**")
    for feed in feeds:
        col_info, col_sync, col_del = st.columns([4, 1, 1])
        with col_info:
            status_icon = "🟢" if feed.get("sync_enabled") else "🔴"
            last_sync = feed.get("last_synced_at", "Nunca")
            st.markdown(
                f"{status_icon} **{feed['room_label']}** — {feed['source']}  \n"
                f"<small>Última sync: {last_sync or 'Nunca'}</small>",
                unsafe_allow_html=True
            )
        with col_sync:
            if st.button("🔄", key=f"sync_{feed['id']}", help="Sincronizar ahora"):
                try:
                    r = _s.post(
                        f"{API_BASE_URL}/ical/feeds/{feed['id']}/sync",
                        headers=_get_auth_headers(), timeout=60
                    )
                    if r.ok:
                        result = r.json()
                        st.success(f"Creadas: {result['created']}, Actualizadas: {result['updated']}")
                    else:
                        st.error("Error al sincronizar")
                except Exception as e:
                    st.error(f"Error: {e}")
        with col_del:
            if st.button("🗑️", key=f"del_{feed['id']}", help="Eliminar feed"):
                try:
                    r = _s.delete(
                        f"{API_BASE_URL}/ical/feeds/{feed['id']}",
                        headers=_get_auth_headers(), timeout=5
                    )
                    if r.status_code == 204:
                        st.success("Feed eliminado")
                        st.rerun()
                    else:
                        st.error("Error al eliminar")
                except Exception as e:
                    st.error(f"Error: {e}")
else:
    st.info("No hay feeds iCal configurados. Agregue uno abajo.")

# Add new feed form
st.markdown("**Agregar nuevo feed:**")
with st.form("add_ical_feed"):
    # Get rooms list
    try:
        rooms_resp = _s.get(f"{API_BASE_URL}/rooms", headers=_get_auth_headers(), timeout=5)
        rooms_data = rooms_resp.json() if rooms_resp.ok else []
    except Exception:
        rooms_data = []

    room_options = {r.get("internal_code", r["id"]): r["id"] for r in rooms_data}
    selected_room_label = st.selectbox("Habitación", options=list(room_options.keys()))
    source = st.selectbox("Plataforma", options=["Booking.com", "Airbnb"])
    ical_url = st.text_input("URL del Calendario iCal", placeholder="https://...")

    if st.form_submit_button("Agregar Feed"):
        if ical_url and selected_room_label:
            room_id = room_options[selected_room_label]
            try:
                r = _s.post(
                    f"{API_BASE_URL}/ical/feeds",
                    json={"room_id": room_id, "source": source, "ical_url": ical_url},
                    headers=_get_auth_headers(), timeout=5
                )
                if r.status_code == 201:
                    st.success(f"✅ Feed agregado para {selected_room_label} ({source})")
                    st.rerun()
                else:
                    st.error(f"Error: {r.text}")
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("Complete todos los campos.")

# Sync all button
st.markdown("---")
col_syncall, col_space = st.columns([1, 3])
with col_syncall:
    if st.button("🔄 Sincronizar Todos", type="primary"):
        try:
            r = _s.post(
                f"{API_BASE_URL}/ical/feeds/sync",
                headers=_get_auth_headers(), timeout=120
            )
            if r.ok:
                result = r.json()
                st.success(
                    f"✅ {result.get('feeds_synced', 0)} feeds sincronizados. "
                    f"Creadas: {result['created']}, Actualizadas: {result['updated']}"
                )
                if result.get("errors"):
                    st.warning(f"Errores: {len(result['errors'])}")
            else:
                st.error("Error al sincronizar")
        except Exception as e:
            st.error(f"Error: {e}")

# Export URLs section
st.markdown("---")
st.markdown("**URLs de Exportación** (para pegar en Booking.com / Airbnb):")
if rooms_data:
    for r in rooms_data:
        label = r.get("internal_code", r["id"])
        export_url = f"http://localhost:8000/api/v1/ical/export/{r['id']}.ics"
        st.code(f"{label}: {export_url}", language=None)
    st.code(f"Todos: http://localhost:8000/api/v1/ical/export/all.ics", language=None)
    st.caption("Reemplace 'localhost:8000' con su dominio de producción.")

st.markdown("---")
st.info("ℹ️ Los cambios afectan inmediatamente a las nuevas reservas. Los feeds iCal se sincronizan automáticamente cada 15 minutos.")
