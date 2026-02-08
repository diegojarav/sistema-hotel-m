"""
Hotel PMS API - Security Configuration
==========================================

JWT and authentication settings for the API.
Requires environment variable for production deployments.

SECURITY: No fallback secret - application will fail fast if not configured.
"""

import os


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

# Access token expires in 30 minutes
ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

# Refresh token expires in 7 days (for biometric persistence)
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
