/**
 * Hotel Munich - Email Service (v1.8.0 — Phase 5)
 * ==================================================
 * Send reservation confirmation emails and read send history.
 */

import { apiGet, apiPost } from './api';

export interface EmailLogItem {
    id: number;
    reserva_id: string;
    recipient_email: string;
    subject: string;
    status: 'ENVIADO' | 'FALLIDO' | 'PENDIENTE';
    error_message?: string | null;
    sent_at?: string | null;
    sent_by?: string | null;
    created_at?: string | null;
}

export interface SendEmailResponse {
    email_log_id: number;
    status: string;
}

/**
 * Queue a reservation confirmation email.
 * Returns 202 Accepted — the actual send runs in a background task.
 *
 * @param reservaId - Reservation ID
 * @param email - Optional override; if omitted, backend uses reservation.contact_email
 */
export async function sendReservationEmail(
    reservaId: string,
    email?: string | null,
): Promise<SendEmailResponse> {
    const body = email ? { email } : {};
    return apiPost<SendEmailResponse>(
        `/email/reserva/${reservaId}/enviar`,
        body,
    );
}

/**
 * Fetch the email send history for a reservation (newest first).
 */
export async function getEmailHistory(reservaId: string): Promise<EmailLogItem[]> {
    return apiGet<EmailLogItem[]>(`/email/reserva/${reservaId}/historial`);
}
