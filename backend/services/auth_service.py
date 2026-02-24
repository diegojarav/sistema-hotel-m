from sqlalchemy.orm import Session
from database import User, SessionLog
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from logging_config import get_logger
from schemas import UserDTO
from services._base import with_db

logger = get_logger(__name__)


class AuthService:
    """Service for user authentication."""

    @staticmethod
    @with_db
    def authenticate(db: Session, username: str, password: str) -> Optional[UserDTO]:
        """
        Verifies user credentials.

        Supports both:
        - Legacy plaintext passwords (for existing users)
        - Bcrypt hashed passwords (for new/migrated users)

        Args:
            username: The username.
            password: The password to verify.

        Returns:
            UserDTO if successful, None otherwise.
        """
        # Import here to avoid circular dependency
        from api.core.security import verify_password

        user = db.query(User).filter(User.username == username).first()
        if user and verify_password(password, user.password):
            return UserDTO(username=user.username, role=user.role, real_name=user.real_name)
        return None

    @staticmethod
    @with_db
    def login(
        db: Session,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: str = "",
        device_type: str = "PC"
    ) -> Optional[Dict[str, Any]]:
        """
        Full login flow: verify credentials, create session, generate tokens.

        Returns dict with access_token, refresh_token, token_type or None if invalid.
        """
        import uuid
        from api.core.security import verify_password, create_access_token, create_refresh_token
        from api.core.config import ACCESS_TOKEN_EXPIRE_MINUTES

        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password):
            return None

        # Create session
        session_id = str(uuid.uuid4())
        session_log = SessionLog(
            session_id=session_id,
            username=user.username,
            login_time=datetime.now(),
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type,
            status="active"
        )
        db.add(session_log)
        db.commit()

        # Generate tokens
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "sid": session_id},
            expires_delta=access_token_expires
        )
        refresh_token = create_refresh_token(
            data={"sub": user.username, "sid": session_id}
        )

        logger.info(f"User '{user.username}' logged in from {device_type} ({ip_address})")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    @staticmethod
    @with_db
    def close_user_sessions(db: Session, username: str, reason: str = "admin_action") -> int:
        """
        Close all active sessions for a user.
        Used for JWT revocation on password reset or user deletion.

        Returns number of sessions closed.
        """
        updated = db.query(SessionLog).filter(
            SessionLog.username == username,
            SessionLog.status == "active"
        ).update({
            "status": "closed",
            "logout_time": datetime.now(),
            "closed_reason": reason
        })
        db.commit()
        logger.info(f"Closed {updated} session(s) for user '{username}' (reason: {reason})")
        return updated
