"""
Hotel Munich - Asistente IA Interno
====================================

Chat interface for internal staff to interact with the AI agent.
Connects to the secured FastAPI endpoint with JWT authentication.
"""

import streamlit as st
import requests
from datetime import datetime

# Import logging and shared session (PERF-10)
from logging_config import get_logger
from api_client import get_session

_s = get_session()

logger = get_logger(__name__)


# ==========================================
# PAGE CONFIG
# ==========================================

st.set_page_config(
    page_title="Asistente IA",
    page_icon="💬",
    layout="centered"
)


# ==========================================
# CONFIGURATION
# ==========================================

API_BASE_URL = "http://localhost:8000"
AGENT_QUERY_URL = f"{API_BASE_URL}/api/v1/agent/query"
AGENT_STATUS_URL = f"{API_BASE_URL}/api/v1/agent/status"


# ==========================================
# SECURITY CHECK
# ==========================================

def check_login():
    """Verify user is logged in."""
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        st.error("⛔ Debe iniciar sesión para acceder al asistente IA")
        st.stop()
    return st.session_state.get('user')


# ==========================================
# JWT TOKEN MANAGEMENT
# ==========================================

def get_api_token() -> str:
    """
    Get a valid JWT token for API authentication.
    
    Uses the current user's session token stored in st.session_state.
    If no token exists, returns None and the user must log in.
    """
    # Check if we have a cached valid token from user's session
    if 'api_token' in st.session_state and st.session_state.api_token:
        return st.session_state.api_token
    
    # No token available - user needs to log in via main app
    logger.warning("No API token available - user must log in via main app")
    return None


def refresh_token():
    """Force refresh the API token."""
    st.session_state.api_token = None
    st.warning("⚠️ Token expirado. Por favor cierre sesión e inicie sesión nuevamente.")


# ==========================================
# API COMMUNICATION
# ==========================================

def check_api_status() -> dict:
    """Check if the AI agent API is available."""
    try:
        response = _s.get(AGENT_STATUS_URL, timeout=5)
        if response.status_code == 200:
            return response.json()
        return {"status": "error", "error": f"HTTP {response.status_code}"}
    except requests.RequestException as e:
        return {"status": "offline", "error": str(e)}


def send_query(prompt: str, token: str) -> dict:
    """
    Send a query to the AI agent.
    
    Requires valid JWT token for authentication.
    Returns dict with 'success', 'response', 'error' keys.
    """
    if not token:
        return {"success": False, "error": "auth_error", "message": "No hay token de autenticación"}
    
    try:
        response = _s.post(
            AGENT_QUERY_URL,
            json={"prompt": prompt},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120  # Long timeout for LLM processing
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "response": data.get("response", ""),
                "tools_used": data.get("tools_used", []),
                "model": data.get("model", "unknown")
            }
        elif response.status_code == 401:
            return {"success": False, "error": "auth_error", "message": "Token inválido o expirado"}
        elif response.status_code == 503:
            return {"success": False, "error": "ollama_error", "message": "El cerebro del hotel está durmiendo (Ollama off)"}
        else:
            error_detail = ""
            try:
                error_detail = response.json().get("detail", "")
            except:
                pass
            return {"success": False, "error": "api_error", "message": f"Error del servidor: {response.status_code}. {error_detail}"}
            
    except requests.Timeout:
        return {"success": False, "error": "timeout", "message": "La consulta tardó demasiado. Intenta de nuevo."}
    except requests.RequestException as e:
        return {"success": False, "error": "connection_error", "message": f"Error de conexión: {str(e)}"}


# ==========================================
# MAIN PAGE
# ==========================================

# Check login
user = check_login()

# Initialize chat history
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# ==========================================
# SIDEBAR
# ==========================================

with st.sidebar:
    st.markdown("### 💬 Asistente IA")
    st.caption(f"Usuario: **{user.username}**")
    
    st.divider()
    
    # API Status indicator
    status = check_api_status()
    if status.get("status") == "online":
        st.success("🟢 Conectado")
        st.caption(f"Modelo: {status.get('model', 'N/A')}")
    elif status.get("status") == "offline":
        st.error("🔴 Desconectado")
        st.caption("Ollama no está ejecutándose")
    else:
        st.warning("🟡 Estado desconocido")
    
    st.divider()
    
    # Reset chat button
    if st.button("🗑️ Reiniciar Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    
    # Token refresh button (for debugging)
    with st.expander("🔧 Opciones avanzadas"):
        if st.button("🔄 Refrescar Token"):
            refresh_token()
            st.success("Token actualizado")
        
        # Show current token status
        if st.session_state.get('api_token'):
            st.caption("✅ Token activo")
        else:
            st.caption("❌ Sin token")


# ==========================================
# CHAT INTERFACE
# ==========================================

st.title("💬 Asistente IA del Hotel")
st.caption("Pregunta sobre reservas, disponibilidad, huéspedes y más")

# Display chat history
for message in st.session_state.chat_history:
    role = message["role"]
    content = message["content"]
    timestamp = message.get("timestamp", "")
    
    with st.chat_message(role):
        st.markdown(content)
        if timestamp:
            st.caption(timestamp)

# Chat input
if prompt := st.chat_input("Escribe tu consulta..."):
    # Add user message to history
    user_timestamp = datetime.now().strftime("%H:%M")
    st.session_state.chat_history.append({
        "role": "user",
        "content": prompt,
        "timestamp": user_timestamp
    })
    
    # Display user message immediately
    with st.chat_message("user"):
        st.markdown(prompt)
        st.caption(user_timestamp)
    
    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Pensando... 🤔"):
            # Get JWT token using service account
            token = get_api_token()
            
            if not token:
                response_text = "❌ **Error de autenticación.** No se pudo conectar con la cuenta de servicio."
                st.error(response_text)
            else:
                # Send query with token
                result = send_query(prompt, token)
                
                if result["success"]:
                    response_text = result["response"]
                    st.markdown(response_text)
                    
                    # Show tools used (optional, for transparency)
                    tools = result.get("tools_used", [])
                    if tools and tools != ["direct"]:
                        st.caption(f"🔧 Herramientas usadas: {', '.join(tools)}")
                else:
                    # Handle different errors
                    error_type = result.get("error", "unknown")
                    error_msg = result.get("message", "Error desconocido")
                    
                    if error_type == "auth_error":
                        response_text = f"🔐 **Error de autenticación.** {error_msg}"
                        st.error(response_text)
                        # Refresh token for next attempt
                        refresh_token()
                    elif error_type == "ollama_error":
                        response_text = "😴 **El cerebro del hotel está durmiendo.** Ollama no está disponible."
                        st.warning(response_text)
                    else:
                        response_text = f"⚠️ **Error:** {error_msg}"
                        st.error(response_text)
        
        # Add timestamp to response
        ai_timestamp = datetime.now().strftime("%H:%M")
        st.caption(ai_timestamp)
    
    # Add AI response to history
    st.session_state.chat_history.append({
        "role": "assistant",
        "content": response_text,
        "timestamp": ai_timestamp
    })


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption("💡 **Tip:** Puedes preguntar sobre disponibilidad, precios, estado del hotel y buscar huéspedes.")
