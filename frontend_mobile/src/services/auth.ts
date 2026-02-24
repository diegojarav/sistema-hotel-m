/**
 * Hotel Munich - Authentication Service
 * ======================================
 * Handles OAuth2 authentication with FastAPI backend.
 * Includes session tracking with beacon logout support.
 */

import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

// Types
export interface AuthTokens {
    access_token: string;
    refresh_token: string;
    token_type: string;
}

export interface LoginError {
    detail: string;
}

/**
 * Login with username and password.
 * POSTs to /auth/login as application/x-www-form-urlencoded (OAuth2 spec).
 */
export async function login(username: string, password: string): Promise<AuthTokens> {
    // OAuth2 requires form-urlencoded body
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
    });

    if (!response.ok) {
        const error: LoginError = await response.json();
        throw new Error(error.detail || 'Login failed');
    }

    const tokens: AuthTokens = await response.json();

    // Store tokens in localStorage
    if (typeof window !== 'undefined') {
        localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
        localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }

    return tokens;
}

/**
 * Logout - Call backend API and clear all stored tokens.
 * Use this for explicit logout button clicks.
 */
export async function logout(): Promise<void> {
    const token = getAccessToken();

    // Call backend logout endpoint to close session properly
    if (token) {
        try {
            await fetch(`${API_URL}/auth/logout`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            });
        } catch {
            // Ignore errors - still clear local tokens
        }
    }

    // Clear local storage
    if (typeof window !== 'undefined') {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
}

/**
 * Beacon logout - Fire-and-forget logout for tab/browser close.
 * Uses navigator.sendBeacon which works during page unload.
 * Does NOT clear local storage (page is closing anyway).
 */
export function logoutBeacon(): void {
    const token = getAccessToken();

    if (token && typeof navigator?.sendBeacon === 'function') {
        // sendBeacon doesn't support custom headers, so we need to use a Blob
        // The backend will need to accept the token from the body OR we use a workaround
        // Using fetch with keepalive as an alternative that supports headers
        try {
            fetch(`${API_URL}/auth/logout-beacon`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
                keepalive: true, // Ensures request completes even as page unloads
            });
        } catch {
            // Ignore errors - this is fire-and-forget
        }
    }
}

/**
 * Get the current access token.
 */
export function getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
}

/**
 * Get the current refresh token.
 */
export function getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/**
 * Check if user is authenticated (has token).
 */
export function isAuthenticated(): boolean {
    return getAccessToken() !== null;
}

/**
 * Refresh tokens using the refresh token.
 */
export async function refreshTokens(): Promise<AuthTokens | null> {
    const refreshToken = getRefreshToken();

    if (!refreshToken) return null;

    try {
        const response = await fetch(`${API_URL}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });

        if (!response.ok) {
            logout(); // Clear invalid tokens
            return null;
        }

        const tokens: AuthTokens = await response.json();

        // Update stored tokens
        if (typeof window !== 'undefined') {
            localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
            localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
        }

        return tokens;
    } catch {
        logout();
        return null;
    }
}
