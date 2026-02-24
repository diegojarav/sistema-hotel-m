"""
Phase 4 — Service-layer tests for SettingsService.
"""

from services.settings_service import SettingsService


class TestHotelName:
    def test_default(self, db_session):
        name = SettingsService.get_hotel_name(db_session)
        assert name == "Mi Hotel"

    def test_set_and_get(self, db_session):
        SettingsService.set_hotel_name(db_session, "Los Monges")
        name = SettingsService.get_hotel_name(db_session)
        assert name == "Los Monges"

    def test_update_existing(self, db_session):
        SettingsService.set_hotel_name(db_session, "First")
        SettingsService.set_hotel_name(db_session, "Second")
        assert SettingsService.get_hotel_name(db_session) == "Second"


class TestParkingCapacity:
    def test_default(self, db_session):
        cap = SettingsService.get_parking_capacity(db_session)
        assert cap == 5

    def test_set_and_get(self, db_session):
        SettingsService.set_parking_capacity(db_session, 10)
        cap = SettingsService.get_parking_capacity(db_session)
        assert cap == 10

    def test_update_existing(self, db_session):
        SettingsService.set_parking_capacity(db_session, 8)
        SettingsService.set_parking_capacity(db_session, 12)
        assert SettingsService.get_parking_capacity(db_session) == 12


class TestPropertySettings:
    def test_defaults_without_property(self, db_session):
        settings = SettingsService.get_property_settings(db_session)
        assert settings["check_in_start"] == "07:00"
        assert settings["check_out_time"] == "10:00"
        assert settings["breakfast_included"] is False

    def test_with_property(self, db_session, seed_property):
        settings = SettingsService.get_property_settings(db_session)
        assert settings["check_in_start"] == "07:00"
        assert settings["check_in_end"] == "22:00"
        assert settings["check_out_time"] == "10:00"
        assert settings["breakfast_included"] is False
