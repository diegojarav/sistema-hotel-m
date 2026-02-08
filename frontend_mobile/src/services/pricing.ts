import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

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
        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
        const res = await fetch(`${API_URL}/pricing/client-types`, {
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        });
        if (!res.ok) return [];
        return res.json();

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
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    const res = await fetch(`${API_URL}/pricing/calculate`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
            category_id: categoryId,
            check_in: checkIn,
            stay_days: stayDays,
            client_type_id: clientTypeId,
            room_id: roomId
        }),
    });

    if (!res.ok) {
        throw new Error('Failed to calculate price');
    }

    return res.json();
}
