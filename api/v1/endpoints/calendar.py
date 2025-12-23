"""
Hotel Munich API - Calendar Endpoints
======================================

HYBRID MONOLITH: Imports from root services.py and schemas.py
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict

# Import from API deps
from api.deps import get_db

# IMPORT FROM ROOT - Single Source of Truth
from services import ReservationService
from schemas import CalendarEventDTO, TodaySummaryDTO

router = APIRouter()


@router.get(
    "/events",
    response_model=List[CalendarEventDTO],
    summary="Get Calendar Events",
    description="Get calendar events for a specific month. FullCalendar compatible."
)
def get_calendar_events(
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: Session = Depends(get_db)
):
    """Get calendar events for a month using original ReservationService."""
    return ReservationService.get_monthly_events(db, year, month)


@router.get(
    "/occupancy",
    response_model=Dict,
    summary="Get Occupancy Map",
    description="Get daily occupancy data for a month."
)
def get_occupancy_map(
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: Session = Depends(get_db)
):
    """Get occupancy map for native calendar rendering."""
    return ReservationService.get_occupancy_map(db, year, month)


@router.get(
    "/summary",
    response_model=TodaySummaryDTO,
    summary="Get Today's Summary",
    description="Get quick occupancy summary for today."
)
def get_today_summary(db: Session = Depends(get_db)):
    """Get today's occupancy summary using original ReservationService."""
    return ReservationService.get_today_summary(db)
