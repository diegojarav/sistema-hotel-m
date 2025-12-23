"""
Hotel Munich API - Main Application
=====================================

HYBRID MONOLITH ARCHITECTURE:
- FastAPI layer in /api/ folder
- Imports services from root services.py (Single Source of Truth)
- Imports schemas from root schemas.py
- Streamlit app (app.py) continues to work unchanged

Run with: python -m uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from api.v1.endpoints import auth, reservations, guests, calendar, rooms, agent

# ==========================================
# APP CONFIGURATION
# ==========================================

# CORS origins for Next.js frontend
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
]

# Create FastAPI app
app = FastAPI(
    title="Hotel Munich API",
    version="1.0.0",
    description="""
## Hotel Munich Management API - Hybrid Monolith

A production-ready REST API for managing a 14-room hotel.

### Architecture
- **Single Source of Truth**: All business logic in root `services.py`
- **Shared Schemas**: Root `schemas.py` used by both Streamlit and FastAPI
- **Smart Decorator**: `@with_db` detects if session is injected or needs creation

### Endpoints
- **Rooms**: View room status and availability
- **Bookings**: Create, update, and cancel reservations  
- **Guests**: Manage check-in records (fichas)
- **Calendar**: Get occupancy data and calendar events
- **Agent**: AI agent integration (Ollama/LM Studio)
""",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ==========================================
# MIDDLEWARE
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# ROUTERS
# ==========================================

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(rooms.router, prefix="/api/v1/rooms", tags=["Rooms"])
app.include_router(reservations.router, prefix="/api/v1/reservations", tags=["Reservations"])
app.include_router(guests.router, prefix="/api/v1/guests", tags=["Guests"])
app.include_router(calendar.router, prefix="/api/v1/calendar", tags=["Calendar"])
app.include_router(agent.router, prefix="/api/v1/agent", tags=["AI Agent"])


# ==========================================
# HEALTH ENDPOINTS
# ==========================================

@app.get("/", tags=["Health"])
def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "api": "Hotel Munich API",
        "version": "1.0.0",
        "architecture": "Hybrid Monolith",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "sqlite (hotel.db)",
        "cors_origins": CORS_ORIGINS,
        "services": "Imported from root services.py"
    }
