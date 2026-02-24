import streamlit as st
from datetime import datetime
import uuid
from database import SessionLocal, SessionLog
from logging_config import get_logger

logger = get_logger(__name__)


def log_login(username: str) -> str:
    """Log user login and return session_id."""
    session_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        log_entry = SessionLog(
            session_id=session_id,
            username=username,
            login_time=datetime.now()
        )
        db.add(log_entry)
        db.commit()
        logger.info(f"Login recorded: {username} (session: {session_id[:8]}...)")
    except Exception as e:
        logger.error(f"Error logging login: {e}")
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()
    return session_id


def log_logout(session_id: str):
    """Log user logout time."""
    if not session_id:
        return
    db = SessionLocal()
    try:
        log_entry = db.query(SessionLog).filter(SessionLog.session_id == session_id).first()
        if log_entry:
            log_entry.logout_time = datetime.now()
            db.commit()
            logger.info(f"Logout recorded: {log_entry.username} (session: {session_id[:8]}...)")
    except Exception as e:
        logger.error(f"Error logging logout: {e}")
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()


def logout():
    """Clear session and log logout."""
    if 'session_id' in st.session_state:
        log_logout(st.session_state.session_id)
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.session_id = None
    st.rerun()
