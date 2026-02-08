/**
 * Hotel Munich - Room Service
 * ============================
 * Handles room data fetching from FastAPI backend.
 * Updated for RoomCategory-based schema (Los Monges MVP)
 */

import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

// Types
export interface RoomCategory {
    id: string;
    name: string;
    description?: string;
    base_price: number;
    max_capacity: number;
    bed_configuration?: string;
    amenities?: string;
    active: number;
}

export interface RoomStatus {
    room_id: string;
    category_id?: string;
    category_name: string;
    base_price?: number;
    max_capacity?: number;
    internal_code?: string;
    floor?: number;
    status: string;  // 'Libre', 'OCUPADA', etc.
    huesped: string;
    res_id?: string;
}

export interface Room {
    id: string;
    category_id?: string;
    category_name: string;
    internal_code?: string;
    floor?: number;
    status: string;
    base_price?: number;
}

/**
 * Get authorization headers with Bearer token.
 */
function getAuthHeaders(): HeadersInit {
    const token = typeof window !== 'undefined'
        ? localStorage.getItem(ACCESS_TOKEN_KEY)
        : null;

    return {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };
}

/**
 * Fetch all room categories with pricing.
 */
export async function getRoomCategories(): Promise<RoomCategory[]> {
    const response = await fetch(`${API_URL}/rooms/categories`, {
        method: 'GET',
        headers: getAuthHeaders(),
    });

    if (!response.ok) {
        if (response.status === 401) {
            throw new Error('Sesión expirada. Por favor, inicie sesión nuevamente.');
        }
        throw new Error('Error al cargar las categorías de habitaciones');
    }

    return response.json();
}

/**
 * Fetch room status for today (or specific date).
 * Returns real-time occupancy status for all rooms with category info.
 */
export async function getRoomsStatus(targetDate?: string): Promise<RoomStatus[]> {
    const url = targetDate
        ? `${API_URL}/rooms/status?target_date=${targetDate}`
        : `${API_URL}/rooms/status`;

    const response = await fetch(url, {
        method: 'GET',
        headers: getAuthHeaders(),
    });

    if (!response.ok) {
        if (response.status === 401) {
            throw new Error('Sesión expirada. Por favor, inicie sesión nuevamente.');
        }
        throw new Error('Error al cargar el estado de las habitaciones');
    }

    return response.json();
}

/**
 * Fetch all rooms.
 */
export async function getAllRooms(): Promise<Room[]> {
    const response = await fetch(`${API_URL}/rooms`, {
        method: 'GET',
        headers: getAuthHeaders(),
    });

    if (!response.ok) {
        if (response.status === 401) {
            throw new Error('Sesión expirada. Por favor, inicie sesión nuevamente.');
        }
        throw new Error('Error al cargar las habitaciones');
    }

    return response.json();
}

/**
 * Get status display info (color classes and label).
 */
export function getStatusDisplay(status: string): {
    bgClass: string;
    borderClass: string;
    textClass: string;
    label: string;
} {
    const statusLower = status.toLowerCase();

    if (statusLower === 'libre' || statusLower === 'available') {
        return {
            bgClass: 'bg-green-500/20',
            borderClass: 'border-green-500',
            textClass: 'text-green-400',
            label: 'Libre',
        };
    }

    if (statusLower === 'ocupada' || statusLower === 'occupied') {
        return {
            bgClass: 'bg-red-500/20',
            borderClass: 'border-red-500',
            textClass: 'text-red-400',
            label: 'Ocupada',
        };
    }

    if (statusLower === 'sucia' || statusLower === 'cleaning') {
        return {
            bgClass: 'bg-amber-500/20',
            borderClass: 'border-amber-500',
            textClass: 'text-amber-400',
            label: 'Limpieza',
        };
    }

    if (statusLower === 'maintenance' || statusLower === 'mantenimiento') {
        return {
            bgClass: 'bg-blue-500/20',
            borderClass: 'border-blue-500',
            textClass: 'text-blue-400',
            label: 'Mantenimiento',
        };
    }

    return {
        bgClass: 'bg-slate-500/20',
        borderClass: 'border-slate-500',
        textClass: 'text-slate-400',
        label: status,
    };
}

/**
 * Format price in Guaraníes.
 */
export function formatPrice(price: number): string {
    return new Intl.NumberFormat('es-PY', {
        style: 'decimal',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(price) + ' Gs';
}

/**
 * Get category color based on price tier.
 */
export function getCategoryColor(basePrice: number): string {
    if (basePrice >= 350000) return 'text-purple-400';
    if (basePrice >= 250000) return 'text-blue-400';
    if (basePrice >= 200000) return 'text-green-400';
    return 'text-slate-400';
}
