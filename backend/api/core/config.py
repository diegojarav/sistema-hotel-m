"""
Hotel PMS API - Configuration
==========================================

Application settings, JWT, monitoring, and versioning.
Requires environment variable for production deployments.

SECURITY: No fallback secret - application will fail fast if not configured.
"""

import os


# ==========================================
# APPLICATION VERSION
# ==========================================

APP_VERSION: str = "1.7.0"


# ==========================================
# JWT CONFIGURATION
# ==========================================

# Secret key for signing JWT tokens
# CRITICAL: Must be set in .env or environment - NO FALLBACK
SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY")

if not SECRET_KEY:
    raise ValueError(
        "CRITICAL: JWT_SECRET_KEY is missing!\n"
        "Please add JWT_SECRET_KEY=your_secret_here to backend/.env\n"
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

# JWT Algorithm
ALGORITHM: str = "HS256"

# Access token expires in 365 days (hotel runs 24/7, manual logout only)
ACCESS_TOKEN_EXPIRE_MINUTES: int = 525600

# Refresh token expires in 365 days
REFRESH_TOKEN_EXPIRE_DAYS: int = 365


# ==========================================
# MONITORING CONFIGURATION
# ==========================================

# Healthchecks.io push URL (free uptime monitoring)
# Sign up at https://healthchecks.io and create a check
HEALTHCHECK_PING_URL: str = os.environ.get("HEALTHCHECK_PING_URL", "")

# Discord webhook for error alerting
# Create a webhook in Discord: Server Settings → Integrations → Webhooks
DISCORD_WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")


# ==========================================
# CORS CONFIGURATION
# ==========================================

# Comma-separated list of allowed origins
# Default covers local development; add Tailscale IPs for remote access
_DEFAULT_CORS = "http://localhost:3000,http://localhost:8501,http://127.0.0.1:3000,http://127.0.0.1:8501,http://192.168.3.140:3000"
CORS_ORIGINS_RAW: str = os.environ.get("CORS_ORIGINS", _DEFAULT_CORS)
CORS_ORIGINS: list = [origin.strip() for origin in CORS_ORIGINS_RAW.split(",") if origin.strip()]
