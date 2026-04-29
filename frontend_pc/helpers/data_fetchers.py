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


# ==========================================
# v1.7.0 — Meal Plan helpers (Phase 4)
# ==========================================

@st.cache_data(ttl=30)
def get_meals_config(property_id: str = "los-monges") -> dict:
    """Fetch the hotel's meal service configuration.

    Returns ``{meals_enabled: bool, meal_inclusion_mode: str|None}``. When
    ``meals_enabled`` is False, callers MUST hide the entire meal plan UI to
    keep parity with the mobile app — hotels that don't serve meals never see
    the section.
    """
    try:
        from services import SettingsService
        return SettingsService.get_meals_config(property_id=property_id)
    except Exception as e:
        logger.error(f"Error fetching meals config: {e}")
        return {"meals_enabled": False, "meal_inclusion_mode": None}


@st.cache_data(ttl=30)
def get_meal_plans(mode_filter: str | None = None) -> list[dict]:
    """Fetch active meal plans, optionally filtered by hotel mode.

    Pass ``mode_filter`` to return only plans valid under the current hotel
    ``meal_inclusion_mode``. Plans with ``applies_to_mode='ANY'`` (e.g.
    SOLO_HABITACION) are always included regardless of the mode.
    """
    try:
        from services import MealPlanService
        return MealPlanService.list_plans(mode_filter=mode_filter)
    except Exception as e:
        logger.error(f"Error fetching meal plans: {e}")
        return []
