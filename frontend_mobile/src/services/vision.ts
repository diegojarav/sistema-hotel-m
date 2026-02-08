/**
 * Hotel Munich - Vision Service (Gemini 2.5 Flash)
 * ==================================================
 * Handles document scanning via Gemini Vision AI.
 */

import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

// Types
export interface ExtractedDocumentData {
    Apellidos: string | null;
    Nombres: string | null;
    Nacionalidad: string | null;
    Fecha_Nacimiento: string | null;  // YYYY-MM-DD
    Nro_Documento: string | null;
    Pais: string | null;
    Sexo: string | null;
    Estado_Civil: string | null;
    Procedencia: string | null;
}

export interface VisionResponse {
    success: boolean;
    data: ExtractedDocumentData | null;
    error: string | null;
}

/**
 * Scan a document image and extract personal data using Gemini 2.5 Flash.
 */
export async function scanDocument(file: File): Promise<VisionResponse> {
    const token = typeof window !== 'undefined'
        ? localStorage.getItem(ACCESS_TOKEN_KEY)
        : null;

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_URL}/vision/extract-data`, {
        method: 'POST',
        headers: {
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            // Note: Don't set Content-Type for FormData, browser sets it with boundary
        },
        body: formData,
    });

    if (!response.ok) {
        if (response.status === 401) {
            throw new Error('Sesión expirada. Por favor, inicie sesión nuevamente.');
        }
        if (response.status === 503) {
            throw new Error('Servicio de visión no disponible. API Key no configurada.');
        }
        throw new Error('Error al procesar el documento');
    }

    return response.json();
}

/**
 * Check if vision service is available.
 */
export async function checkVisionStatus(): Promise<{ configured: boolean; status: string }> {
    const response = await fetch(`${API_URL}/vision/status`);
    return response.json();
}
