"""
Hotel Munich - Caja (Cash Register) Management
================================================

Panel para gestionar sesiones de caja, registrar pagos y ver reportes financieros.

Funcionalidades:
- Abrir/cerrar sesiones de caja
- Ver sesion actual + movimientos del turno
- Historial de sesiones pasadas
- Reportes financieros (ingresos diarios, transferencias, resumen por periodo)
"""

import streamlit as st
import requests
from datetime import datetime, date, timedelta
import io
import csv
import pandas as pd

from logging_config import get_logger
from api_client import get_session

_s = get_session()
logger = get_logger(__name__)

API_BASE_URL = "http://localhost:8000/api/v1"

# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="Caja & Pagos",
    page_icon="💰",
    layout="wide"
)

# ==========================================
# SECURITY CHECK
# ==========================================

def check_access():
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.error("Debe iniciar sesion para acceder a esta pagina")
        st.stop()
    user = st.session_state.get('user')
    if not user:
        st.error("Sesion invalida")
        st.stop()
    return True


check_access()

# ==========================================
# API HELPERS
# ==========================================

def get_auth_headers():
    token = st.session_state.get('api_token')
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def fmt_gs(amount) -> str:
    """Format guaranies amount for display."""
    if amount is None:
        return "-"
    try:
        return f"{float(amount):,.0f} Gs".replace(",", ".")
    except (ValueError, TypeError):
        return str(amount)


def api_get(path: str):
    try:
        r = _s.get(f"{API_BASE_URL}{path}", headers=get_auth_headers(), timeout=10)
        if r.ok:
            return r.json()
        st.error(f"Error al cargar datos: {r.status_code} {r.text}")
    except Exception as e:
        st.error(f"Error de conexion: {e}")
    return None


def api_post(path: str, data: dict):
    try:
        r = _s.post(f"{API_BASE_URL}{path}", json=data, headers=get_auth_headers(), timeout=10)
        if r.ok:
            return True, r.json()
        detail = r.json().get("detail", f"HTTP {r.status_code}") if r.headers.get("content-type", "").startswith("application/json") else r.text
        return False, detail
    except Exception as e:
        return False, str(e)


# ==========================================
# HEADER
# ==========================================

st.title("💰 Caja & Pagos")
st.caption(f"Gestion de caja y transacciones - {st.session_state.get('hotel_name', 'Hotel')}")

tab_actual, tab_historial, tab_reportes = st.tabs([
    "📊 Sesion Actual",
    "📜 Historial",
    "📈 Reportes Financieros",
])

# ==========================================
# TAB 1 — SESION ACTUAL
# ==========================================

