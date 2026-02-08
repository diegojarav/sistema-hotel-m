/**
 * Hotel Management System - API Fetch Wrapper
 * =============================================
 * Global error handling and rate limiting for all API calls.
 *
 * NOTE: This module should be used for all API calls to ensure
 * consistent error handling. Page components currently make direct
 * fetch calls - consider refactoring to use these helpers.
 */

import { API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

/**
 * Custom API error with status code.
 */
export class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
        super(message);
        this.status = status;
        this.name = 'ApiError';
    }
}

/**
 * Authenticated fetch wrapper with global error handling.
 * Intercepts common error codes and provides user-friendly messages.
 * 
 * @param endpoint - API endpoint (without base URL)
 * @param options - Fetch options
 * @param token - Optional JWT token for authentication
 * @returns Promise with JSON response
 */
export async function apiFetch<T>(
    endpoint: string,
    options: RequestInit = {},
    token?: string | null
): Promise<T> {
    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers,
    });

    // Handle rate limiting
    if (response.status === 429) {
        throw new ApiError(
            'Sistema saturado. Por favor espera 30 segundos.',
            429
        );
    }

    // Handle server errors
    if (response.status >= 500) {
        throw new ApiError(
            'Error de conexión con el servidor.',
            response.status
        );
    }

    // Handle unauthorized
    if (response.status === 401) {
        throw new ApiError(
            'Sesión expirada. Por favor inicie sesión nuevamente.',
            401
        );
    }

    // Handle not found
    if (response.status === 404) {
        throw new ApiError(
            'Recurso no encontrado.',
            404
        );
    }

    // Handle other client errors
    if (!response.ok) {
        let errorMessage = 'Error en la solicitud.';
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
        } catch {
            // Ignore JSON parse errors
        }
        throw new ApiError(errorMessage, response.status);
    }

    // Return JSON response
    return response.json() as Promise<T>;
}

/**
 * GET request helper.
 */
export async function apiGet<T>(endpoint: string, token?: string | null): Promise<T> {
    return apiFetch<T>(endpoint, { method: 'GET' }, token);
}

/**
 * POST request helper.
 */
export async function apiPost<T>(
    endpoint: string,
    body: unknown,
    token?: string | null
): Promise<T> {
    return apiFetch<T>(
        endpoint,
        {
            method: 'POST',
            body: JSON.stringify(body),
        },
        token
    );
}

/**
 * PUT request helper.
 */
export async function apiPut<T>(
    endpoint: string,
    body: unknown,
    token?: string | null
): Promise<T> {
    return apiFetch<T>(
        endpoint,
        {
            method: 'PUT',
            body: JSON.stringify(body),
        },
        token
    );
}

/**
 * DELETE request helper.
 */
export async function apiDelete<T>(endpoint: string, token?: string | null): Promise<T> {
    return apiFetch<T>(endpoint, { method: 'DELETE' }, token);
}
