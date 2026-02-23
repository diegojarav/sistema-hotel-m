"""
Phase 2 — Service-layer tests for AuthService (PC/Streamlit path).

Tests AuthService.authenticate, AuthService.login, AuthService.close_user_sessions
by passing db_session directly (mimics @with_db behavior for FastAPI mode).
"""

import pytest
from datetime import date, timedelta

from services.auth_service import AuthService
from database import SessionLog


# ==========================================
# AuthService.authenticate
# ==========================================

class TestAuthenticate:
    """Tests for AuthService.authenticate(db, username, password)."""

    def test_valid_credentials_returns_user_dto(self, db_session, seed_users):
        """Valid username + password returns a UserDTO with correct fields."""
        result = AuthService.authenticate(db_session, "admin", "admin123")
        assert result is not None
        assert result.username == "admin"
        assert result.role == "admin"
        assert result.real_name == "Admin User"

    def test_valid_credentials_recepcionista(self, db_session, seed_users):
        """Recepcionista user authenticates correctly."""
        result = AuthService.authenticate(db_session, "recepcion", "recep123")
        assert result is not None
        assert result.username == "recepcion"
        assert result.role == "recepcionista"

    def test_invalid_password_returns_none(self, db_session, seed_users):
        """Correct username but wrong password returns None."""
        result = AuthService.authenticate(db_session, "admin", "wrong_password")
        assert result is None

    def test_nonexistent_user_returns_none(self, db_session, seed_users):
        """Username that does not exist returns None."""
        result = AuthService.authenticate(db_session, "ghost_user", "any_password")
        assert result is None


# ==========================================
# AuthService.login
# ==========================================

class TestLogin:
    """Tests for AuthService.login(db, username, password, ...)."""

    def test_login_returns_token_dict(self, db_session, seed_users):
        """Successful login returns dict with access_token, refresh_token, token_type."""
        result = AuthService.login(db_session, "admin", "admin123")
        assert result is not None
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"

    def test_login_creates_session_log(self, db_session, seed_users):
        """Login creates a SessionLog record in the database."""
        AuthService.login(db_session, "admin", "admin123")
        logs = db_session.query(SessionLog).filter(SessionLog.username == "admin").all()
        assert len(logs) == 1
        assert logs[0].status == "active"

    def test_login_session_fields(self, db_session, seed_users):
        """SessionLog captures ip_address, user_agent, device_type, status."""
        AuthService.login(
            db_session,
            "admin",
            "admin123",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 TestBrowser",
            device_type="Mobile",
        )
        log = db_session.query(SessionLog).filter(SessionLog.username == "admin").first()
        assert log is not None
        assert log.ip_address == "192.168.1.100"
        assert log.user_agent == "Mozilla/5.0 TestBrowser"
        assert log.device_type == "Mobile"
        assert log.status == "active"

    def test_login_bad_credentials_returns_none(self, db_session, seed_users):
        """Login with wrong password returns None and creates no session."""
        result = AuthService.login(db_session, "admin", "bad_password")
        assert result is None
        logs = db_session.query(SessionLog).filter(SessionLog.username == "admin").all()
        assert len(logs) == 0


# ==========================================
# AuthService.close_user_sessions
# ==========================================

class TestCloseUserSessions:
    """Tests for AuthService.close_user_sessions(db, username, reason)."""

    def test_closes_active_sessions_returns_count(self, db_session, seed_users):
        """Closing sessions for a user with 2 active sessions returns 2."""
        AuthService.login(db_session, "admin", "admin123")
        AuthService.login(db_session, "admin", "admin123")

        count = AuthService.close_user_sessions(db_session, "admin", reason="password_reset")
        assert count == 2

        # Verify all are now closed
        active = db_session.query(SessionLog).filter(
            SessionLog.username == "admin",
            SessionLog.status == "active",
        ).count()
        assert active == 0

    def test_close_no_sessions_returns_zero(self, db_session, seed_users):
        """Closing sessions when none exist returns 0."""
        count = AuthService.close_user_sessions(db_session, "admin")
        assert count == 0

    def test_close_sets_reason(self, db_session, seed_users):
        """closed_reason is set on the SessionLog records."""
        AuthService.login(db_session, "admin", "admin123")
        AuthService.close_user_sessions(db_session, "admin", reason="admin_action")

        log = db_session.query(SessionLog).filter(SessionLog.username == "admin").first()
        assert log.closed_reason == "admin_action"
        assert log.status == "closed"
        assert log.logout_time is not None
