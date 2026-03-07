"""
Hotel Munich PMS - Test Configuration
========================================

Provides fixtures for both service-layer tests (PC/Streamlit path)
and API endpoint tests (mobile/Next.js path).

All tests use in-memory SQLite — zero risk to production data.
"""

import os
import sys
import pytest
from typing import Generator
from datetime import date, time, timedelta

# ==========================================
# ENVIRONMENT SETUP (must run before any app import)
# ==========================================

# Set JWT_SECRET_KEY before api.core.config is imported (it raises ValueError if missing)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-32chars!")
os.environ.setdefault("GOOGLE_API_KEY", "")  # Disable Gemini in tests

# Ensure we can import from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import (
    Base, User, SessionLog, RoomCategory, Room, Reservation,
    CheckIn, Property, ClientType, ClientContract, PricingSeason,
    SystemSetting, ICalFeed, PriceCalculation
)

# ==========================================
# IN-MEMORY DATABASE
# ==========================================

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# CRITICAL: Use StaticPool so all threads share the SAME in-memory database.
# Without it, SQLAlchemy defaults to SingletonThreadPool which gives each thread
# its own connection — and each in-memory connection is a SEPARATE empty database.
# FastAPI runs endpoint handlers in a thread pool, so without StaticPool the
# handlers would see an empty DB with no tables or seed data.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ==========================================
# CORE FIXTURES
# ==========================================

@pytest.fixture(scope="function")
def db_session() -> Generator:
    """Creates a fresh database session for a test (clean DB each time)."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient with in-memory DB override.

    This simulates the mobile/Next.js path — all requests go through
    HTTP endpoints with JWT auth, CORS, rate limiting, etc.

    KEY FIX: We must patch database.session_factory AND api.deps.session_factory
    because:
    1. _close_stale_sessions() in lifespan uses database.session_factory directly
    2. get_db() in api/deps.py imported session_factory at module load time,
       creating a local reference that doesn't update if we only patch database.
    3. dependency_overrides is our primary mechanism but we also need the
       factory patches as a safety net for code that bypasses FastAPI DI.
    """
    from fastapi.testclient import TestClient
    from api.main import app
    from api.deps import get_db
    import database
    import api.deps as deps_module

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Patch session_factory at both module levels so ALL code paths
    # (lifespan startup, direct service calls, etc.) use the test DB
    original_db_factory = database.session_factory
    original_deps_factory = deps_module.session_factory
    database.session_factory = TestingSessionLocal
    deps_module.session_factory = TestingSessionLocal

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()
    database.session_factory = original_db_factory
    deps_module.session_factory = original_deps_factory


@pytest.fixture(autouse=True)
def disable_rate_limit():
    """Disable slowapi rate limiter during tests."""
    from api.main import app
    limiter = getattr(app.state, "limiter", None)
    if limiter:
        limiter.enabled = False
    yield
    if limiter:
        limiter.enabled = True


# ==========================================
# SEED DATA FIXTURES
# ==========================================

@pytest.fixture
def seed_property(db_session):
    """Create the los-monges property."""
    prop = Property(
        id="los-monges",
        name="Hospedaje Los Monges",
        slug="los-monges",
        display_mode="category",
        check_in_start="07:00",
        check_in_end="22:00",
        check_out_time="10:00",
        breakfast_included=0,
        parking_available=1,
        currency="PYG",
    )
    db_session.add(prop)
    db_session.commit()
    return prop


@pytest.fixture
def seed_rooms(db_session, seed_property):
    """
    Create 2 room categories and 6 rooms.

    - Estandar (150,000 Gs): rooms DE-01, DE-02, DE-03, DE-04
    - Suite (250,000 Gs): rooms DS-01, DS-02
    """
    cat_std = RoomCategory(
        id="los-monges-estandar",
        property_id="los-monges",
        name="Estandar",
        base_price=150000.0,
        max_capacity=2,
        amenities="[]",
        sort_order=1,
    )
    cat_suite = RoomCategory(
        id="los-monges-suite",
        property_id="los-monges",
        name="Suite",
        base_price=250000.0,
        max_capacity=4,
        amenities='["jacuzzi"]',
        sort_order=2,
    )
    db_session.add_all([cat_std, cat_suite])
    db_session.flush()

    rooms = []
    for i in range(1, 5):
        r = Room(
            id=f"los-monges-room-{i:03d}",
            property_id="los-monges",
            category_id="los-monges-estandar",
            floor=1,
            internal_code=f"DE-{i:02d}",
            status="available",
            active=1,
        )
        rooms.append(r)

    for i in range(5, 7):
        r = Room(
            id=f"los-monges-room-{i:03d}",
            property_id="los-monges",
            category_id="los-monges-suite",
            floor=2,
            internal_code=f"DS-{i-4:02d}",
            status="available",
            active=1,
        )
        rooms.append(r)

    db_session.add_all(rooms)
    db_session.commit()

    return {
        "cat_std": cat_std,
        "cat_suite": cat_suite,
        "rooms": rooms,
    }


