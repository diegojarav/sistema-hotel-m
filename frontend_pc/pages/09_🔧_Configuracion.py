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
# CHANNEL MANAGER v2 (v1.5.0) — iCal feeds + reviews
# ==========================================
st.subheader("📅 Channel Manager — Sincronización iCal")
st.caption("Booking.com · Airbnb · Vrbo · Expedia · Custom")

from api_client import get_session

_s = get_session()
API_BASE_URL = "http://localhost:8000/api/v1"
SOURCES_v2 = ["Booking.com", "Airbnb", "Vrbo", "Expedia", "Custom"]


def _get_auth_headers():
    token = st.session_state.get("api_token", "")
    return {"Authorization": f"Bearer {token}"}


def _badge_emoji(badge: str) -> str:
    return {
        "healthy": "🟢",
        "warning": "🟡",
        "error": "🔴",
        "unknown": "⚪",
    }.get(badge, "⚪")


# Fetch current feeds (with v1.5.0 health fields)
try:
    feeds_resp = _s.get(f"{API_BASE_URL}/ical/feeds", headers=_get_auth_headers(), timeout=5)
    feeds = feeds_resp.json() if feeds_resp.ok else []
except Exception:
    feeds = []
    st.warning("No se pudo conectar con la API para obtener feeds iCal.")

# ---- Health summary banner ----
if feeds:
    n_total = len(feeds)
    n_error = sum(1 for f in feeds if f.get("health_badge") == "error")
    n_warn = sum(1 for f in feeds if f.get("health_badge") == "warning")
    n_healthy = sum(1 for f in feeds if f.get("health_badge") == "healthy")
    n_unknown = sum(1 for f in feeds if f.get("health_badge") == "unknown")
    cols = st.columns(4)
    cols[0].metric("🟢 Saludables", n_healthy)
    cols[1].metric("🟡 Advertencias", n_warn)
    cols[2].metric("🔴 Errores", n_error)
    cols[3].metric("⚪ Sin sincronizar", n_unknown)

