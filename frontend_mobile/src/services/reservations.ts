/**
 * Hotel Munich - Reservation Service
 * ====================================
 * Handles reservation data fetching and creation.
 */

import { apiGet, apiPost, apiPut } from './api';

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

export interface ReservationDetail extends Reservation {
    price: number;
    stay_days: number;
    room_type: string;
    contact_phone: string;
    contact_email: string;
    reserved_by: string;
    received_by: string;
    arrival_time: string | null;
    source: string;
    parking_needed: boolean;
    vehicle_model: string | null;
    vehicle_plate: string | null;
    category_id: string | null;
    client_type_id: string | null;
    created_at: string | null;
    cancellation_reason: string | null;
    cancelled_by: string | null;
}

/**
 * Fetch all reservations.
 */
export async function getAllReservations(): Promise<Reservation[]> {
    return apiGet<Reservation[]>('/reservations');
}

/**
 * Fetch a single reservation by ID.
 */
export async function getReservationById(id: string): Promise<ReservationDetail> {
    return apiGet<ReservationDetail>(`/reservations/${id}`);
}

/**
 * Update reservation status (Pendiente → Confirmada, any → Cancelada, etc.)
 */
export async function updateReservationStatus(id: string, status: string, reason?: string): Promise<{ message: string }> {
    return apiPut<{ message: string }>(`/reservations/${id}/status`, { status, reason });
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
/**
 * Parse "YYYY-MM-DD" as local date (avoids UTC shift).
 */
function parseLocalDate(dateStr: string): Date {
    const [y, m, d] = dateStr.split('T')[0].split('-').map(Number);
    return new Date(y, m - 1, d);
}

function formatLocalDate(date: Date): string {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function getDatesWithReservations(reservations: Reservation[]): Set<string> {
    const dates = new Set<string>();

    reservations.forEach(res => {
        const checkIn = parseLocalDate(res.check_in);
        const checkOut = parseLocalDate(res.check_out);

        const current = new Date(checkIn);
        while (current <= checkOut) {
            dates.add(formatLocalDate(current));
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
                textClass: 'text-green-600',
                label: 'Confirmada',
            };
        case 'pendiente':
        case 'pending':
            return {
                bgClass: 'bg-amber-500/20',
                textClass: 'text-amber-600',
                label: 'Pendiente',
            };
        case 'completada':
        case 'completed':
            return {
                bgClass: 'bg-gray-500/20',
                textClass: 'text-gray-600',
                label: 'Completada',
            };
        case 'cancelada':
        case 'cancelled':
            return {
                bgClass: 'bg-red-500/20',
                textClass: 'text-red-600',
                label: 'Cancelada',
            };
        default:
            return {
                bgClass: 'bg-slate-500/20',
                textClass: 'text-gray-500',
                label: status,
            };
    }
}
