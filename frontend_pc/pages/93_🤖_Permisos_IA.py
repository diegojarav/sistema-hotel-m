"""
Hotel Munich — Permisos de Herramientas IA (v1.9.0 — Feature 1)
================================================================

Activa la configuración granular de permisos del agente IA por rol.
Cada rol (admin, supervisor, gerencia, recepcion, recepcionista, cocina)
tiene su propio set de 14 permisos booleanos que determinan qué
herramientas del agente puede invocar.

Solo accesible por Admin.
"""

import requests
import streamlit as st

from api_client import get_session
from logging_config import get_logger

_s = get_session()
logger = get_logger(__name__)
API_BASE_URL = "http://localhost:8000/api/v1"

# ==========================================
# PAGE CONFIG + AUTH
# ==========================================
st.set_page_config(page_title="Permisos IA", page_icon="🤖", layout="wide")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.error("Debe iniciar sesion para acceder a esta pagina")
    st.stop()

user = st.session_state.get("user")
if not user or not user.role or user.role.lower() != "admin":
    st.error("🛑 Solo el Admin puede configurar permisos de la IA.")
    st.stop()

st.title("🤖 Permisos de Herramientas IA")
st.caption(
    f"Control granular por rol de qué puede consultar el agente · Usuario: {user.username}"
)

# ==========================================
# AUTH + API HELPERS
# ==========================================

def get_auth_headers() -> dict:
    # Token PC convention (see feedback_dev_environment_gotchas.md G3)
    token = st.session_state.get("api_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


# ==========================================
# PERMISSION METADATA
# ==========================================

# User-friendly Spanish labels for the 14 permission columns
PERMISSION_LABELS = {
    "can_view_reservations":   "Ver reservas",
    "can_create_reservations": "Crear reservas",
    "can_modify_reservations": "Modificar reservas",
    "can_cancel_reservations": "Cancelar reservas",
    "can_view_guests":         "Ver huéspedes",
    "can_modify_guests":       "Modificar huéspedes",
    "can_view_rooms":          "Ver habitaciones (disponibilidad)",
    "can_modify_rooms":        "Modificar habitaciones",
    "can_modify_room_status":  "Cambiar estado de habitación",
    "can_view_prices":         "Ver precios / tarifas",
    "can_modify_prices":       "Modificar precios",
    "can_view_reports":        "Ver reportes (incl. financieros)",
    "can_export_data":         "Exportar datos",
    "can_modify_settings":     "Modificar configuración",
}

PERMISSION_ORDER = list(PERMISSION_LABELS.keys())


# ==========================================
# LOAD STATE
# ==========================================

@st.cache_data(ttl=10)
def fetch_permissions():
    try:
        resp = _s.get(
            f"{API_BASE_URL}/admin/ai-permissions",
            headers=get_auth_headers(),
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.error(f"Error fetching AI permissions: {e}")
        return None


@st.cache_data(ttl=10)
def fetch_tool_map():
    try:
        # Use any role to get the tool map — it's static
        resp = _s.get(
            f"{API_BASE_URL}/admin/ai-permissions/admin/allowed-tools",
            headers=get_auth_headers(),
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("tool_permission_map", {})
        return {}
    except Exception:
        return {}


permissions_rows = fetch_permissions()
tool_map = fetch_tool_map()

if permissions_rows is None:
    st.error("No se pudieron cargar los permisos desde el backend.")
    st.stop()

# Index tool → list of tools controlled by each column
tools_by_permission = {}
for tool_name, perm_col in tool_map.items():
    tools_by_permission.setdefault(perm_col, []).append(tool_name)


# ==========================================
# WARNING BANNER
# ==========================================

st.info(
    "ℹ️ Los cambios afectan sólo a las consultas del agente IA. Los endpoints "
    "directos (páginas del PC y mobile) siguen su propio control de acceso por rol."
)

is_admin_row_shown = any(r["role"] == "admin" for r in permissions_rows)
if is_admin_row_shown:
    st.warning(
        "⚠️ Modificar los permisos del rol **admin** puede bloquear funcionalidades "
        "críticas del agente. Se rechaza dejar TODOS los permisos deshabilitados en "
        "admin / supervisor / gerencia."
    )


# ==========================================
# RENDER PER ROLE
# ==========================================

for row in permissions_rows:
    role = row["role"]
    with st.expander(f"👤 Rol: **{role}**", expanded=(role in {"admin", "recepcion", "recepcionista"})):
        st.markdown(f"Configura qué puede consultar el agente cuando un usuario `{role}` le hace una pregunta.")

        with st.form(key=f"form_{role}"):
            col1, col2 = st.columns(2)
            updated = {}
            for idx, perm in enumerate(PERMISSION_ORDER):
                target_col = col1 if idx % 2 == 0 else col2
                with target_col:
                    label = PERMISSION_LABELS[perm]
                    tools_hint = tools_by_permission.get(perm, [])
                    help_text = (
                        f"Controla: {', '.join(tools_hint)}"
                        if tools_hint
                        else "Sin herramientas IA activas asociadas (reservado para features futuras)."
                    )
                    updated[perm] = st.checkbox(
                        label,
                        value=bool(row.get(perm, False)),
                        key=f"{role}_{perm}",
                        help=help_text,
                    )

            submitted = st.form_submit_button(f"💾 Guardar permisos para {role}", width="stretch")
            if submitted:
                # Only send fields that actually changed
                diff = {k: v for k, v in updated.items() if bool(row.get(k, False)) != v}
                if not diff:
                    st.info("No hay cambios para guardar.")
                else:
                    try:
                        resp = _s.put(
                            f"{API_BASE_URL}/admin/ai-permissions/{role}",
                            headers={**get_auth_headers(), "Content-Type": "application/json"},
                            json=diff,
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            st.success(f"✅ Permisos actualizados para rol '{role}'. {len(diff)} cambio(s) aplicado(s).")
                            fetch_permissions.clear()
                            st.rerun()
                        else:
                            detail = resp.json().get("detail", resp.text) if resp.text else f"HTTP {resp.status_code}"
                            st.error(f"❌ Error: {detail}")
                    except Exception as e:
                        st.error(f"❌ Error de red: {e}")


# ==========================================
# REFERENCE: tool → permission mapping
# ==========================================

with st.expander("📚 Referencia: herramientas del agente y permisos que las controlan", expanded=False):
    if tool_map:
        # Sort by permission so it reads grouped
        grouped = {}
        for tool, perm in tool_map.items():
            grouped.setdefault(perm, []).append(tool)
        for perm in PERMISSION_ORDER:
            if perm not in grouped:
                continue
            st.markdown(f"**{PERMISSION_LABELS[perm]}** (`{perm}`)")
            for t in sorted(grouped[perm]):
                st.markdown(f"  - `{t}`")
    else:
        st.info("No se pudo cargar el mapeo de herramientas.")
