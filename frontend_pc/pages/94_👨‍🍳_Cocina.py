"""
Hotel Munich - Reporte de Cocina (v1.7.0 — Phase 4)
====================================================

Panel operacional para la cocina. Por defecto muestra el reporte para MAÑANA
(modo planificación — la cocina puede preparar con anticipación). Se puede
elegir cualquier fecha (hoy, pasado, futuro).

Si el hotel no tiene habilitado el servicio de comidas, muestra un mensaje y
un link a la página de Configuración.

Accesible por: admin, supervisor, gerencia, recepcion, **cocina** (read-only).
"""

import io
from datetime import date, timedelta

import pandas as pd
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
st.set_page_config(page_title="Cocina", page_icon="👨‍🍳", layout="wide")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.error("Debe iniciar sesion para acceder a esta pagina")
    st.stop()

user = st.session_state.get("user")
_ALLOWED = {"admin", "supervisor", "gerencia", "recepcion", "cocina"}
if not user or not user.role or user.role.lower() not in _ALLOWED:
    st.error("🛑 No tiene permisos para ver esta página.")
    st.stop()

st.title("👨‍🍳 Cocina — Reporte Diario")
st.caption(
    f"Reporte de desayunos y comidas · Usuario: {user.username} ({user.role})"
)

# ==========================================
# HELPERS
# ==========================================

def _auth_headers() -> dict:
    # BUG-TOKEN-PC: app.py guarda el JWT bajo `api_token`, no `access_token`.
    # Mismo patrón que BUG-TOKEN-PC-01 / BUG-TOKEN-SETTINGS.
    token = st.session_state.get("api_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


# ==========================================
# DATE PICKER — default tomorrow (planning mode)
# ==========================================
default_date = date.today() + timedelta(days=1)
col_date, col_today = st.columns([3, 1])
fecha = col_date.date_input(
    "Fecha del reporte",
    value=default_date,
    help="Por defecto: mañana. Útil para planificar la preparación con anticipación.",
)
if col_today.button("🔄 Actualizar"):
    st.rerun()

st.markdown("---")

# ==========================================
# FETCH REPORT
# ==========================================
try:
    resp = requests.get(
        f"{API_BASE_URL}/reportes/cocina",
        params={"fecha": fecha.isoformat()},
        headers=_auth_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    report = resp.json()
except requests.HTTPError as e:
    if resp.status_code == 403:
        st.error("🛑 No tiene permisos para ver este reporte.")
    else:
        st.error(f"Error al obtener el reporte: {e}")
    st.stop()
except Exception as e:
    st.error(f"Error al conectar con el backend: {e}")
    st.stop()

# ==========================================
# DISABLED STATE
# ==========================================
if not report.get("enabled"):
    st.info(
        "🍽️ **Servicio de comidas no habilitado.** Para activar el reporte de "
        "cocina, vaya a **Configuración → Configuración de Comidas** y habilite "
        "el servicio."
    )
    st.stop()

# ==========================================
# SUMMARY
# ==========================================
mode_labels = {
    "INCLUIDO": "Desayuno incluido en la tarifa",
    "OPCIONAL_PERSONA": "Opcional — por persona",
    "OPCIONAL_HABITACION": "Opcional — por habitación",
}
mode_text = mode_labels.get(report.get("mode"), "-")

st.caption(f"**Modalidad:** {mode_text}")

c1, c2, c3 = st.columns(3)
c1.metric("🥐 Total desayunos", report["total_with_breakfast"])
c2.metric("Sin desayuno", report["total_without"])
c3.metric("Fecha", fecha.strftime("%d/%m/%Y"))

# ==========================================
# DETAIL TABLE
# ==========================================
st.markdown("### Detalle por habitación")

rooms = report.get("rooms", [])
if not rooms:
    st.info("Sin reservas activas para esta fecha.")
else:
    df = pd.DataFrame([
        {
            "Hab.": r["internal_code"],
            "Huésped": r["guest_name"],
            "Pax": r["guests_count"],
            "Desay.": r["breakfast_guests"],
            "Plan": r.get("plan_name") or "-",
            "Check-out": r["checkout_date"] + (" (hoy)" if r.get("checkout_today") else ""),
        }
        for r in rooms
    ])

    # Highlight checkout-today rows
    def _highlight_checkout_today(row):
        # Find original index to check checkout_today
        idx = df.index.get_loc(row.name)
        if rooms[idx].get("checkout_today"):
            return ["background-color: #fff8dc"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df.style.apply(_highlight_checkout_today, axis=1),
        hide_index=True,
        use_container_width=True,
    )

    # CSV export
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "📥 Descargar CSV",
        csv_buf.getvalue(),
        file_name=f"cocina_{fecha.strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

st.markdown("---")

# ==========================================
# PDF DOWNLOAD
# ==========================================
st.markdown("### Descargar PDF")
if st.button("📄 Generar PDF del reporte"):
    try:
        pdf_resp = requests.get(
            f"{API_BASE_URL}/reportes/cocina/pdf",
            params={"fecha": fecha.isoformat()},
            headers=_auth_headers(),
            timeout=20,
        )
        pdf_resp.raise_for_status()
        st.download_button(
            "⬇ Descargar cocina_{}.pdf".format(fecha.strftime("%Y%m%d")),
            pdf_resp.content,
            file_name=f"cocina_{fecha.strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
        )
    except requests.HTTPError as e:
        st.error(f"Error al generar PDF: {e}")
    except Exception as e:
        st.error(f"Error: {e}")
