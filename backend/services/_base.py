import os
from pathlib import Path

# Load backend .env BEFORE any imports that depend on it
# This ensures Streamlit (frontend_pc) can access JWT_SECRET_KEY
from dotenv import load_dotenv
_backend_dir = Path(__file__).parent.parent
_env_path = _backend_dir / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from sqlalchemy.orm import Session
from database import SessionLocal

from logging_config import get_logger

# Logger para este módulo
logger = get_logger(__name__)

# ==========================================
# SERVICES
# ==========================================

def get_db():
    """
    Context manager para obtener sesión thread-safe.
    Uso: with get_db() as db: ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        SessionLocal.remove()


# Helper for direct usage (non-dependency injection style for Streamlit)
# THREAD-SAFE: Usa scoped_session con remove() para limpiar
# HYBRID MONOLITH: Smart decorator that works with both Streamlit (no db) and FastAPI (db injected)
def with_db(func):
    """
    Smart decorator que maneja el ciclo de vida de la sesión de forma segura.

    HYBRID MONOLITH PATTERN:
    - Si `db` es pasado como primer argumento o en kwargs: usa esa sesión (FastAPI mode)
    - Si `db` no está presente: crea una sesión propia (Streamlit mode)

    Esto permite que services.py sea el Single Source of Truth para ambos frontends.
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if db was passed explicitly
        db_provided = False
        db = None

        # Check if first argument is a Session (FastAPI injects it this way)
        if args and isinstance(args[0], Session):
            db_provided = True
            db = args[0]

        # Check if db is in kwargs (alternative injection pattern)
        if 'db' in kwargs and kwargs['db'] is not None:
            db_provided = True
            db = kwargs['db']

        if db_provided:
            # FastAPI Mode: Use the provided session, don't manage its lifecycle
            # The session is managed by FastAPI's Depends(get_db)
            return func(*args, **kwargs)
        else:
            # Streamlit Mode: Create and manage our own session
            db = SessionLocal()
            try:
                # Insert db as first argument
                result = func(db, *args, **kwargs)
                return result
            except Exception as e:
                db.rollback()
                logger.error(f"Error in {func.__name__}: {e}")
                raise e
            finally:
                # CRITICAL: Clean the session from the thread's registry
                SessionLocal.remove()

    return wrapper
