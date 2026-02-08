/**
 * Hotel Munich - Vision Service (Gemini 2.5 Flash)
 * ==================================================
 * Handles document scanning via Gemini Vision AI.
 */

import { apiPostFormData, apiGet } from './api';

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
    const formData = new FormData();
    formData.append('file', file);
    return apiPostFormData<VisionResponse>('/vision/extract-data', formData);
}

/**
 * Check if vision service is available.
 */
export async function checkVisionStatus(): Promise<{ configured: boolean; status: string }> {
    return apiGet<{ configured: boolean; status: string }>('/vision/status', null);
}