# ---- Feed list ----
if feeds:
    st.markdown("**Feeds configurados:**")
    for feed in feeds:
        badge = feed.get("health_badge", "unknown")
        emoji = _badge_emoji(badge)
        status_icon = "🟢" if feed.get("sync_enabled") else "🔴 (deshabilitado)"
        last_sync = feed.get("last_synced_at") or "Nunca"
        last_attempt = feed.get("last_sync_attempted_at") or "—"
        consecutive = feed.get("consecutive_failures", 0)

        with st.expander(
            f"{emoji} {feed['room_label']} — {feed['source']}  ·  "
            f"última sync: {last_sync[:19].replace('T', ' ') if last_sync != 'Nunca' else 'Nunca'}"
        ):
            col_info, col_actions = st.columns([3, 2])
            with col_info:
                st.write(f"**Estado:** {feed.get('last_sync_status', 'NEVER')}")
                st.write(f"**Fallos consecutivos:** {consecutive}")
                st.write(f"**Último intento:** {last_attempt[:19].replace('T', ' ') if last_attempt != '—' else '—'}")
                if feed.get("last_sync_error"):
                    st.error(f"Último error: {feed['last_sync_error']}")
                st.caption(f"URL: `{feed.get('ical_url', '')}`")

            with col_actions:
                if st.button("🔄 Sincronizar ahora", key=f"sync_{feed['id']}"):
                    try:
                        r = _s.post(
                            f"{API_BASE_URL}/ical/feeds/{feed['id']}/sync",
                            headers=_get_auth_headers(), timeout=60
                        )
                        if r.ok:
                            result = r.json()
                            st.success(
                                f"OK — Creadas: {result.get('created', 0)}, "
                                f"Actualizadas: {result.get('updated', 0)}, "
                                f"Marcadas para revisión: {result.get('flagged_for_review', 0)}, "
                                f"Conflictos: {result.get('conflicts', 0)}"
                            )
                            st.rerun()
                        else:
                            st.error(f"Error al sincronizar: {r.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

                if st.button("📜 Ver historial", key=f"hist_{feed['id']}"):
                    st.session_state[f"_show_history_{feed['id']}"] = True

                if st.button("🗑️ Eliminar feed", key=f"del_{feed['id']}"):
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

            # History panel (toggleable)
            if st.session_state.get(f"_show_history_{feed['id']}"):
                st.markdown("---")
                st.markdown("**Historial (últimas 20 sincronizaciones)**")
                try:
                    logs_resp = _s.get(
                        f"{API_BASE_URL}/ical/feeds/{feed['id']}/logs?limit=20",
                        headers=_get_auth_headers(), timeout=10
                    )
                    if logs_resp.ok:
                        logs = logs_resp.json()
                        if logs:
                            import pandas as pd
                            df = pd.DataFrame([
                                {
                                    "Hora": (l["attempted_at"] or "")[:19].replace("T", " "),
                                    "Estado": l["status"],
                                    "Creadas": l["created_count"],
                                    "Actualizadas": l["updated_count"],
                                    "Marcadas": l["flagged_for_review_count"],
                                    "Conflictos": l["conflicts_detected"],
                                    "Duración (ms)": l["duration_ms"],
                                    "Error": (l.get("error_message") or "")[:80],
                                }
                                for l in logs
                            ])
                            st.dataframe(df, width="stretch", hide_index=True)
                        else:
                            st.info("Sin historial todavía.")
                    else:
                        st.error("No se pudo cargar el historial.")
                except Exception as e:
                    st.error(f"Error: {e}")
                if st.button("Cerrar historial", key=f"close_hist_{feed['id']}"):
                    st.session_state[f"_show_history_{feed['id']}"] = False
                    st.rerun()
else:
    st.info("No hay feeds iCal configurados. Agregue uno abajo.")

# Add new feed form (v1.5.0 expanded sources)
st.markdown("**Agregar nuevo feed:**")
with st.form("add_ical_feed"):
    try:
        rooms_resp = _s.get(f"{API_BASE_URL}/rooms", headers=_get_auth_headers(), timeout=5)
        rooms_data = rooms_resp.json() if rooms_resp.ok else []
    except Exception:
        rooms_data = []

    room_options = {r.get("internal_code", r["id"]): r["id"] for r in rooms_data}
    selected_room_label = st.selectbox("Habitación", options=list(room_options.keys()))
    source = st.selectbox("Plataforma", options=SOURCES_v2)
    ical_url = st.text_input("URL del Calendario iCal", placeholder="https://...")
    st.caption("Para 'Custom', usa cualquier URL .ics estándar.")

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
                    error_detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
                    st.error(f"Error: {error_detail}")
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("Complete todos los campos.")

# Sync all button
st.markdown("---")
col_syncall, col_space = st.columns([1, 3])
with col_syncall:
    if st.button("🔄 Sincronizar Todos los Feeds", type="primary"):
        try:
            r = _s.post(
                f"{API_BASE_URL}/ical/feeds/sync",
                headers=_get_auth_headers(), timeout=120
            )
            if r.ok:
                result = r.json()
                st.success(
                    f"✅ {result.get('feeds_synced', 0)} feeds sincronizados. "
                    f"Creadas: {result.get('created', 0)}, "
                    f"Actualizadas: {result.get('updated', 0)}, "
                    f"Marcadas para revisión: {result.get('flagged_for_review', 0)}, "
                    f"Conflictos: {result.get('conflicts', 0)}"
                )
                if result.get("errors"):
                    st.warning(f"⚠️ {len(result['errors'])} error(es) — ver historial por feed")
            else:
                st.error(f"Error al sincronizar: {r.text}")
        except Exception as e:
            st.error(f"Error: {e}")

# ==========================================
# Reservations needing review (v1.5.0)
# ==========================================
st.markdown("---")
st.subheader("⚠️ Reservas por revisar")
st.caption(
    "Reservas cuyo UID desapareció del feed OTA. Confirme con el huésped antes de cancelar."
)
try:
    review_resp = _s.get(
        f"{API_BASE_URL}/reservations/needs-review",
        headers=_get_auth_headers(), timeout=10
    )
    reviews = review_resp.json() if review_resp.ok else []
except Exception:
    reviews = []
    st.warning("No se pudo obtener la lista de reservas por revisar.")

if not reviews:
    st.success("✓ No hay reservas pendientes de revisión.")
else:
    for r in reviews:
        with st.expander(
            f"⚠️ Reserva #{r['id']} — {r['guest_name']} ({r['source']}) "
            f"· {r.get('check_in_date', '')} · {r['stay_days']} noche(s)"
        ):
            st.write(f"**Estado actual:** {r['status']}")
            st.write(f"**Razón:** {r.get('review_reason', '—')}")
            if r.get("price"):
                st.write(f"**Precio:** {r['price']:,.0f} Gs".replace(",", "."))
            if r.get("ota_booking_id"):
                st.write(f"**OTA Booking ID:** {r['ota_booking_id']}")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✓ Mantener (acknowledge)", key=f"ack_{r['id']}"):
                    try:
                        ack = _s.post(
                            f"{API_BASE_URL}/reservations/{r['id']}/acknowledge-review",
                            headers=_get_auth_headers(), timeout=5
                        )
                        if ack.ok:
                            st.success("Reserva mantenida activa.")
                            st.rerun()
                        else:
                            st.error(f"Error: {ack.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")
            with col_b:
                if st.button("❌ Confirmar cancelación OTA", key=f"cancel_{r['id']}"):
                    try:
                        cancel = _s.post(
                            f"{API_BASE_URL}/reservations/{r['id']}/confirm-ota-cancellation",
                            headers=_get_auth_headers(), timeout=5
                        )
                        if cancel.ok:
                            st.success("Reserva cancelada.")
                            st.rerun()
                        else:
                            st.error(f"Error: {cancel.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

# Export URLs section
st.markdown("---")
st.markdown("**URLs de Exportación** (para pegar en Booking.com / Airbnb / etc):")
if rooms_data:
    for r in rooms_data:
        label = r.get("internal_code", r["id"])
        export_url = f"http://localhost:8000/api/v1/ical/export/{r['id']}.ics"
        st.code(f"{label}: {export_url}", language=None)
    st.code(f"Todos: http://localhost:8000/api/v1/ical/export/all.ics", language=None)
    st.caption(
        "Reemplace 'localhost:8000' con su dominio de producción. "
        "Endpoints públicos limitados a 60/min (room) y 30/min (all)."
    )

st.markdown("---")
st.info(
    "ℹ️ Los feeds iCal se sincronizan automáticamente cada 15 minutos. "
    "Cuando un UID desaparece del feed OTA, la reserva se marca para revisión "
    "y se envía una alerta por Discord (a partir de 3 fallos consecutivos)."
)
