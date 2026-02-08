/**
 * Hotel Munich - Reservation Service
 * ====================================
 * Handles reservation data fetching from FastAPI backend.
 */

import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

// Types
export interface Reservation {
    id: string;
    room_id: string;
    guest_name: string;
    status: string;
    check_in: string;  // ISO date string
    check_out: string; // ISO date string
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
 * Fetch all reservations.
 */
export async function getAllReservations(): Promise<Reservation[]> {
    const response = await fetch(`${API_URL}/reservations`, {
        method: 'GET',
        headers: getAuthHeaders(),
    });

    if (!response.ok) {
        if (response.status === 401) {
            throw new Error('Sesión expirada. Por favor, inicie sesión nuevamente.');
        }
        throw new Error('Error al cargar las reservas');
    }

    return response.json();
}

/**
 * Fetch upcoming reservations (check_in >= today).
 * Sorted by check_in date ASC (nearest first).
 * Filters on frontend since backend doesn't support complex filtering.
 */
export async function getUpcomingReservations(limit: number = 14): Promise<Reservation[]> {
    const allReservations = await getAllReservations();

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Filter: only upcoming (check_in >= today) and active status
    const upcoming = allReservations.filter(res => {
        const checkInDate = new Date(res.check_in);
        const isUpcoming = checkInDate >= today;
        const isActive = res.status.toLowerCase() !== 'cancelada';
        return isUpcoming && isActive;
    });

    // Sort by check_in date ASC
    upcoming.sort((a, b) => {
        return new Date(a.check_in).getTime() - new Date(b.check_in).getTime();
    });

    // Limit results
    return upcoming.slice(0, limit);
}

/**
 * Get reservations for a specific date.
 */
export async function getReservationsForDate(targetDate: Date): Promise<Reservation[]> {
    const allReservations = await getAllReservations();

    const targetTime = targetDate.getTime();

    return allReservations.filter(res => {
        const checkIn = new Date(res.check_in);
        const checkOut = new Date(res.check_out);

        checkIn.setHours(0, 0, 0, 0);
        checkOut.setHours(0, 0, 0, 0);

        // Reservation spans this date
        return targetTime >= checkIn.getTime() && targetTime <= checkOut.getTime();
    });
}

/**
 * Get dates that have reservations (for calendar dots).
 */
export function getDatesWithReservations(reservations: Reservation[]): Set<string> {
    const dates = new Set<string>();

    reservations.forEach(res => {
        const checkIn = new Date(res.check_in);
        const checkOut = new Date(res.check_out);

        // Add all dates in the reservation range
        const current = new Date(checkIn);
        while (current <= checkOut) {
            dates.add(current.toISOString().split('T')[0]);
            current.setDate(current.getDate() + 1);
        }
    });

    return dates;
}

/**
 * Get status badge styling.
 */
export function getStatusBadge(status: string): {
    bgClass: string;
    textClass: string;
    label: string;
} {
    const normalizedStatus = status.toLowerCase();

    switch (normalizedStatus) {
        case 'confirmada':
        case 'confirmed':
            return {
                bgClass: 'bg-green-500/20',
                textClass: 'text-green-400',
                label: 'Confirmada',
            };
        case 'pendiente':
        case 'pending':
            return {
                bgClass: 'bg-amber-500/20',
                textClass: 'text-amber-400',
                label: 'Pendiente',
            };
        case 'cancelada':
        case 'cancelled':
            return {
                bgClass: 'bg-red-500/20',
                textClass: 'text-red-400',
                label: 'Cancelada',
            };
        case 'ocupada':
        case 'checked_in':
            return {
                bgClass: 'bg-blue-500/20',
                textClass: 'text-blue-400',
                label: 'Hospedado',
            };
        default:
            return {
                bgClass: 'bg-slate-500/20',
                textClass: 'text-slate-400',
                label: status,
            };
    }
}
