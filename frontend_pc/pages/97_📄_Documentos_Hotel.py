"""
Hotel Munich - Documentos del Hotel
====================================
Browse and download generated PDF documents (reservations and clients).
"""

import os
import streamlit as st
from datetime import datetime

from logging_config import get_logger

logger = get_logger(__name__)

# Import paths directly from backend (PYTHONPATH includes ../backend)
from services.document_service import RESERVAS_DIR, CLIENTES_DIR

st.set_page_config(
    page_title="Documentos del Hotel",
    page_icon="📄",
    layout="wide"
)


# ==========================================
# SECURITY CHECK
# ==========================================

def check_access():
    """Verify user is logged in."""
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.error("Debe iniciar sesion para acceder a esta pagina")
        st.stop()

    user = st.session_state.get('user')
    if not user:
        st.error("Sesion invalida")
        st.stop()

check_access()


# ==========================================
# MAIN PAGE
# ==========================================

st.title("Documentos del Hotel")

tab_reservas, tab_clientes, tab_emails = st.tabs(["Reservas", "Clientes", "📧 Historial de Emails"])


def _render_document_list(folder: str):
    """Render a list of PDF documents with download buttons."""
    target_dir = RESERVAS_DIR if folder == "Reservas" else CLIENTES_DIR

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("Actualizar", key=f"refresh_{folder}"):
            st.rerun()

    if not os.path.isdir(target_dir):
        st.info(f"No hay documentos en {folder}.")
        return

    pdf_files = sorted(
        [f for f in os.listdir(target_dir) if f.lower().endswith(".pdf")],
        reverse=True,
    )

    if not pdf_files:
        st.info(f"No hay documentos en {folder}.")
        return

    st.caption(f"{len(pdf_files)} documento(s) encontrado(s)")

    for filename in pdf_files:
        filepath = os.path.join(target_dir, filename)
        stat = os.stat(filepath)
        size_kb = stat.st_size / 1024
        date_display = datetime.fromtimestamp(stat.st_ctime).strftime("%d/%m/%Y %H:%M")

        col_name, col_date, col_size, col_dl = st.columns([4, 2, 1, 1])

        with col_name:
            st.text(filename)
        with col_date:
            st.text(date_display)
        with col_size:
            st.text(f"{size_kb:.0f} KB")
        with col_dl:
            with open(filepath, "rb") as f:
                pdf_data = f.read()
            st.download_button(
                label="Descargar",
                data=pdf_data,
                file_name=filename,
                mime="application/pdf",
                key=f"dl_{folder}_{filename}",
            )

        st.divider()


with tab_reservas:
    _render_document_list("Reservas")

with tab_clientes:
    _render_document_list("Clientes")


# ==========================================
# EMAIL HISTORY TAB (v1.8.0 — Phase 5)
# ==========================================

with tab_emails:
    st.caption(
        "Auditoría de envíos de correo de confirmación. Los registros son "
        "inmutables: cada intento queda guardado con su estado final."
    )

    # Filters live OUTSIDE any form — st.download_button cannot sit inside a form.
    from datetime import date as _date, timedelta as _timedelta
    from sqlalchemy import and_ as _and

    col_desde, col_hasta, col_estado, col_refresh = st.columns([1, 1, 1, 1])
    with col_desde:
        _desde = st.date_input(
            "Desde", value=_date.today() - _timedelta(days=30), key="email_desde"
        )
    with col_hasta:
        _hasta = st.date_input("Hasta", value=_date.today(), key="email_hasta")
    with col_estado:
        _estado_filter = st.selectbox(
            "Estado",
            ["Todos", "ENVIADO", "FALLIDO", "PENDIENTE"],
            key="email_estado_filter",
        )
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("Actualizar", key="refresh_emails"):
            st.rerun()

    # Query directly from the shared DB (same-machine access — Streamlit is co-located with backend).
    from services._base import SessionLocal
    from database import EmailLog

    _session_db = SessionLocal()
    try:
        _q = _session_db.query(EmailLog).filter(
            EmailLog.created_at >= _desde,
            EmailLog.created_at < (_hasta + _timedelta(days=1)),
        )
        if _estado_filter != "Todos":
            _q = _q.filter(EmailLog.status == _estado_filter)
        _rows = _q.order_by(EmailLog.created_at.desc()).limit(500).all()
    finally:
        _session_db.close()
        SessionLocal.remove()

    if not _rows:
        st.info("Sin registros en el rango y filtro seleccionados.")
    else:
        st.caption(f"{len(_rows)} registro(s) encontrado(s)")

        import pandas as pd
        _data = [
            {
                "Fecha": (r.sent_at or r.created_at).strftime("%d/%m/%Y %H:%M") if (r.sent_at or r.created_at) else "-",
                "Reserva": r.reserva_id,
                "Destinatario": r.recipient_email,
                "Asunto": r.subject,
                "Estado": r.status,
                "Error": (r.error_message or "")[:120] if r.status == "FALLIDO" else "",
            }
            for r in _rows
        ]
        _df = pd.DataFrame(_data)
        st.dataframe(_df, hide_index=True, use_container_width=True)

        # CSV export — MUST live outside any st.form per Streamlit rules.
        _csv = _df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="⬇️ Exportar CSV",
            data=_csv,
            file_name=f"email_log_{_desde.isoformat()}_{_hasta.isoformat()}.csv",
            mime="text/csv",
            key="email_csv_export",
        )
