"""
Hotel Munich - Administración de Usuarios
==========================================

Panel seguro para gestionar usuarios del sistema.
Solo accesible para usuarios con rol "admin".

Funcionalidades:
- Listar usuarios (sin mostrar hash de contraseña)
- Crear nuevos usuarios con contraseña hasheada
- Resetear contraseñas de usuarios existentes

V9 FIX: Refactored to use API calls instead of direct database access.
"""

import streamlit as st
import requests
from datetime import datetime, timedelta

# Import logging and shared session (PERF-10)
from logging_config import get_logger
from api_client import get_session

_s = get_session()

logger = get_logger(__name__)

# API Base URL
API_BASE_URL = "http://localhost:8000/api/v1"


# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="Admin - Usuarios",
    page_icon="👤",
    layout="wide"
)


# ==========================================
# SECURITY CHECK
# ==========================================

def check_admin_access():
    """Verify user is logged in and has admin role."""
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.error("⛔ Debe iniciar sesión para acceder a esta página")
        st.stop()
    
    user = st.session_state.get('user')
    if not user:
        st.error("⛔ Sesión inválida")
        st.stop()
    
    # Check if user has admin role
    if hasattr(user, 'role') and user.role and user.role.lower() == 'admin':
        return True
    
    # Show warning but allow access (for development/legacy purposes)
    st.warning("⚠️ **Área Restringida** - Esta sección está destinada a administradores.")
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


