from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_db
from services import PricingService
from typing import List
from schemas import (
    PriceCalculationRequest, PriceCalculationResponse,
    ClientTypeDTO, PricingSeasonDTO
)
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

@router.get("/client-types", response_model=List[ClientTypeDTO])
def get_client_types_list(db: Session = Depends(get_db)):
    """
    Get list of active client types for selection.
    """
    try:
        return PricingService.get_client_types(db)
    except Exception as e:
        logger.error(f"Error fetching client types: {e}")
        raise HTTPException(status_code=500, detail="Error fetching client types")

@router.get("/seasons", response_model=List[PricingSeasonDTO])
def get_seasons_list(db: Session = Depends(get_db)):
    """
    Get list of active pricing seasons for manual override selection.
    """
    try:
        return PricingService.get_seasons(db)
    except Exception as e:
        logger.error(f"Error fetching seasons: {e}")
        raise HTTPException(status_code=500, detail="Error fetching seasons")

@router.post("/calculate", response_model=PriceCalculationResponse)
def calculate_price(
    request: PriceCalculationRequest,
    db: Session = Depends(get_db)
):
    """
    Calculate dynamic price for a reservation based on rules.
    """
    try:
        result = PricingService.calculate_price(
            db,
            property_id=request.property_id,
            category_id=request.category_id,
            check_in=request.check_in,
            stay_days=request.stay_days,
            client_type_id=request.client_type_id,
            room_id=request.room_id,
            season_id=request.season_id,
            meal_plan_id=request.meal_plan_id,
            breakfast_guests=request.breakfast_guests,
        )
        return result
    except ValueError as e:
        logger.warning(f"Pricing validation error: {e}")
        raise HTTPException(status_code=400, detail="Datos de precio invalidos. Verifique los parametros.")
    except Exception as e:
        logger.error(f"Pricing calculation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
