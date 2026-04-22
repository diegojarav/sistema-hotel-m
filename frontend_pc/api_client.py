"""
Frontend PC - API Service Layer
================================

Helper functions for communicating with the Hotel API.
Uses a shared requests.Session() for TCP connection reuse (PERF-10).
"""

import requests
import os

# API base URL - defaults to localhost for development
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

# Shared session for connection pooling (PERF-10)
_session = requests.Session()
_session.headers.update({"Content-Type": "application/json"})


def get_session() -> requests.Session:
    """Return the shared requests.Session for admin pages to reuse."""
    return _session


def get_hotel_config() -> dict:
    """
    Fetch hotel configuration from API.

    Returns:
        Dict with 'hotel_name' key
    """
    try:
        response = _session.get(
            f"{API_BASE}/api/v1/settings/hotel-name",
            timeout=5
        )
        if response.ok:
            return response.json()
    except requests.RequestException:
        pass

    # Return default if API unavailable
    return {"hotel_name": "Mi Hotel"}


def set_hotel_name(name: str, token: str) -> bool:
    """
    Update hotel name via API.

    Args:
        name: New hotel name
        token: JWT authentication token

    Returns:
        True if successful, False otherwise
    """
    try:
        response = _session.post(
            f"{API_BASE}/api/v1/settings/hotel-name",
            json={"name": name},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        return response.ok
    except requests.RequestException:
        return False


# ==========================================
# v1.8.0 — Email / SMTP helpers (Phase 5)
# ==========================================

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_smtp_config(token: str) -> dict:
    """Fetch current SMTP config (password never exposed — see `smtp_password_set` flag)."""
    try:
        r = _session.get(f"{API_BASE}/api/v1/settings/email", headers=_auth(token), timeout=5)
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return {}


def save_smtp_config(payload: dict, token: str) -> tuple[bool, str]:
    """Upsert SMTP config. Returns (success, message)."""
    try:
        r = _session.put(
            f"{API_BASE}/api/v1/settings/email",
            json=payload,
            headers=_auth(token),
            timeout=10,
        )
        if r.ok:
            return True, "Configuración guardada correctamente."
        return False, r.json().get("detail", f"Error {r.status_code}")
    except requests.RequestException as e:
        return False, f"No se pudo conectar al backend: {e}"


def test_smtp(email: str, token: str) -> tuple[bool, str]:
    """Send a test email using the saved SMTP config. Returns (success, message)."""
    try:
        r = _session.post(
            f"{API_BASE}/api/v1/settings/email/test",
            json={"email": email},
            headers=_auth(token),
            timeout=30,
        )
        if r.ok:
            data = r.json()
            return bool(data.get("success")), str(data.get("message", ""))
        return False, r.json().get("detail", f"Error {r.status_code}")
    except requests.RequestException as e:
        return False, f"No se pudo conectar al backend: {e}"


def send_reservation_email(reserva_id: str, email: str | None, token: str) -> tuple[bool, str]:
    """POST /email/reserva/{id}/enviar. Returns (success, message)."""
    try:
        r = _session.post(
            f"{API_BASE}/api/v1/email/reserva/{reserva_id}/enviar",
            json={"email": email} if email else {},
            headers=_auth(token),
            timeout=15,
        )
        if r.status_code == 202:
            return True, "Envío encolado. Puede tardar unos segundos."
        if r.status_code == 429:
            return False, r.json().get("detail", "Límite de reenvíos alcanzado.")
        return False, r.json().get("detail", f"Error {r.status_code}")
    except requests.RequestException as e:
        return False, f"No se pudo conectar al backend: {e}"


def get_email_history(reserva_id: str, token: str) -> list:
    """GET /email/reserva/{id}/historial. Returns list of email_log dicts (newest first)."""
    try:
        r = _session.get(
            f"{API_BASE}/api/v1/email/reserva/{reserva_id}/historial",
            headers=_auth(token),
            timeout=5,
        )
        if r.ok:
            return r.json() or []
    except requests.RequestException:
        pass
    return []
