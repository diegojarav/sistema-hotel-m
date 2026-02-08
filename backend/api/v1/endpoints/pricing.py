from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_db
from services import PricingService
from typing import List
from schemas import PriceCalculationRequest, PriceCalculationResponse, ClientTypeDTO
from logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

@router.get("/client-types", response_model=List[ClientTypeDTO])
def get_client_types_list(db: Session = Depends(get_db)):
    """
    Get list of active client types for selection.
    """
    try:
        # PricingService.get_client_types is a cached list, 
        # but the service method might not accept db if it uses its own?
        # Check PricingService.get_client_types signature.
        # It is: @st.cache_data ... def get_client_types(). 
        # Wait, get_client_types in service calls database.
        # But app.py calls it without arguments.
        # Services use @with_db.
        # So I can call it without arguments.
        return PricingService.get_client_types()
    except Exception as e:
        logger.error(f"Error fetching client types: {e}")
        raise HTTPException(status_code=500, detail="Error fetching client types")

@router.post("/calculate", response_model=PriceCalculationResponse)
def calculate_price(
    request: PriceCalculationRequest,
    db: Session = Depends(get_db)
):
    """
    Calculate dynamic price for a reservation based on rules.
    """
    try:
        # Pass db explicitly to leverage dependency injection
        # The service method accepts db as first argument due to @with_db
        result = PricingService.calculate_price(
            db, # Passed as first arg
            property_id=request.property_id,
            category_id=request.category_id,
            check_in=request.check_in,
            stay_days=request.stay_days,
            client_type_id=request.client_type_id,
            room_id=request.room_id
        )
        return result
    except ValueError as e:
        logger.warning(f"Pricing validation error: {e}")
        raise HTTPException(status_code=400, detail="Datos de precio invalidos. Verifique los parametros.")
    except Exception as e:
        logger.error(f"Pricing calculation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