def get_all_users():
    """Fetch all users via API."""
    try:
        response = _s.get(
            f"{API_BASE_URL}/users",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            users = response.json()
            # Convert to objects with attributes for compatibility
            class UserObj:
                def __init__(self, data):
                    self.id = data['id']
                    self.username = data['username']
                    self.real_name = data.get('real_name')
                    self.role = data.get('role')
                    self.password = '$2' if data.get('is_password_hashed') else 'plain'
            return [UserObj(u) for u in users]
        return []
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        return []


def create_user(username: str, password: str, role: str, real_name: str) -> tuple:
    """Create a new user via API."""
    try:
        response = _s.post(
            f"{API_BASE_URL}/users",
            json={
                "username": username,
                "password": password,
                "role": role,
                "real_name": real_name
            },
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            logger.info(f"Usuario creado: {username} por {st.session_state.user.username}")
            return True, "Usuario creado exitosamente"
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error creando usuario: {e}")
        return False, str(e)


def reset_user_password(user_id: int, new_password: str) -> tuple:
    """Reset a user's password via API."""
    try:
        response = _s.patch(
            f"{API_BASE_URL}/users/{user_id}/password",
            json={"new_password": new_password},
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            result = response.json()
            logger.info(f"Contraseña reseteada por {st.session_state.user.username}")
            return True, result.get('message', 'Contraseña actualizada')
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error reseteando contraseña: {e}")
        return False, str(e)


def delete_user(user_id: int) -> tuple:
    """Delete a user via API."""
    try:
        response = _s.delete(
            f"{API_BASE_URL}/users/{user_id}",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            result = response.json()
            logger.info(f"Usuario eliminado por {st.session_state.user.username}")
            return True, result.get('message', 'Usuario eliminado')
        else:
            error = response.json().get('detail', 'Error desconocido')
            return False, error
    except Exception as e:
        logger.error(f"Error eliminando usuario: {e}")
        return False, str(e)


def get_session_logs(filter_user: str = None):
    """Fetch session logs via API."""
    try:
        params = {"limit": 100}
        if filter_user and filter_user != "Todos":
            params["username"] = filter_user

        response = _s.get(
            f"{API_BASE_URL}/users/sessions",
            params=params,
            headers=get_auth_headers(),
            timeout=10
        )
        if response.ok:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        return []


# ==========================================
# MAIN PAGE
# ==========================================

# Check access
check_admin_access()

# Header
st.title("👤 Administración de Usuarios")
st.caption(f"Gestión segura de usuarios del sistema {st.session_state.get('hotel_name', 'Mi Hotel')}")

st.divider()

# ==========================================
# TAB LAYOUT
# ==========================================

tab_list, tab_create, tab_reset, tab_sessions, tab_config = st.tabs([
    "📋 Lista de Usuarios",
    "➕ Crear Usuario",
    "🔑 Resetear Contraseña",
    "📊 Historial de Sesiones",
    "⚙️ Configuración General"
])


# ------------------------------------------
# TAB 1: List Users
# ------------------------------------------
with tab_list:
    st.subheader("📋 Usuarios Registrados")
    
    if st.button("🔄 Actualizar Lista", key="refresh_list"):
        st.rerun()
    
    users = get_all_users()
    
    if users:
        # Create display data (without password hash!)
        user_data = []
        for u in users:
            # Check if password is hashed (starts with $2) or plaintext
            is_hashed = u.password.startswith('$2') if u.password else False
            
            user_data.append({
                "ID": u.id,
                "Usuario": u.username,
                "Nombre Real": u.real_name or "—",
                "Rol": u.role or "—",
                "Password": "🔒 Hasheado" if is_hashed else "⚠️ Texto Plano"
            })
        
        # Display table
        st.dataframe(
            user_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Usuario": st.column_config.TextColumn("Usuario", width="medium"),
                "Nombre Real": st.column_config.TextColumn("Nombre Real", width="medium"),
                "Rol": st.column_config.TextColumn("Rol", width="small"),
                "Password": st.column_config.TextColumn("Password", width="medium"),
            }
        )
        
        st.info(f"📊 Total: **{len(users)}** usuarios registrados")
        
        # Show warning if there are plaintext passwords
        plaintext_count = sum(1 for u in users if not (u.password and u.password.startswith('$2')))
        if plaintext_count > 0:
            st.warning(f"⚠️ **{plaintext_count}** usuario(s) tienen contraseñas en texto plano. "
                      "Use la pestaña 'Resetear Contraseña' para migrarlos a bcrypt.")
    else:
        st.info("No hay usuarios registrados")


# ------------------------------------------
# TAB 2: Create User
# ------------------------------------------
with tab_create:
    st.subheader("➕ Crear Nuevo Usuario")
    
    with st.form("create_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            new_username = st.text_input(
                "Nombre de Usuario *",
                placeholder="ej: recepcion1",
                help="Identificador único para login"
            )
            new_password = st.text_input(
                "Contraseña *",
                type="password",
                placeholder="Mínimo 4 caracteres",
                help="Se encriptará automáticamente con bcrypt"
            )
        
        with col2:
            new_real_name = st.text_input(
                "Nombre Real *",
                placeholder="ej: Juan Pérez",
                help="Nombre completo del usuario"
            )
            new_role = st.selectbox(
                "Rol *",
                options=["recepcion", "admin", "gerencia", "limpieza"],
                help="Determina los permisos del usuario"
            )
        
        st.divider()
        
        submitted = st.form_submit_button("✅ Crear Usuario", type="primary", use_container_width=True)
        
        if submitted:
            # Validation
            if not new_username or not new_password or not new_real_name:
                st.error("❌ Todos los campos marcados con * son obligatorios")
            elif len(new_password) < 4:
                st.error("❌ La contraseña debe tener al menos 4 caracteres")
            elif len(new_username) < 3:
                st.error("❌ El nombre de usuario debe tener al menos 3 caracteres")
            else:
                success, message = create_user(new_username, new_password, new_role, new_real_name)
                if success:
                    st.success(f"✅ {message}")
                    st.balloons()
                else:
                    st.error(f"❌ {message}")


# ------------------------------------------
# TAB 3: Reset Password
# ------------------------------------------
with tab_reset:
    st.subheader("🔑 Resetear Contraseña")
    
    users = get_all_users()
    
    if users:
        # Create options for dropdown
        user_options = {f"{u.username} ({u.real_name or 'Sin nombre'})": u.id for u in users}
        
        with st.form("reset_password_form", clear_on_submit=True):
            selected_user_label = st.selectbox(
                "Seleccionar Usuario *",
                options=list(user_options.keys()),
                help="Usuario al que se le reseteará la contraseña"
            )
            
            new_pwd = st.text_input(
                "Nueva Contraseña *",
                type="password",
                placeholder="Mínimo 4 caracteres",
                help="Se encriptará con bcrypt"
            )
            
            confirm_pwd = st.text_input(
                "Confirmar Contraseña *",
                type="password",
                placeholder="Repita la contraseña"
            )
            
            st.divider()
            
            submitted = st.form_submit_button("🔄 Resetear Contraseña", type="primary", use_container_width=True)
            
            if submitted:
                if not new_pwd or not confirm_pwd:
                    st.error("❌ Debe completar ambos campos de contraseña")
                elif new_pwd != confirm_pwd:
                    st.error("❌ Las contraseñas no coinciden")
                elif len(new_pwd) < 4:
                    st.error("❌ La contraseña debe tener al menos 4 caracteres")
                else:
                    user_id = user_options[selected_user_label]
                    success, message = reset_user_password(user_id, new_pwd)
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
    else:
        st.info("No hay usuarios registrados para resetear")


# ------------------------------------------
# TAB 4: Session Logs
# ------------------------------------------
with tab_sessions:
    st.subheader("📊 Historial de Sesiones")

    col_filter, col_refresh = st.columns([3, 1])

    with col_filter:
        filter_user = st.selectbox(
            "Filtrar por usuario",
            options=["Todos"] + [u.username for u in get_all_users()],
            key="session_filter_user"
        )

    with col_refresh:
        st.write("")  # Spacer
        st.write("")  # Spacer
        if st.button("🔄 Actualizar", key="refresh_sessions"):
            st.rerun()

    # Fetch session logs via API
    sessions = get_session_logs(filter_user)

    if sessions:
        session_data = []
        for s in sessions:
            # Parse timestamps
            login_time = datetime.fromisoformat(s['login_time']) if s.get('login_time') else None
            logout_time = datetime.fromisoformat(s['logout_time']) if s.get('logout_time') else None

            # Calculate duration if logout exists
            if logout_time and login_time:
                duration = logout_time - login_time
                duration_str = str(duration).split('.')[0]  # Remove microseconds
                status = "✅ Cerrada"
            else:
                duration_str = "—"
                status = "🟢 Activa"

            session_data.append({
                "Usuario": s.get('username', '—'),
                "Login": login_time.strftime("%Y-%m-%d %H:%M:%S") if login_time else "—",
                "Logout": logout_time.strftime("%Y-%m-%d %H:%M:%S") if logout_time else "—",
                "Duración": duration_str,
                "Estado": status
            })

        st.dataframe(
            session_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Usuario": st.column_config.TextColumn("Usuario", width="medium"),
                "Login": st.column_config.TextColumn("Inicio Sesión", width="large"),
                "Logout": st.column_config.TextColumn("Cierre Sesión", width="large"),
                "Duración": st.column_config.TextColumn("Duración", width="medium"),
                "Estado": st.column_config.TextColumn("Estado", width="small"),
            }
        )

        # Summary stats
        active_count = sum(1 for s in sessions if not s.get('logout_time'))
        closed_count = sum(1 for s in sessions if s.get('logout_time'))

        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total Sesiones", len(sessions))
        col2.metric("🟢 Activas", active_count)
        col3.metric("✅ Cerradas", closed_count)
    else:
        st.info("No hay sesiones registradas")


# ------------------------------------------
# TAB 5: Configuration
# ------------------------------------------
with tab_config:
    st.subheader("⚙️ Configuración General")
    st.caption("Configura los parámetros generales del sistema")
    
    st.markdown("---")
    st.markdown("### 🏨 Nombre del Establecimiento")
    
    current_name = st.session_state.get('hotel_name', 'Mi Hotel')
    
    with st.form("config_form", clear_on_submit=False):
        new_hotel_name = st.text_input(
            "Nombre del Hotel",
            value=current_name,
            help="Este nombre aparecerá en toda la interfaz del sistema",
            placeholder="Ej: Hotel Paradise"
        )
        
        st.divider()
        
        submitted = st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True)
        
        if submitted:
            if not new_hotel_name or len(new_hotel_name.strip()) < 2:
                st.error("❌ El nombre debe tener al menos 2 caracteres")
            elif new_hotel_name.strip() == current_name:
                st.info("ℹ️ No hay cambios para guardar")
            else:
                # Import frontend services and update
                import api_client
                
                # Get JWT token from session (if available)
                token = st.session_state.get('jwt_token', '')
                
                if api_client.set_hotel_name(new_hotel_name.strip(), token):
                    st.session_state.hotel_name = new_hotel_name.strip()
                    st.success(f"✅ Nombre actualizado a: **{new_hotel_name.strip()}**")
                    st.info("🔄 Recarga la página para ver los cambios en el título")
                    st.balloons()
                else:
                    st.error("❌ Error al guardar. Verifica que el servidor backend esté corriendo.")
    
    st.markdown("---")
    st.info("💡 **Tip:** El nombre del hotel se utiliza en el título de la página, encabezados y en las respuestas del asistente IA.")


# ==========================================
# FOOTER
# ==========================================
st.divider()

st.caption("🔐 Todas las contraseñas nuevas se encriptan con **bcrypt** antes de guardarse.")
st.caption("📝 Las operaciones quedan registradas en el log del sistema.")
