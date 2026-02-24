from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import Room, RoomCategory, ClientType, PricingSeason
from typing import List, Dict, Any
from datetime import date

from logging_config import get_logger
from services._base import with_db

logger = get_logger(__name__)


class PricingService:
    """Service for dynamic price calculation."""

    @staticmethod
    @with_db
    def calculate_price(
        db: Session,
        property_id: str,
        category_id: str,
        check_in: date,
        stay_days: int,
        client_type_id: str,
        room_id: str = None
    ) -> Dict[str, Any]:
        """
        Calculates the final price with all modifiers.

        Args:
            property_id: Property ID
            category_id: Room Category ID
            check_in: Check-in date
            stay_days: Number of nights
            client_type_id: Client Type ID
            room_id: Optional, to check for custom room price

        Returns:
            Dict with final_price, currency, breakdown_json, etc.
        """
        # 1. Base Price (Category or Room Custom)
        base_price = 0.0
        if room_id:
            room = db.query(Room).filter(Room.id == room_id).first()
            if room and room.custom_price:
                base_price = room.custom_price

        if base_price == 0.0:
            cat = db.query(RoomCategory).filter(RoomCategory.id == category_id).first()
            if not cat:
                return {
                    "final_price": 0.0,
                    "currency": "PYG",
                    "breakdown": {
                        "base_unit_price": 0.0,
                        "base_total": 0.0,
                        "nights": stay_days,
                        "modifiers": []
                    }
                }
            base_price = cat.base_price

        # 2. Calculate Base Total (Price * Nights)
        total_base = base_price * stay_days

        breakdown = {
            "base_unit_price": base_price,
            "nights": stay_days,
            "base_total": total_base,
            "modifiers": []
        }

        current_total = total_base

        # 3. Client Type Discount
        client_type = db.query(ClientType).filter(ClientType.id == client_type_id).first()
        if client_type:
            discount_pct = client_type.default_discount_percent
            if discount_pct > 0:
                discount_amount = total_base * (discount_pct / 100)
                current_total -= discount_amount
                breakdown["modifiers"].append({
                    "name": f"Descuento Cliente: {client_type.name}",
                    "percent": -discount_pct,
                    "amount": -discount_amount
                })

        # 4. Seasonal Pricing
        seasons = db.query(PricingSeason).filter(
            PricingSeason.property_id == property_id,
            PricingSeason.active == 1,
            PricingSeason.start_date <= check_in,
            PricingSeason.end_date >= check_in
        ).order_by(desc(PricingSeason.priority)).all()

        if seasons:
            # Take highest priority season active at check-in
            season = seasons[0]
            modifier = season.price_modifier

            season_adjustment = total_base * (modifier - 1.0)
            current_total += season_adjustment

            pct_change = (modifier - 1.0) * 100
            breakdown["modifiers"].append({
                "name": f"Temporada: {season.name}",
                "percent": pct_change,
                "amount": season_adjustment
            })

        # 5. Final Rounding
        final_price = max(0, current_total)

        breakdown["final_price"] = final_price

        return {
            "final_price": final_price,
            "currency": "PYG",
            "breakdown": breakdown
        }

    @staticmethod
    @with_db
    def get_client_types(db: Session, property_id: str = "los-monges") -> List[Dict]:
        """Get all active client types."""
        types = db.query(ClientType).filter(
            ClientType.property_id == property_id,
            ClientType.active == 1
        ).order_by(ClientType.sort_order).all()

        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description or "",
                "default_discount_percent": t.default_discount_percent,
                "requires_contract": t.requires_contract,
                "color": t.color or "#6B7280",
                "icon": t.icon or "user"
            }
            for t in types
        ]