with tab_actual:
    current = api_get("/caja/actual")

    if current is None:
        st.error("No se pudo cargar la informacion de caja.")
        st.stop()

    # NO SESSION OPEN
    if current == {} or current is None or not current:
        st.warning("⚠️ No tenes ninguna sesion de caja abierta.")
        st.markdown("### Abrir nueva caja")

        col1, col2 = st.columns([1, 2])
        with col1:
            opening_balance = st.number_input(
                "Balance inicial (Gs)",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                format="%.0f",
            )
        with col2:
            open_notes = st.text_input("Notas (opcional)", placeholder="Ej: Turno mañana")

        if st.button("💰 Abrir Caja", type="primary", use_container_width=True):
            ok, result = api_post("/caja/abrir", {
                "opening_balance": float(opening_balance),
                "notes": open_notes,
            })
            if ok:
                st.success(f"Caja abierta. Balance inicial: {fmt_gs(opening_balance)}")
                st.rerun()
            else:
                st.error(f"Error al abrir caja: {result}")

    # SESSION OPEN
    else:
        sesion = current
        detalle = api_get(f"/caja/{sesion['id']}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Apertura", fmt_gs(sesion.get("opening_balance", 0)))
        with col2:
            st.metric("Efectivo", fmt_gs(detalle.get("total_efectivo", 0) if detalle else 0))
        with col3:
            st.metric("Transferencias", fmt_gs(detalle.get("total_transferencia", 0) if detalle else 0))
        with col4:
            st.metric("POS", fmt_gs(detalle.get("total_pos", 0) if detalle else 0))

        expected = (sesion.get("opening_balance", 0) or 0) + (detalle.get("total_efectivo", 0) if detalle else 0)

        st.info(f"💵 **Esperado en caja:** {fmt_gs(expected)}")

        # Session meta
        opened_at = sesion.get("opened_at", "")
        try:
            opened_dt = datetime.fromisoformat(opened_at.replace("Z", "")) if opened_at else None
            opened_str = opened_dt.strftime("%d/%m/%Y %H:%M") if opened_dt else "?"
        except Exception:
            opened_str = opened_at
        st.caption(
            f"Sesion #{sesion['id']} • Abierta por {sesion.get('user_name', '?')} el {opened_str}"
        )
        if sesion.get("notes"):
            st.caption(f"Notas: {sesion['notes']}")

        st.divider()

        # Transactions table
        if detalle and detalle.get("transactions"):
            st.subheader("Transacciones del turno")
            trans_data = [
                {
                    "ID": t["id"],
                    "Hora": (t["created_at"] or "")[-8:-3] if t.get("created_at") else "",
                    "Metodo": t["payment_method"],
                    "Monto": fmt_gs(t["amount"]),
                    "Reserva": t.get("reserva_id") or "",
                    "Ref": t.get("reference_number") or "",
                    "Estado": "ANULADA" if t["voided"] else "activa",
                }
                for t in detalle["transactions"]
            ]
            df = pd.DataFrame(trans_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Aun no hay transacciones registradas en esta sesion.")

        st.divider()

        # Cerrar caja
        st.subheader("Cerrar Caja")
        col1, col2 = st.columns([1, 2])
        with col1:
            declared = st.number_input(
                "Monto declarado en caja (Gs)",
                min_value=0.0,
                value=float(expected),
                step=1000.0,
                format="%.0f",
            )
        with col2:
            close_notes = st.text_input("Notas de cierre (opcional)", key="close_notes")

        diff = declared - expected
        if diff == 0:
            st.success(f"✓ Cuadrado con lo esperado ({fmt_gs(expected)})")
        elif diff < 0:
            st.error(f"⚠️ Faltante: {fmt_gs(abs(diff))}")
        else:
            st.warning(f"⚠️ Sobrante: {fmt_gs(diff)}")

        if st.button("🔒 Cerrar Caja", type="primary"):
            ok, result = api_post("/caja/cerrar", {
                "session_id": sesion["id"],
                "closing_balance_declared": float(declared),
                "notes": close_notes,
            })
            if ok:
                st.success(f"Caja cerrada. Diferencia: {fmt_gs(diff)}")
                st.rerun()
            else:
                st.error(f"Error al cerrar caja: {result}")


# ==========================================
# TAB 2 — HISTORIAL
# ==========================================

with tab_historial:
    st.subheader("Historial de sesiones")

    limit = st.slider("Cantidad de sesiones a mostrar", 10, 200, 50)
    sessions = api_get(f"/caja/historial?limit={limit}")

    if sessions is None:
        st.error("No se pudo cargar el historial")
    elif not sessions:
        st.info("Aun no hay sesiones registradas.")
    else:
        rows = []
        for s in sessions:
            opened = s.get("opened_at", "")[:19].replace("T", " ") if s.get("opened_at") else ""
            closed = s.get("closed_at", "")[:19].replace("T", " ") if s.get("closed_at") else "-"
            rows.append({
                "ID": s["id"],
                "Usuario": s.get("user_name", "?"),
                "Estado": s.get("status", ""),
                "Abierta": opened,
                "Cerrada": closed,
                "Apertura": fmt_gs(s.get("opening_balance", 0)),
                "Efectivo": fmt_gs(s.get("total_efectivo", 0)),
                "Declarado": fmt_gs(s.get("closing_balance_declared")),
                "Diferencia": fmt_gs(s.get("difference")) if s.get("difference") is not None else "-",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ==========================================
# TAB 3 — REPORTES FINANCIEROS
# ==========================================

with tab_reportes:
    st.subheader("📈 Reportes Financieros")

    sub1, sub2, sub3 = st.tabs([
        "Ingresos del dia",
        "Transferencias (conciliacion)",
        "Resumen por periodo",
    ])

    # --- Ingresos del dia ---
    with sub1:
        fecha = st.date_input("Fecha", value=date.today(), key="ing_fecha")
        data = api_get(f"/reportes/ingresos-diarios?fecha={fecha.isoformat()}")

        if data:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("💵 Efectivo", fmt_gs(data["efectivo"]["total"]),
                          f"{data['efectivo']['count']} pagos")
            with col2:
                st.metric("🏦 Transferencia", fmt_gs(data["transferencia"]["total"]),
                          f"{data['transferencia']['count']} pagos")
            with col3:
                st.metric("💳 POS", fmt_gs(data["pos"]["total"]),
                          f"{data['pos']['count']} pagos")
            with col4:
                st.metric("📊 TOTAL", fmt_gs(data["total_general"]),
                          f"{data['transacciones_total']} total")

    # --- Transferencias ---
    with sub2:
        col1, col2 = st.columns(2)
        with col1:
            desde = st.date_input("Desde", value=date.today() - timedelta(days=30), key="tr_desde")
        with col2:
            hasta = st.date_input("Hasta", value=date.today(), key="tr_hasta")

        data = api_get(f"/reportes/transferencias?desde={desde.isoformat()}&hasta={hasta.isoformat()}")

        if data and data.get("transferencias"):
            st.success(f"Total: {fmt_gs(data['total'])} ({data['count']} transferencias)")
            rows = [
                {
                    "Fecha": (t["created_at"] or "")[:19].replace("T", " "),
                    "Reserva": t.get("reserva_id") or "",
                    "Monto": fmt_gs(t["amount"]),
                    "Referencia": t.get("reference_number") or "",
                    "Descripcion": t.get("description") or "",
                    "Usuario": t.get("created_by") or "",
                }
                for t in data["transferencias"]
            ]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # CSV export
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(["fecha", "reserva_id", "monto", "referencia", "descripcion", "usuario"])
            for t in data["transferencias"]:
                writer.writerow([
                    (t["created_at"] or "")[:19].replace("T", " "),
                    t.get("reserva_id") or "",
                    t["amount"],
                    t.get("reference_number") or "",
                    t.get("description") or "",
                    t.get("created_by") or "",
                ])
            st.download_button(
                "📥 Descargar CSV",
                csv_buffer.getvalue(),
                f"transferencias_{desde.isoformat()}_{hasta.isoformat()}.csv",
                "text/csv",
            )
        elif data is not None:
            st.info("No hay transferencias en el periodo seleccionado.")

    # --- Resumen por periodo ---
    with sub3:
        col1, col2 = st.columns(2)
        with col1:
            desde_r = st.date_input("Desde", value=date.today().replace(day=1), key="rp_desde")
        with col2:
            hasta_r = st.date_input("Hasta", value=date.today(), key="rp_hasta")

        data = api_get(f"/reportes/resumen-periodo?desde={desde_r.isoformat()}&hasta={hasta_r.isoformat()}")

        if data:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total general", fmt_gs(data["total_general"]))
            with col2:
                st.metric("Transacciones", data["total_transacciones"])
            with col3:
                st.metric("Promedio/transaccion", fmt_gs(data["promedio_por_transaccion"]))

            if data.get("por_metodo"):
                st.subheader("Distribucion por metodo")
                rows = [
                    {
                        "Metodo": m["metodo"],
                        "Total": fmt_gs(m["total"]),
                        "Cantidad": m["count"],
                        "Porcentaje": f"{m['porcentaje']:.1f}%",
                    }
                    for m in data["por_metodo"]
                ]
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)
