/**
 * Hotel Munich - Transaccion Service
 * ====================================
 * Handles payment transaction creation, voiding, and saldo queries.
 */

import { apiGet, apiPost } from './api';

export type PaymentMethod = 'EFECTIVO' | 'TRANSFERENCIA' | 'POS';

export interface Transaccion {
    id: number;
    reserva_id: string | null;
    caja_sesion_id: number | null;
    amount: number;
    payment_method: PaymentMethod;
    reference_number: string | null;
    description: string | null;
    created_at: string;
    created_by: string | null;
    voided: boolean;
    void_reason: string | null;
    voided_at: string | null;
    voided_by: string | null;
}

export interface RegistrarPagoRequest {
    reserva_id: string;
    amount: number;
    payment_method: PaymentMethod;
    reference_number?: string;
    description?: string;
}

export interface AnularRequest {
    reason: string;
}

export interface SaldoReserva {
    reserva_id: string;
    total: number;
    paid: number;
    pending: number;
    transacciones: Transaccion[];
}

/**
 * Register a payment against a reservation.
 * EFECTIVO requires an open caja session for the logged-in user.
 */
export async function registrarPago(data: RegistrarPagoRequest): Promise<Transaccion> {
    return apiPost<Transaccion>('/transacciones/', data);
}

/**
 * Void (anular) a transaction. Reason must be at least 3 characters.
 * Both admin and recepcion can void, action is audited.
 */
export async function anularTransaccion(
    transaccionId: number,
    reason: string
): Promise<Transaccion> {
    return apiPost<Transaccion>(`/transacciones/${transaccionId}/anular`, { reason });
}

/**
 * Get saldo (total/paid/pending) and all active transactions for a reservation.
 */
export async function getSaldoReserva(reservaId: string): Promise<SaldoReserva> {
    return apiGet<SaldoReserva>(`/reservations/${reservaId}/saldo`);
}

/**
 * Get saldo via the transacciones endpoint (same result).
 */
export async function getSaldoFromTransacciones(reservaId: string): Promise<SaldoReserva> {
    return apiGet<SaldoReserva>(`/transacciones/reserva/${reservaId}`);
}

/**
 * List all transactions with optional filters.
 */
export async function listTransacciones(params?: {
    dateFrom?: string;
    dateTo?: string;
    paymentMethod?: PaymentMethod;
    includeVoided?: boolean;
}): Promise<Transaccion[]> {
    const query = new URLSearchParams();
    if (params?.dateFrom) query.append('date_from', params.dateFrom);
    if (params?.dateTo) query.append('date_to', params.dateTo);
    if (params?.paymentMethod) query.append('payment_method', params.paymentMethod);
    if (params?.includeVoided) query.append('include_voided', 'true');
    const q = query.toString() ? `?${query.toString()}` : '';
    return apiGet<Transaccion[]>(`/transacciones/${q}`);
}

/**
 * Get display label for a payment method.
 */
export function paymentMethodLabel(method: PaymentMethod): string {
    const map: Record<PaymentMethod, string> = {
        EFECTIVO: 'Efectivo',
        TRANSFERENCIA: 'Transferencia',
        POS: 'POS (Tarjeta)',
    };
    return map[method] || method;
}

/**
 * Get emoji for a payment method.
 */
export function paymentMethodEmoji(method: PaymentMethod): string {
    const map: Record<PaymentMethod, string> = {
        EFECTIVO: '💵',
        TRANSFERENCIA: '🏦',
        POS: '💳',
    };
    return map[method] || '💰';
}