@pytest.fixture
def seed_users(db_session):
    """Create admin and recepcionista users with bcrypt passwords."""
    from api.core.security import get_password_hash

    admin = User(
        username="admin",
        password=get_password_hash("admin123"),
        role="admin",
        real_name="Admin User",
    )
    recep = User(
        username="recepcion",
        password=get_password_hash("recep123"),
        role="recepcionista",
        real_name="Recepcionista",
    )
    db_session.add_all([admin, recep])
    db_session.commit()
    return {"admin": admin, "recepcionista": recep}


@pytest.fixture
def seed_pricing_data(db_session):
    """Seeds the test DB with pricing data (categories, client types, seasons)."""
    prop_id = "los-monges"

    # Room Category
    cat = RoomCategory(
        id=f"{prop_id}-estandar",
        property_id=prop_id,
        name="Estandar",
        base_price=150000.0,
        max_capacity=2,
        amenities="[]",
    )
    db_session.add(cat)

    # Client Types
    c_std = ClientType(
        id=f"{prop_id}-particular",
        property_id=prop_id,
        name="Particular",
        default_discount_percent=0.0,
    )
    c_corp = ClientType(
        id=f"{prop_id}-empresa",
        property_id=prop_id,
        name="Empresa",
        default_discount_percent=15.0,
    )
    db_session.add_all([c_std, c_corp])

    # High Season (Semana Santa +30%)
    s_high = PricingSeason(
        id=f"{prop_id}-semana-santa-2026",
        property_id=prop_id,
        name="Semana Santa",
        description="Temporada alta - Semana Santa",
        start_date=date(2026, 3, 29),
        end_date=date(2026, 4, 5),
        price_modifier=1.30,
        applies_to_categories=None,
        priority=10,
        color="#EF4444",
        active=1,
    )
    # Low Season (Febrero -10%)
    s_low = PricingSeason(
        id=f"{prop_id}-baja-feb-2026",
        property_id=prop_id,
        name="Temporada Baja Febrero",
        description="Temporada baja",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        price_modifier=0.90,
        applies_to_categories=None,
        priority=5,
        color="#10B981",
        active=1,
    )
    # Inactive season (should not appear in API)
    s_inactive = PricingSeason(
        id=f"{prop_id}-inactive",
        property_id=prop_id,
        name="Inactiva",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        price_modifier=1.50,
        active=0,
    )
    db_session.add_all([s_high, s_low, s_inactive])
    db_session.commit()

    return {
        "prop_id": prop_id,
        "cat_std": cat,
        "c_std": c_std,
        "c_corp": c_corp,
        "s_high": s_high,
        "s_low": s_low,
    }


@pytest.fixture
def seed_client_types(db_session, seed_property):
    """Create client types (Particular + Empresa)."""
    c_std = ClientType(
        id="los-monges-particular",
        property_id="los-monges",
        name="Particular",
        default_discount_percent=0.0,
        sort_order=1,
        active=1,
    )
    c_corp = ClientType(
        id="los-monges-empresa",
        property_id="los-monges",
        name="Empresa",
        default_discount_percent=15.0,
        sort_order=2,
        active=1,
    )
    db_session.add_all([c_std, c_corp])
    db_session.commit()
    return {"particular": c_std, "empresa": c_corp}


@pytest.fixture
def seed_full(db_session, seed_property, seed_rooms, seed_users, seed_client_types):
    """Full seed: property + rooms + users + client types."""
    return {
        "property": seed_property,
        **seed_rooms,
        **seed_users,
        **seed_client_types,
    }


# ==========================================
# AUTH HELPERS
# ==========================================

@pytest.fixture
def auth_headers_admin(client, seed_users) -> dict:
    """Login as admin and return Authorization headers."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_recep(client, seed_users) -> dict:
    """Login as recepcionista and return Authorization headers."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "recepcion", "password": "recep123"},
    )
    assert response.status_code == 200, f"Recep login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ==========================================
# RESERVATION FACTORY
# ==========================================

@pytest.fixture
def make_reservation(db_session, seed_rooms):
    """Factory to create test reservations quickly."""
    counter = [1000]

    def _make(
        check_in_date=None,
        stay_days=1,
        room_id=None,
        guest_name="Test Guest",
        status="Confirmada",
        price=150000.0,
        **kwargs,
    ):
        room = room_id or seed_rooms["rooms"][0].id
        res = Reservation(
            id=f"{counter[0]:07d}",
            check_in_date=check_in_date or (date.today() + timedelta(days=7)),
            stay_days=stay_days,
            guest_name=guest_name,
            room_id=room,
            status=status,
            price=price,
            property_id="los-monges",
            source="Direct",
            reserved_by="test",
            received_by="test",
            contact_phone="",
            **kwargs,
        )
        db_session.add(res)
        db_session.commit()
        counter[0] += 1
        return res

    return _make
