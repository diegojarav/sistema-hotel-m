/**
 * Hotel Munich - Caja (Cash Register) Service
 * =============================================
 * Handles cash register session management: open, close, query current state.
 */

import { apiGet, apiPost } from './api';

export interface CajaSesion {
    id: number;
    user_id: number;
    user_name: string;
    opened_at: string;
    closed_at: string | null;
    opening_balance: number;
    closing_balance_declared: number | null;
    closing_balance_expected: number | null;
    difference: number | null;
    status: 'ABIERTA' | 'CERRADA';
    notes: string | null;
    total_efectivo: number;
}

export interface AbrirCajaRequest {
    opening_balance: number;
    notes?: string;
}

export interface CerrarCajaRequest {
    session_id: number;
    closing_balance_declared: number;
    notes?: string;
}

/**
 * Open a new cash register session.
 * Fails if user already has an open session.
 */
export async function abrirCaja(data: AbrirCajaRequest): Promise<CajaSesion> {
    return apiPost<CajaSesion>('/caja/abrir', data);
}

/**
 * Close a cash register session. Computes expected vs declared balance.
 */
export async function cerrarCaja(data: CerrarCajaRequest): Promise<CajaSesion> {
    return apiPost<CajaSesion>('/caja/cerrar', data);
}

/**
 * Get the current open session for the logged-in user, or null.
 */
export async function getCajaActual(): Promise<CajaSesion | null> {
    return apiGet<CajaSesion | null>('/caja/actual');
}

/**
 * List past cash register sessions.
 * Non-admins only see their own sessions.
 */
export async function getCajaHistorial(limit: number = 50): Promise<CajaSesion[]> {
    return apiGet<CajaSesion[]>(`/caja/historial?limit=${limit}`);
}

/**
 * Get full session detail (with transactions).
 */
export async function getCajaDetalle(sessionId: number): Promise<CajaSesion & {
    transactions: Array<{
        id: number;
        reserva_id: string | null;
        amount: number;
        payment_method: string;
        reference_number: string | null;
        description: string | null;
        created_at: string;
        created_by: string | null;
        voided: boolean;
        void_reason: string | null;
    }>;
    total_efectivo: number;
    total_transferencia: number;
    total_pos: number;
}> {
    return apiGet(`/caja/${sessionId}`);
}

/**
 * Format Guaranies amount for display.
 */
export function formatGs(amount: number): string {
    return `${amount.toLocaleString('es-PY')} Gs`;
}
