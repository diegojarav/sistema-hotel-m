/**
 * Meals service (v1.7.0 — Phase 4)
 * =================================
 *
 * Typed wrappers around /meal-plans and /reportes/cocina endpoints.
 *
 * Hotels that don't offer meals should NEVER call these endpoints — gate
 * their usage with the `meals_enabled` flag from getMealsConfig() instead.
 */

import { apiGet } from './api';
import type { MealInclusionMode } from './settings';

export interface MealPlan {
    id: string;
    property_id: string;
    code: string;
    name: string;
    description?: string | null;
    surcharge_per_person: number;
    surcharge_per_room: number;
    applies_to_mode: 'ANY' | MealInclusionMode;
    is_system: boolean;
    is_active: boolean;
    sort_order: number;
}

/**
 * List meal plans available for the current hotel mode. Pass `mode` to filter
 * to plans valid under that mode (ANY-mode plans like SOLO_HABITACION are
 * always included).
 */
export async function listMealPlans(mode?: MealInclusionMode): Promise<MealPlan[]> {
    try {
        const qs = mode ? `?mode=${encodeURIComponent(mode)}` : '';
        return await apiGet<MealPlan[]>(`/meal-plans${qs}`);
    } catch (error) {
        console.error('Failed to list meal plans:', error);
        return [];
    }
}

// ==========================================
// Kitchen Report
// ==========================================

export interface KitchenRoomRow {
    reservation_id: string;
    room_id: string;
    internal_code: string;
    room_type: string;
    guest_name: string;
    guests_count: number;
    breakfast_guests: number;
    plan_id?: string | null;
    plan_code?: string | null;
    plan_name?: string | null;
    checkout_date: string;
    checkout_today: boolean;
    check_in_date?: string | null;
}

export interface KitchenReport {
    enabled: boolean;
    fecha: string;
    property_id: string;
    mode: MealInclusionMode | null;
    total_with_breakfast: number;
    total_without: number;
    rooms: KitchenRoomRow[];
}

/**
 * Get kitchen report for a given date. Default: tomorrow (planning mode).
 * Returns enabled:false when the hotel's meals are disabled.
 *
 * NOTE: do NOT pass `null` as the token here — /reportes/cocina requires JWT
 * auth. Omit the 2nd arg so apiFetch auto-reads from localStorage.
 */
export async function getKitchenReport(fecha?: string): Promise<KitchenReport> {
    const qs = fecha ? `?fecha=${encodeURIComponent(fecha)}` : '';
    return await apiGet<KitchenReport>(`/reportes/cocina${qs}`, undefined, { cache: 'no-store' });
}
