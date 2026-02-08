/**
 * Hotel Settings Service
 * Fetches dynamic hotel configuration from the API
 */

import { API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

export interface HotelConfig {
    hotel_name: string;
}

/**
 * Fetch hotel configuration from API
 */
export async function getHotelConfig(): Promise<HotelConfig> {
    try {
        const response = await fetch(`${API_URL}/settings/hotel-name`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            cache: 'no-store', // Always get fresh data
        });

        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.error('Failed to fetch hotel config:', error);
    }

    // Return default if API unavailable
    return { hotel_name: 'Mi Hotel' };
}

/**
 * Update hotel name via API
 */
export async function setHotelName(name: string, token?: string): Promise<boolean> {
    try {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_URL}/settings/hotel-name`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ name }),
        });

        return response.ok;
    } catch (error) {
        console.error('Failed to update hotel name:', error);
        return false;
    }
}
