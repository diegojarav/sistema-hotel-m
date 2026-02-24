"""
Hotel Munich - Reactive Caching Service
========================================

Provides cached wrappers for expensive database queries.
Uses Streamlit's @st.cache_data with TTL for automatic refresh.

IMPORTANT: Call force_refresh() after ANY write operation to guarantee
the user sees their changes immediately.
"""

import streamlit as st
from typing import Dict, List
from datetime import date

# Import services from backend
from services import ReservationService

# ==========================================
# CACHED QUERY WRAPPERS
# ==========================================

@st.cache_data(ttl=60, show_spinner=False)
def get_occupancy_map_cached(year: int, month: int) -> Dict[str, Dict]:
    """
    Cached wrapper for ReservationService.get_occupancy_map.
    
    TTL: 60 seconds - auto-refreshes every minute.
    Call force_refresh() after creating/updating reservations.
    """
    return ReservationService.get_occupancy_map(year, month)


@st.cache_data(ttl=60, show_spinner=False)
def get_all_reservations_cached() -> List:
    """
    Cached wrapper for ReservationService.get_all_reservations.
    
    TTL: 60 seconds - auto-refreshes every minute.
    Call force_refresh() after creating/updating reservations.
    """
    return ReservationService.get_all_reservations()


@st.cache_data(ttl=120, show_spinner=False)
def get_all_guest_names_cached() -> List[str]:
    """
    Cached wrapper for GuestService.get_all_guest_names.
    
    TTL: 120 seconds - guest list changes less frequently.
    """
    from services import GuestService
    return GuestService.get_all_guest_names()


# ==========================================
# CACHE CONTROL
# ==========================================

def force_refresh():
    """
    Clear all cached data to force immediate refresh.
    
    MUST be called after any write operation:
    - Creating a reservation
    - Updating a reservation
    - Cancelling a reservation
    - Registering a check-in
    
    This ensures the user sees their changes instantly.
    """
    st.cache_data.clear()


def refresh_reservations_only():
    """
    Clear only reservation-related caches.
    More targeted than force_refresh().
    """
    get_occupancy_map_cached.clear()
    get_all_reservations_cached.clear()
