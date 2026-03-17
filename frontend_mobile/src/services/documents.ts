/**
 * Hotel Munich - Document Service
 * ==================================
 * Handles PDF document downloads from the backend.
 */

import { API_BASE_URL } from '@/constants/keys';
import { getAccessToken } from './auth';

const API_URL = `${API_BASE_URL}/api/v1`;

/**
 * Download a reservation confirmation PDF.
 * Uses fetch + blob to send JWT in Authorization header.
 */
export async function downloadReservationPdf(reservationId: string): Promise<void> {
    const token = getAccessToken();
    const response = await fetch(`${API_URL}/documents/reservations/${reservationId}`, {
        headers: {
            'Authorization': `Bearer ${token}`,
        },
    });

    if (!response.ok) {
        throw new Error('No se pudo descargar el PDF');
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `reserva_${reservationId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
}

/**
 * Download a client registration PDF.
 */
export async function downloadClientPdf(checkinId: number): Promise<void> {
    const token = getAccessToken();
    const response = await fetch(`${API_URL}/documents/clients/${checkinId}`, {
        headers: {
            'Authorization': `Bearer ${token}`,
        },
    });

    if (!response.ok) {
        throw new Error('No se pudo descargar el PDF del cliente');
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `cliente_${checkinId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
}
