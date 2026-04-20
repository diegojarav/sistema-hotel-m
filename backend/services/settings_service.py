from sqlalchemy.orm import Session
from services._base import with_db

from logging_config import get_logger

logger = get_logger(__name__)


class SettingsService:
    """Service for system-wide settings management (White Label support)."""

    DEFAULT_HOTEL_NAME = "Mi Hotel"

    @staticmethod
    @with_db
    def get_hotel_name(db: Session = None) -> str:
        """
        Returns the stored hotel name or default if not set.

        Returns:
            Hotel name string
        """
        from database import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.setting_key == "hotel_name").first()
        return setting.setting_value if setting and setting.setting_value else SettingsService.DEFAULT_HOTEL_NAME

    @staticmethod
    @with_db
    def get_parking_capacity(db: Session = None) -> int:
        """Returns the max parking slots (default 5)."""
        from database import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.setting_key == "parking_capacity").first()
        try:
            return int(setting.setting_value) if setting else 5
        except:
            return 5

    @staticmethod
    @with_db
    def set_parking_capacity(db: Session, capacity: int) -> bool:
        """Updates max parking slots."""
        from database import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.setting_key == "parking_capacity").first()
        if setting:
            setting.setting_value = str(capacity)
        else:
            import uuid
            db.add(SystemSetting(
                id=str(uuid.uuid4()),
                property_id="los-monges",
                setting_key="parking_capacity",
                setting_value=str(capacity)
            ))
        db.commit()
        return True

    @staticmethod
    @with_db
    def set_hotel_name(db: Session, name: str) -> bool:
        """
        Updates or creates the hotel name setting.

        Args:
            name: New hotel name

        Returns:
            True if successful
        """
        from database import SystemSetting
        setting = db.query(SystemSetting).filter(SystemSetting.setting_key == "hotel_name").first()
        if setting:
            setting.setting_value = name
        else:
            # Create new setting with required fields
            import uuid
            db.add(SystemSetting(
                id=str(uuid.uuid4()),
                property_id="los-monges",  # Default property
                setting_key="hotel_name",
                setting_value=name
            ))
        db.commit()
        logger.info(f"Hotel name updated to: {name}")
        return True

    @staticmethod
    @with_db
    def get_property_settings(db: Session, property_id: str = "los-monges") -> dict:
        """Get property settings: check-in/out times and breakfast policy."""
        from database import Property
        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            return {
                "check_in_start": "07:00",
                "check_in_end": "22:00",
                "check_out_time": "10:00",
                "breakfast_included": False
            }
        return {
            "check_in_start": prop.check_in_start or "07:00",
            "check_in_end": prop.check_in_end or "22:00",
            "check_out_time": prop.check_out_time or "10:00",
            "breakfast_included": bool(prop.breakfast_included)
        }

    # ==================================================================
    # v1.7.0 — Meal service configuration (Phase 4)
    # ==================================================================
    VALID_MEAL_MODES = {"INCLUIDO", "OPCIONAL_PERSONA", "OPCIONAL_HABITACION"}

    @staticmethod
    @with_db
    def get_meals_config(db: Session = None, property_id: str = "los-monges") -> dict:
        """Return the hotel's meal service configuration.

        Shape: {meals_enabled: bool, meal_inclusion_mode: str|None}

        Hotels that don't serve meals see `meals_enabled=False` and should
        hide ALL meal-related UI. The mode is only meaningful when enabled.
        """
        from database import Property
        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            return {"meals_enabled": False, "meal_inclusion_mode": None}
        return {
            "meals_enabled": bool(prop.meals_enabled or 0),
            "meal_inclusion_mode": prop.meal_inclusion_mode,
        }

    @staticmethod
    @with_db
    def set_meals_config(
        db: Session,
        meals_enabled: bool,
        meal_inclusion_mode: str = None,
        property_id: str = "los-monges",
    ) -> dict:
        """Update the hotel's meal service config and seed system plans.

        When enabling or changing mode, `MealPlanService.seed_system_plans`
        is called to ensure SOLO_HABITACION (always) and CON_DESAYUNO
        (for INCLUIDO) exist.
        """
        from database import Property
        # Validate mode
        if meals_enabled and meal_inclusion_mode not in SettingsService.VALID_MEAL_MODES:
            raise ValueError(
                f"meal_inclusion_mode debe ser uno de {SettingsService.VALID_MEAL_MODES} "
                f"cuando meals_enabled=True"
            )

        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            raise ValueError(f"Property no encontrada: {property_id}")

        prop.meals_enabled = 1 if meals_enabled else 0
        prop.meal_inclusion_mode = meal_inclusion_mode if meals_enabled else None
        db.commit()

        # Seed system plans (idempotent)
        if meals_enabled:
            from services.meal_plan_service import MealPlanService
            MealPlanService.seed_system_plans(
                db=db, property_id=property_id, mode=meal_inclusion_mode
            )

        logger.info(
            f"Meals config updated for {property_id}: enabled={meals_enabled}, mode={meal_inclusion_mode}"
        )
        return {
            "meals_enabled": bool(prop.meals_enabled),
            "meal_inclusion_mode": prop.meal_inclusion_mode,
        }
