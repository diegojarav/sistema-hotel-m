/**
 * Hotel Munich - Consumo & Product Service (v1.6.0 — Phase 3)
 * =============================================================
 * Frontend bindings for the POS layer: list active products,
 * register consumos against a reservation, void consumos (admin).
 */

import { apiGet, apiPost } from './api';

export type ProductCategory = 'BEBIDA' | 'SNACK' | 'SERVICIO' | 'MINIBAR' | 'OTRO';

export interface Producto {
    id: string;
    property_id: string | null;
    name: string;
    category: ProductCategory | string;
    price: number;
    stock_current: number | null;
    stock_minimum: number | null;
    is_stocked: boolean;
    is_active: boolean;
    created_at: string | null;
    updated_at: string | null;
}

export interface Consumo {
    id: number;
    reserva_id: string;
    producto_id: string;
    producto_name: string;
    quantity: number;
    unit_price: number;
    total: number;
    description: string | null;
    created_at: string | null;
    created_by: string | null;
    voided: boolean;
    void_reason: string | null;
    voided_at: string | null;
    voided_by: string | null;
}

export interface RegistrarConsumoRequest {
    reserva_id: string;
    producto_id: string;
    quantity: number;
    description?: string;
}

/**
 * List active products (optionally filtered by category).
 */
export async function listProducts(category?: string): Promise<Producto[]> {
    const qs = category ? `?category=${encodeURIComponent(category)}&active_only=true` : '?active_only=true';
    return apiGet<Producto[]>(`/productos/${qs}`);
}

/**
 * Register a consumo against an active reservation.
 * Allowed roles: admin, supervisor, gerencia, recepcion.
 */
export async function registrarConsumo(data: RegistrarConsumoRequest): Promise<Consumo> {
    return apiPost<Consumo>('/consumos/', data);
}

/**
 * Void a consumo. Admin only. Restores stock and recalculates reservation status.
 */
export async function anularConsumo(consumoId: number, reason: string): Promise<Consumo> {
    return apiPost<Consumo>(`/consumos/${consumoId}/anular`, { reason });
}

/**
 * List active consumos for a reservation.
 */
export async function listConsumosByReserva(reservaId: string): Promise<Consumo[]> {
    return apiGet<Consumo[]>(`/consumos/reserva/${reservaId}`);
}

/**
 * Group products by category for UI display.
 */
export function groupByCategory(products: Producto[]): Record<string, Producto[]> {
    const groups: Record<string, Producto[]> = {};
    for (const p of products) {
        const key = p.category || 'OTRO';
        if (!groups[key]) groups[key] = [];
        groups[key].push(p);
    }
    return groups;
}

export function categoryEmoji(cat: string): string {
    return {
        BEBIDA: '🥤',
        SNACK: '🍿',
        SERVICIO: '🛎️',
        MINIBAR: '🍾',
        OTRO: '📦',
    }[cat] || '📦';
}

/**
 * Format a Guarani amount for display.
 */
export function formatPriceGs(amount: number): string {
    return `${amount.toLocaleString('es-PY')} Gs`;
}
