/**
 * Hotel Munich - Reservation Service
 * ====================================
 * Handles reservation data fetching and creation.
 */

import { apiGet, apiPost } from './api';

// Types
export interface Reservation {
    id: string;
    room_id: string;
    room_internal_code?: string;  // Friendly code (e.g. "DF-01")
    guest_name: string;
    status: string;
    check_in: string;  // ISO date string
    check_out: string; // ISO date string
}

/**
 * Fetch all reservations.
 */
export async function getAllReservations(): Promise<Reservation[]> {
    return apiGet<Reservation[]>('/reservations');
}

/**
 * Create a reservation for a single room.
 */
export async function createReservation(data: Record<string, unknown>): Promise<string[]> {
    return apiPost<string[]>('/reservations', data);
}

/**
 * Fetch upcoming reservations (check_in >= today).
 * Sorted by check_in date ASC (nearest first).
 */
export async function getUpcomingReservations(limit: number = 14): Promise<Reservation[]> {
    const allReservations = await getAllReservations();

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const upcoming = allReservations.filter(res => {
        const checkInDate = new Date(res.check_in);
        const isUpcoming = checkInDate >= today;
        const isActive = res.status.toLowerCase() !== 'cancelada';
        return isUpcoming && isActive;
    });

    upcoming.sort((a, b) => {
        return new Date(a.check_in).getTime() - new Date(b.check_in).getTime();
    });

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
