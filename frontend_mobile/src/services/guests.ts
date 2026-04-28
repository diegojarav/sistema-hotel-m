/**
 * Master Guest entity service (v1.10.0 — Phase 2a)
 * =================================================
 *
 * Typed wrappers around /api/v1/huespedes/* endpoints. Distinct from the
 * legacy CheckIn endpoints at /api/v1/guests/* (which manage per-stay
 * registration records — kept under the old URL for backward compat).
 *
 * Used by the reservation detail page to show the guest's previous stays
 * count + tap-to-history badge.
 */

import { apiGet } from './api';

export interface Guest {
    id: number;
    property_id: string;
    first_name: string;
    last_name: string;
    document_type?: string | null;
    document_number?: string | null;
    email?: string | null;
    phone?: string | null;
    nationality?: string | null;
    country?: string | null;
    city?: string | null;
    notes?: string | null;
    source?: string | null;
    is_active: boolean;
    total_stays: number;
    total_spent: number;
    last_visit_at?: string | null;  // ISO date
    created_at?: string | null;
    updated_at?: string | null;
}

export interface GuestSearchResult {
    id: number;
    first_name: string;
    last_name: string;
    document_number?: string | null;
    email?: string | null;
    phone?: string | null;
    total_stays: number;
    label: string;
}

export interface GuestReservationItem {
    id: string;
    check_in_date: string;   // ISO date
    check_out_date: string;  // ISO date
    stay_days: number;
    room_id: string;
    room_internal_code?: string | null;
    status: string;
    price: number;
    source?: string | null;
}

export interface GuestHistory {
    guest: Guest;
    reservations: GuestReservationItem[];
    total_stays: number;
    total_spent: number;
    last_visit_at?: string | null;
    avg_stay_length: number;
}

/** Fetch a guest by id (or null on 404). */
export async function getGuest(guestId: number): Promise<Guest | null> {
    try {
        return await apiGet<Guest>(`/huespedes/${guestId}`);
    } catch (error) {
        console.error(`getGuest(${guestId}) failed:`, error);
        return null;
    }
}

/** Fetch the full reservation history + aggregates for a guest. */
export async function getGuestHistory(guestId: number): Promise<GuestHistory | null> {
    try {
        return await apiGet<GuestHistory>(`/huespedes/${guestId}/history`);
    } catch (error) {
        console.error(`getGuestHistory(${guestId}) failed:`, error);
        return null;
    }
}

/** Search guests by name/document/email/phone (autocomplete). */
export async function searchGuests(
    query: string,
    limit: number = 25,
): Promise<GuestSearchResult[]> {
    if (!query || query.trim().length < 2) return [];
    try {
        const qs = `?q=${encodeURIComponent(query.trim())}&limit=${limit}`;
        return await apiGet<GuestSearchResult[]>(`/huespedes/search${qs}`);
    } catch (error) {
        console.error('searchGuests failed:', error);
        return [];
    }
}
