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

tab_reservas, tab_clientes = st.tabs(["Reservas", "Clientes"])


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
