"""
Frontend PC - API Service Layer
================================

Helper functions for communicating with the Hotel API.
"""

import requests
import os

# API base URL - defaults to localhost for development
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")


def get_hotel_config() -> dict:
    """
    Fetch hotel configuration from API.
    
    Returns:
        Dict with 'hotel_name' key
    """
    try:
        response = requests.get(
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
        response = requests.post(
            f"{API_BASE}/api/v1/settings/hotel-name",
            json={"name": name},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        return response.ok
    except requests.RequestException:
        return False
