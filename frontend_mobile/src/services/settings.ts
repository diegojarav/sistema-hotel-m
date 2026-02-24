/**
 * Hotel Settings Service
 * Fetches dynamic hotel configuration from the API.
 */

import { apiGet, apiPost } from './api';

export interface HotelConfig {
    hotel_name: string;
}

/**
 * Fetch hotel configuration from API.
 */
export async function getHotelConfig(): Promise<HotelConfig> {
    try {
        return await apiGet<HotelConfig>('/settings/hotel-name', null, { cache: 'no-store' });
    } catch (error) {
        console.error('Failed to fetch hotel config:', error);
        return { hotel_name: 'Mi Hotel' };
    }
}

/**
 * Update hotel name via API.
 */
export async function setHotelName(name: string, token?: string): Promise<boolean> {
    try {
        await apiPost('/settings/hotel-name', { name }, token);
        return true;
    } catch (error) {
        console.error('Failed to update hotel name:', error);
        return false;
    }
}

export interface PropertySettings {
    check_in_start: string;
    check_in_end: string;
    check_out_time: string;
    breakfast_included: boolean;
}

/**
 * Fetch property settings (check-in/out times, breakfast policy).
 */
export async function getPropertySettings(): Promise<PropertySettings> {
    try {
        return await apiGet<PropertySettings>('/settings/property-settings');
    } catch (error) {
        console.error('Failed to fetch property settings:', error);
        return {
            check_in_start: '07:00',
            check_in_end: '22:00',
            check_out_time: '10:00',
            breakfast_included: false
        };
    }
}
