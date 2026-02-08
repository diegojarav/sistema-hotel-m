/**
 * Hotel Munich - Chat Service (AI Agent)
 * ========================================
 * Handles communication with the internal AI agent.
 */

import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

// Types
export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

export interface AgentResponse {
    response: string;
}

/**
 * Send a message to the AI agent.
 */
export async function sendMessage(message: string): Promise<string> {
    const token = typeof window !== 'undefined'
        ? localStorage.getItem(ACCESS_TOKEN_KEY)
        : null;

    if (!token) {
        throw new Error('No autorizado. Por favor, inicie sesión.');
    }

    const response = await fetch(`${API_URL}/agent/query`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ prompt: message }),
    });

    if (!response.ok) {
        if (response.status === 401) {
            // Clear token and throw specific error
            localStorage.removeItem(ACCESS_TOKEN_KEY);
            throw new Error('UNAUTHORIZED');
        }
        throw new Error('Error al comunicarse con el asistente');
    }

    const data: AgentResponse = await response.json();
    return data.response;
}

/**
 * Generate a unique message ID.
 */
export function generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}
