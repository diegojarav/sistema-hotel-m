"""
Hotel PMS API - Main Application
=====================================

HYBRID MONOLITH ARCHITECTURE:
- FastAPI layer in /api/ folder
- Imports services from root services.py (Single Source of Truth)
- Imports schemas from root schemas.py
- Streamlit app (app.py) continues to work unchanged

SECURITY HARDENED:
- Rate limiting via slowapi (5 req/min on login)
- JWT requires .env configuration

Run with: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import requests as http_requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables from .env file (BEFORE importing routers)
load_dotenv()

# Initialize rate limiter (used by endpoint decorators)
limiter = Limiter(key_func=get_remote_address)

# Logging (used by lifespan, exception handler, and background tasks)
from logging_config import get_logger
_main_logger = get_logger("api.main")

# Configuration (version, CORS, monitoring URLs)
from api.core.config import APP_VERSION, CORS_ORIGINS, HEALTHCHECK_PING_URL, DISCORD_WEBHOOK_URL

# Import routers
from api.v1.endpoints import auth, reservations, guests, calendar, rooms, agent, vision, settings, pricing, users, ical, admin, documents, caja, transacciones, reportes_financieros

# Track server start time for uptime reporting
_START_TIME = time.time()

@asynccontextmanager
async def lifespan(app):
    """App lifespan: startup cleanup + background iCal sync."""
    _close_stale_sessions()
    sync_task = asyncio.create_task(_periodic_ical_sync())
    _main_logger.info("iCal background sync started (every 15 minutes)")
    yield
    sync_task.cancel()

# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="Hotel PMS API",
    version=APP_VERSION,
    description="""
## Hotel Property Management System API - Hybrid Monolith

A production-ready REST API for hotel management.

### Architecture
- **Single Source of Truth**: All business logic in root `services.py`
- **Shared Schemas**: Root `schemas.py` used by both Streamlit and FastAPI
- **Smart Decorator**: `@with_db` detects if session is injected or needs creation

### Security
- **Rate Limiting**: Login endpoint limited to 5 requests per minute
- **JWT**: Access tokens with 30-minute expiration

### Endpoints
- **Rooms**: View room status and availability
- **Bookings**: Create, update, and cancel reservations
- **Guests**: Manage check-in records (fichas)
- **Calendar**: Get occupancy data and calendar events
- **Agent**: AI agent integration (Gemini 2.5 Flash)
""",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limiter to app state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Safety net: catch unhandled exceptions and return a generic 500.
    Prevents internal details from leaking to the client.

    CRITICAL: Must include CORS headers directly because BaseHTTPMiddleware
    (security_headers) can re-raise exceptions, bypassing CORSMiddleware.
    Without these headers, browsers report "TypeError: Failed to fetch"
    instead of showing the actual 500 error.
    """
    _main_logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor."}
    )
    # Inject CORS headers so the browser can read the error response
    origin = request.headers.get("origin")
    if origin and origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


# ==========================================
# STARTUP / BACKGROUND TASKS
# ==========================================

def _close_stale_sessions():
    """Mark all 'active' sessions as closed on server restart."""
    from datetime import datetime
    from database import session_factory, SessionLog

    db = session_factory()
    try:
        updated = db.query(SessionLog).filter(
            SessionLog.status == "active"
        ).update({
            "status": "closed",
            "logout_time": datetime.now(),
            "closed_reason": "server_restart"
        })
        db.commit()
        if updated > 0:
            _main_logger.info(f"Startup cleanup: Closed {updated} stale session(s)")
        else:
            _main_logger.info("Startup cleanup: No stale sessions found")
    except Exception as e:
        db.rollback()
        _main_logger.error(f"Startup cleanup failed: {e}")
    finally:
        db.close()


async def _periodic_ical_sync():
    """Background task: sync all iCal feeds every 15 minutes + heartbeat ping."""
    while True:
        await asyncio.sleep(900)  # 15 minutes
        try:
            from services import ICalService
            await asyncio.to_thread(ICalService.sync_all_feeds_standalone)
        except Exception as e:
            _main_logger.error(f"iCal auto-sync error: {e}")

        # Auto-complete past reservations
        try:
            from services import ReservationService
            count = await asyncio.to_thread(ReservationService.auto_complete_reservations)
            if count > 0:
                _main_logger.info(f"Auto-completed {count} past reservation(s)")
        except Exception as e:
            _main_logger.error(f"Auto-complete error: {e}")

        # Heartbeat ping to healthchecks.io (push-based uptime monitoring)
        if HEALTHCHECK_PING_URL:
            try:
                http_requests.get(HEALTHCHECK_PING_URL, timeout=5)
            except Exception:
                pass  # Don't log — network issues shouldn't spam logs


# ==========================================
# MIDDLEWARE
# ==========================================

# ORDER MATTERS: Starlette builds middleware last-added = outermost.
# security_headers is added first (inner), then CORS wraps it (outer).
# This ensures CORS headers are present even on error responses.

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

# CORS must be added AFTER security_headers so it wraps outermost
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
app.include_router(vision.router, prefix="/api/v1/vision", tags=["Vision AI"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(pricing.router, prefix="/api/v1/pricing", tags=["Pricing"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(ical.router, prefix="/api/v1/ical", tags=["iCal Sync"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(caja.router, prefix="/api/v1/caja", tags=["Caja"])
app.include_router(transacciones.router, prefix="/api/v1/transacciones", tags=["Transacciones"])
app.include_router(reportes_financieros.router, prefix="/api/v1/reportes", tags=["Reportes Financieros"])


# ==========================================
# HEALTH ENDPOINTS
# ==========================================

@app.get("/", tags=["Health"])
def root():
    """Quick health check endpoint."""
    return {
        "status": "ok",
        "api": "Hotel PMS API",
        "version": APP_VERSION,
        "architecture": "Hybrid Monolith",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
def health_check():
    """
    Detailed health check with database test, disk space, and backup info.
    Used by monitoring systems (healthchecks.io) and deploy scripts.
    """
    from sqlalchemy import text
    from database import session_factory

    # Test database connectivity
    db_status = "ok"
    try:
        db = session_factory()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        db_status = f"error: {e}"

    # Check disk space
    try:
        backend_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent
        disk = shutil.disk_usage(str(backend_dir))
        disk_free_gb = round(disk.free / (1024 ** 3), 1)
    except Exception:
        disk_free_gb = -1

    # Last backup info
    last_backup_name = None
    try:
        backup_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent / "backups"
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("hotel_daily_*.db"), key=os.path.getmtime, reverse=True)
            if backups:
                last_backup_name = backups[0].name
    except Exception:
        pass

    overall_status = "healthy" if db_status == "ok" else "degraded"

    return {
        "status": overall_status,
        "version": APP_VERSION,
        "database": db_status,
        "disk_free_gb": disk_free_gb,
        "last_backup": last_backup_name,
        "uptime_seconds": round(time.time() - _START_TIME),
        "cors_origins_count": len(CORS_ORIGINS),
    }
