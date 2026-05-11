/**
 * Constants - Single Source of Truth for Storage Keys + API Configuration
 * ========================================================================
 *
 * TOKEN-01 FIX: All services must import from here to avoid key mismatches.
 */

// LocalStorage keys for authentication tokens
export const ACCESS_TOKEN_KEY = 'hms_access_token';
export const REFRESH_TOKEN_KEY = 'hms_refresh_token';

// ==========================================================================
// API base URL — auto-detected from current hostname (v1.10.0)
// ==========================================================================
//
// Pre-v1.10.0 we hardcoded `NEXT_PUBLIC_API_URL=http://192.168.x.x:8000` in
// `.env.local`. That broke every time the laptop joined a different network
// (home → office → café each have different LAN IPs). Auto-detection here
// fixes the recurring "Failed to fetch" problem permanently.
//
// Resolution order (first match wins):
//   1. `NEXT_PUBLIC_API_URL` env var  → explicit override (staging/prod where
//      the API lives on a DIFFERENT hostname than the UI).
//   2. Browser context → derive from `window.location.hostname`. Same host the
//      UI is being served from, port 8000. Works automatically for:
//        - in-browser preview at localhost:3000  → localhost:8000
//        - real phone on Wi-Fi at 192.168.3.140:3000 → 192.168.3.140:8000
//        - any other LAN address → matching :8000
//   3. SSR fallback → `localhost:8000`. Only reached if Next pre-renders a
//      page on the server; client hydration immediately replaces with #2.
//
// Why this safety order: when deployed (e.g. `app.hotel.com` UI, `api.hotel.com`
// backend), the `NEXT_PUBLIC_API_URL` env var is baked into the build and must
// override the hostname-derived guess. Local dev leaves it unset → auto-detect.

const getApiBaseUrl = (): string => {
    // 1. Explicit override (staging/prod with split UI ↔ API hosts).
    if (process.env.NEXT_PUBLIC_API_URL) {
        return process.env.NEXT_PUBLIC_API_URL;
    }
    // 2. Browser: derive from where the page is being served from.
    if (typeof window !== 'undefined') {
        return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    // 3. SSR fallback (very rare for this app — all API calls are client-side).
    return 'http://localhost:8000';
};

export const API_BASE_URL = getApiBaseUrl();
