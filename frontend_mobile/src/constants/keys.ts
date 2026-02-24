/**
 * Constants - Single Source of Truth for Storage Keys
 * =====================================================
 *
 * TOKEN-01 FIX: All services must import from here to avoid key mismatches.
 */

// LocalStorage keys for authentication tokens
export const ACCESS_TOKEN_KEY = 'hms_access_token';
export const REFRESH_TOKEN_KEY = 'hms_refresh_token';

// API Configuration
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
