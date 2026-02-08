/**
 * Hotel Management System - Centralized API Client
 * ==================================================
 * Single gateway for all HTTP calls to the FastAPI backend.
 * Provides consistent error handling, auth headers, and FormData support.
 */

import { API_BASE_URL } from '@/constants/keys';
import { getAccessToken } from './auth';

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
 * Auto-reads JWT from localStorage unless token is explicitly passed.
 * Supports JSON and FormData bodies.
 *
 * @param endpoint - API endpoint path (e.g. '/rooms/categories')
 * @param options - Fetch options (method, body, headers, cache, etc.)
 * @param token - Optional token override. Pass `null` for unauthenticated requests.
 */
export async function apiFetch<T>(
    endpoint: string,
    options: RequestInit = {},
    token?: string | null
): Promise<T> {
    // Auto-read token unless explicitly passed (null = unauthenticated)
    const authToken = token !== undefined ? token : getAccessToken();

    // Skip Content-Type for FormData (browser sets it with boundary)
    const isFormData = options.body instanceof FormData;

    const headers: HeadersInit = {
        ...(!isFormData ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
    };

    if (authToken) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${authToken}`;
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

    return response.json() as Promise<T>;
}

/**
 * GET request helper.
 */
export async function apiGet<T>(
    endpoint: string,
    token?: string | null,
    options?: RequestInit
): Promise<T> {
    return apiFetch<T>(endpoint, { method: 'GET', ...options }, token);
}

/**
 * POST request helper (JSON body).
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
 * POST request helper (FormData body — for file uploads).
 */
export async function apiPostFormData<T>(
    endpoint: string,
    formData: FormData,
    token?: string | null
): Promise<T> {
    return apiFetch<T>(
        endpoint,
        {
            method: 'POST',
            body: formData,
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
