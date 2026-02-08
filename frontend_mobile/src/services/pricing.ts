/**
 * Hotel Munich - Pricing Service
 * ================================
 * Handles pricing calculations and client type data.
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

export async function getClientTypes(): Promise<ClientType[]> {
    try {
        return await apiGet<ClientType[]>('/pricing/client-types');
    } catch (error) {
        console.error("Error fetching client types", error);
        return [];
    }
}

export async function calculatePrice(
    categoryId: string,
    checkIn: string,
    stayDays: number,
    clientTypeId: string,
    roomId?: string
): Promise<PriceCalculationResponse> {
    return apiPost<PriceCalculationResponse>('/pricing/calculate', {
        category_id: categoryId,
        check_in: checkIn,
        stay_days: stayDays,
        client_type_id: clientTypeId,
        room_id: roomId,
    });
}
