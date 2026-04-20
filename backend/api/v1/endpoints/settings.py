"""
Hotel API - System Settings Endpoints
======================================

Endpoints for managing system-wide configuration (White Label support).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db, require_role
from logging_config import get_logger
from database import User

logger = get_logger(__name__)
from services import SettingsService

router = APIRouter()


# ==========================================
# SCHEMAS
# ==========================================

class HotelNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Nombre del hotel")


class HotelNameResponse(BaseModel):
    hotel_name: str


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "/hotel-name",
    response_model=HotelNameResponse,
    summary="Get Hotel Name",
    description="Obtiene el nombre del hotel configurado. Endpoint público."
)
def get_hotel_name(db: Session = Depends(get_db)):
    """Get current hotel name (public endpoint - no auth required)."""
    hotel_name = SettingsService.get_hotel_name(db=db)
    return HotelNameResponse(hotel_name=hotel_name)


@router.post(
    "/hotel-name",
    response_model=HotelNameResponse,
    summary="Update Hotel Name",
    description="Actualiza el nombre del hotel. Requiere autenticación."
)
def set_hotel_name(
    request: HotelNameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Update hotel name. Requires admin role."""
    try:
        SettingsService.set_hotel_name(db=db, name=request.name)
        return HotelNameResponse(hotel_name=request.name)
    except Exception as e:
        logger.error(f"Error updating hotel name: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la configuracion."
        )


# ==========================================
# PARKING CONFIGURATION
# ==========================================

class ParkingCapacityRequest(BaseModel):
    capacity: int = Field(..., ge=0, description="Capacidad total de estacionamiento")

class ParkingCapacityResponse(BaseModel):
    parking_capacity: int

@router.get(
    "/parking-capacity",
    response_model=ParkingCapacityResponse,
    summary="Get Parking Capacity",
    description="Obtiene la capacidad máxima de estacionamiento."
)
def get_parking_capacity(db: Session = Depends(get_db)):
    cap = SettingsService.get_parking_capacity(db=db)
    return ParkingCapacityResponse(parking_capacity=cap)

@router.post(
    "/parking-capacity",
    response_model=ParkingCapacityResponse,
    summary="Set Parking Capacity",
    description="Actualiza la capacidad de estacionamiento. Requiere autenticación."
)
def set_parking_capacity(
    request: ParkingCapacityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Update parking capacity. Requires admin role."""
    SettingsService.set_parking_capacity(db=db, capacity=request.capacity)
    return ParkingCapacityResponse(parking_capacity=request.capacity)


# ==========================================
# PROPERTY SETTINGS (Check-in/out, Breakfast)
# ==========================================

class PropertySettingsResponse(BaseModel):
    check_in_start: str
    check_in_end: str
    check_out_time: str
    breakfast_included: bool


@router.get(
    "/property-settings",
    response_model=PropertySettingsResponse,
    summary="Get Property Settings",
    description="Check-in/check-out times and breakfast policy. Public endpoint."
)
def get_property_settings(db: Session = Depends(get_db)):
    """Get property configuration (check-in/out times, breakfast policy)."""
    settings = SettingsService.get_property_settings(db=db)
    return PropertySettingsResponse(**settings)


# ==========================================
# v1.7.0 — MEALS CONFIGURATION (Phase 4)
# ==========================================

class MealsConfigResponse(BaseModel):
    meals_enabled: bool
    meal_inclusion_mode: Optional[str] = None  # INCLUIDO | OPCIONAL_PERSONA | OPCIONAL_HABITACION


class MealsConfigRequest(BaseModel):
    meals_enabled: bool
    meal_inclusion_mode: Optional[str] = Field(
        None,
        description="INCLUIDO | OPCIONAL_PERSONA | OPCIONAL_HABITACION (required when meals_enabled=True)"
    )


@router.get(
    "/meals-config",
    response_model=MealsConfigResponse,
    summary="Get Meals Configuration",
    description="Hotel meal service configuration (enabled flag + inclusion mode). Public endpoint."
)
def get_meals_config(db: Session = Depends(get_db)):
    """Return the hotel's meal service config. Public so mobile can conditionally
    render UI widgets without logging in."""
    cfg = SettingsService.get_meals_config(db=db)
    return MealsConfigResponse(**cfg)


@router.put(
    "/meals-config",
    response_model=MealsConfigResponse,
    summary="Update Meals Configuration",
    description="Enable/disable meal service and set inclusion mode. Admin-only."
)
def set_meals_config(
    request: MealsConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Update the hotel's meal service config. Seeds system plans when enabling."""
    try:
        cfg = SettingsService.set_meals_config(
            db=db,
            meals_enabled=request.meals_enabled,
            meal_inclusion_mode=request.meal_inclusion_mode,
        )
        return MealsConfigResponse(**cfg)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating meals config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la configuración de comidas."
        )
