"""
Hotel API — Meal Plans Endpoints (v1.7.0 — Phase 4)
====================================================

CRUD for meal plans (breakfast, half-board, full-board, etc.). Admin-only
writes; any authenticated user can list (used by the reservation form).
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db, require_role
from database import User
from logging_config import get_logger
from services import MealPlanService, MealPlanError

logger = get_logger(__name__)
router = APIRouter()


# ==========================================
# SCHEMAS
# ==========================================

class MealPlanDTO(BaseModel):
    id: str
    property_id: str
    code: str
    name: str
    description: Optional[str] = None
    surcharge_per_person: float
    surcharge_per_room: float
    applies_to_mode: str
    is_system: bool
    is_active: bool
    sort_order: int


class MealPlanCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    surcharge_per_person: float = Field(0.0, ge=0)
    surcharge_per_room: float = Field(0.0, ge=0)
    applies_to_mode: str = Field(
        "ANY",
        pattern="^(ANY|INCLUIDO|OPCIONAL_PERSONA|OPCIONAL_HABITACION)$",
    )
    sort_order: int = 0


class MealPlanUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    surcharge_per_person: Optional[float] = Field(None, ge=0)
    surcharge_per_room: Optional[float] = Field(None, ge=0)
    applies_to_mode: Optional[str] = Field(
        None,
        pattern="^(ANY|INCLUIDO|OPCIONAL_PERSONA|OPCIONAL_HABITACION)$",
    )
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ==========================================
# ENDPOINTS
# ==========================================

@router.get(
    "",
    response_model=List[MealPlanDTO],
    summary="List Meal Plans",
    description="List active meal plans. Filter by mode to get plans valid under the current hotel configuration."
)
def list_meal_plans(
    mode: Optional[str] = Query(None, description="Filter by applies_to_mode (INCLUIDO | OPCIONAL_PERSONA | OPCIONAL_HABITACION)"),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all plans for the default property, optionally filtered by mode."""
    plans = MealPlanService.list_plans(
        db=db,
        mode_filter=mode,
        include_inactive=include_inactive,
    )
    return plans


@router.post(
    "",
    response_model=MealPlanDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create Meal Plan",
    description="Create a new meal plan. Admin-only."
)
def create_meal_plan(
    request: MealPlanCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    try:
        plan = MealPlanService.create_plan(
            db=db,
            property_id="los-monges",
            code=request.code.strip().upper(),
            name=request.name.strip(),
            description=request.description,
            surcharge_per_person=request.surcharge_per_person,
            surcharge_per_room=request.surcharge_per_room,
            applies_to_mode=request.applies_to_mode,
            sort_order=request.sort_order,
            is_system=False,
        )
        return plan
    except MealPlanError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put(
    "/{plan_id}",
    response_model=MealPlanDTO,
    summary="Update Meal Plan",
    description="Update fields on an existing meal plan. Admin-only. System plans cannot have their code changed."
)
def update_meal_plan(
    plan_id: str,
    request: MealPlanUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    try:
        updates = request.model_dump(exclude_unset=True)
        # Coerce is_active bool → int for ORM
        if "is_active" in updates:
            updates["is_active"] = 1 if updates["is_active"] else 0
        plan = MealPlanService.update_plan(db=db, plan_id=plan_id, **updates)
        return plan
    except MealPlanError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{plan_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate Meal Plan",
    description="Soft-delete a meal plan (is_active=False). System plans cannot be deleted. Admin-only."
)
def delete_meal_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    try:
        MealPlanService.soft_delete(db=db, plan_id=plan_id)
        return {"success": True, "detail": "Plan desactivado"}
    except MealPlanError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
