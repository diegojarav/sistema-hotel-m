/**
 * Hotel Munich - Pricing Service
 * ================================
 * Handles pricing calculations, client type, and season data.
 */

import { apiGet, apiPost } from './api';

export interface PriceModifier {
    name: string;
    amount: number;
    percent: number;
}

export interface PriceBreakdown {
    base_unit_price: number;
    base_total: number;
    nights: number;
    modifiers: PriceModifier[];
}

export interface PriceCalculationResponse {
    final_price: number;
    currency: string;
    breakdown: PriceBreakdown;
}

export interface ClientType {
    id: string;
    name: string;
    description: string;
    default_discount_percent: number;
    color: string;
    icon: string;
}

export interface PricingSeason {
    id: string;
    name: string;
    description: string;
    price_modifier: number;
    color: string;
}

export async function getClientTypes(): Promise<ClientType[]> {
    try {
        return await apiGet<ClientType[]>('/pricing/client-types');
    } catch (error) {
        console.error("Error fetching client types", error);
        return [];
    }
}

export async function getSeasons(): Promise<PricingSeason[]> {
    try {
        return await apiGet<PricingSeason[]>('/pricing/seasons');
    } catch (error) {
        console.error("Error fetching seasons", error);
        return [];
    }
}

export async function calculatePrice(
    categoryId: string,
    checkIn: string,
    stayDays: number,
    clientTypeId: string,
    roomId?: string,
    seasonId?: string
): Promise<PriceCalculationResponse> {
    return apiPost<PriceCalculationResponse>('/pricing/calculate', {
        category_id: categoryId,
        check_in: checkIn,
        stay_days: stayDays,
        client_type_id: clientTypeId,
        room_id: roomId,
        season_id: seasonId,
    });
}
