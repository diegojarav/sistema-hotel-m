
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator
import sys
import os

# Ensure we can import from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Base, ClientType, PricingSeason, RoomCategory
from datetime import date

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session() -> Generator:
    """
    Creates a fresh database session for a test.
    """
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def seed_pricing_data(db_session):
    """
    Seeds the test DB with the data expected by the verification logic.
    """
    prop_id = "los-monges"
    
    # 1. Room Category
    cat = RoomCategory(
        id=f"{prop_id}-estandar",
        property_id=prop_id,
        name="Estandar",
        base_price=150000.0,
        max_capacity=2,
        amenities="[]"
    )
    db_session.add(cat)
    
    # 2. Client Types
    # Particular (Standard - 0%)
    c_std = ClientType(
        id=f"{prop_id}-particular",
        property_id=prop_id,
        name="Particular",
        default_discount_percent=0.0
    )
    # Empresa (Corporate - 15%)
    c_corp = ClientType(
        id=f"{prop_id}-empresa",
        property_id=prop_id,
        name="Empresa",
        default_discount_percent=15.0
    )
    db_session.add_all([c_std, c_corp])
    
    # 3. Seasons
    # High Season (Semana Santa - +30%)
    s_high = PricingSeason(
        id=f"{prop_id}-semana-santa-2026",
        property_id=prop_id,
        name="Semana Santa",
        start_date=date(2026, 3, 29),
        end_date=date(2026, 4, 5),
        price_modifier=1.30, # +30%
        applies_to_categories=None 
    )
    db_session.add(s_high)
    db_session.commit()
    
    return {
        "prop_id": prop_id,
        "cat_std": cat,
        "c_std": c_std,
        "c_corp": c_corp,
        "s_high": s_high
    }
