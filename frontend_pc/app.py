import streamlit as st
from dotenv import load_dotenv
from logging_config import get_logger

# Logger para este módulo
logger = get_logger(__name__)

# Importar Servicios
from services import AuthService

# Frontend-specific services
import api_client
from frontend_services.cache_service import force_refresh

# Import database for session logging
from database import engine

# Components & Helpers
from components.styles import inject_custom_css
from components.tab_calendario import render_tab_calendario
from components.tab_reserva import render_tab_reserva
from components.tab_checkin import render_tab_checkin
from helpers.auth_helpers import log_login, logout

# Verify DB Path
print(f"🔌 [SYSTEM CHECK] Frontend PC Database Path: {engine.url}")

# --- 1. CONFIGURACIÓN INICIAL ---
load_dotenv()
_hotel_config = api_client.get_hotel_config()
_hotel_name = _hotel_config.get("hotel_name", "Mi Hotel")
st.set_page_config(page_title=f"{_hotel_name} - Recepción", page_icon="🏨", layout="wide")

# Global CSS para optimizar espacio en pantallas de laptop
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. CONTROL DE LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if 'hotel_name' not in st.session_state:
    config = api_client.get_hotel_config()
    st.session_state.hotel_name = config.get("hotel_name", "Mi Hotel")

if not st.session_state.logged_in:
    st.markdown(f"## 🏨 {st.session_state.hotel_name} - Acceso (v4.0 Native Calendar)")
    with st.form("login_form"):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            user_dto = AuthService.authenticate(u, p)
            if user_dto:
                st.session_state.logged_in = True
                st.session_state.user = user_dto

                from api.core.security import create_access_token
                access_token = create_access_token(
                    data={"sub": user_dto.username}
                )
                st.session_state.api_token = access_token

                st.session_state.session_id = log_login(user_dto.username)
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# --- 3. INTERFAZ PRINCIPAL ---
inject_custom_css()

# Sidebar
with st.sidebar:
    st.write(f"👤 **{st.session_state.user.real_name}** ({st.session_state.user.role})")
    if st.button("Cerrar Sesión"): logout()
    if st.button("🔄 Sincronizar Datos"):
        force_refresh()
        st.success("Datos sincronizados")
        st.rerun()
    st.divider()

st.title(f"🏨 {st.session_state.hotel_name} - Sistema de Recepción")

if st.session_state.hotel_name in ["Mi Hotel", ""]:
    st.warning("⚠️ **Configuración requerida:** Por favor ingresa el nombre de tu hotel en **Administración → Configuración General**.")

# Tabs principales
tab_calendario, tab_reserva, tab_checkin = st.tabs([
    "📅 CALENDARIO Y ESTADO",
    "📞 NUEVA RESERVA",
    "👤 FICHA DE CLIENTE"
])

with tab_calendario:
    render_tab_calendario()

with tab_reserva:
    render_tab_reserva()

with tab_checkin:
    render_tab_checkin()
