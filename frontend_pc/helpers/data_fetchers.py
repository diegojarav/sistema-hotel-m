import streamlit as st
from logging_config import get_logger
from services import RoomService, PricingService

logger = get_logger(__name__)


@st.cache_data(ttl=60)
def get_room_categories():
    """Fetch room categories from database with pricing."""
    try:
        return RoomService.get_all_categories()
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return []


@st.cache_data(ttl=30)
def get_available_rooms_for_dates(check_in_str: str, check_out_str: str, category_id: str = None):
    """Fetch available rooms for date range with conflict detection."""
    try:
        from datetime import datetime
        check_in = datetime.strptime(check_in_str, "%Y-%m-%d").date()
        check_out = datetime.strptime(check_out_str, "%Y-%m-%d").date()
        return RoomService.get_available_rooms(check_in, check_out, category_id)
    except Exception as e:
        logger.error(f"Error fetching available rooms: {e}")
        return []


@st.cache_data(ttl=60)
def get_all_rooms_list():
    """Fetch all active rooms from database."""
    try:
        return RoomService.get_all_rooms()
    except Exception as e:
        logger.error(f"Error fetching rooms: {e}")
        return []


@st.cache_data(ttl=60)
def get_client_types():
    """Fetch active client types."""
    try:
        return PricingService.get_client_types()
    except Exception as e:
        logger.error(f"Error fetching client types: {e}")
        return []


@st.cache_data(ttl=60)
def get_seasons():
    """Fetch active pricing seasons for manual override."""
    try:
        return PricingService.get_seasons()
    except Exception as e:
        logger.error(f"Error fetching seasons: {e}")
        return []
