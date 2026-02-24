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
