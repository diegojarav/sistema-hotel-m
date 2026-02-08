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
st.info("ℹ️ Los cambios afectan inmediatamente a las nuevas reservas.")
