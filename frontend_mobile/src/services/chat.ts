/**
 * Hotel Munich - Chat Service (AI Agent)
 * ========================================
 * Handles communication with the internal AI agent.
 */

import { apiPost } from './api';

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
    const data = await apiPost<AgentResponse>('/agent/query', { prompt: message });
    return data.response;
}

/**
 * Generate a unique message ID.
 */
export function generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}
