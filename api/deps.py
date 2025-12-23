"""
Hotel Munich API - Dependency Injection
========================================

Provides the database session dependency for FastAPI endpoints.
Works with the Hybrid Monolith pattern - imports from root.
"""

from typing import Generator
from sqlalchemy.orm import Session

# Import from ROOT - Single Source of Truth
from database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency for FastAPI.
    
    Yields a session that is properly closed after use.
    The smart @with_db decorator in services.py will detect this
    injected session and use it instead of creating its own.
    
    Usage:
        @router.post("/")
        def create_item(db: Session = Depends(get_db)):
            return SomeService.some_method(db=db, ...)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        SessionLocal.remove()
