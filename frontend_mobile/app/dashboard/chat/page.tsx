'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { getHotelConfig } from '@/services/settings';
import { sendMessage } from '@/services/chat';
import { useAuth } from '@/hooks/useAuth';
import { ApiError } from '@/services/api';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
}

export default function ChatPage() {
    const { isLoading: authLoading, isAuthenticated, logout } = useAuth({ required: true });
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [hotelName, setHotelName] = useState('Mi Hotel');

    // Load welcome message once authenticated
    useEffect(() => {
        if (authLoading || !isAuthenticated) return;

        getHotelConfig().then(config => {
            setHotelName(config.hotel_name);
            setMessages([{
                id: 'welcome',
                role: 'assistant',
                content: `¡Hola! Soy el asistente del ${config.hotel_name}. ¿En qué puedo ayudarte hoy? Puedo responder sobre reservas, disponibilidad, huéspedes y más.`
            }]);
        });
    }, [authLoading, isAuthenticated]);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Send message
    const handleSend = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            id: `msg_${Date.now()}`,
            role: 'user',
            content: input.trim(),
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await sendMessage(userMessage.content);

            const assistantMessage: Message = {
                id: `msg_${Date.now()}_ai`,
                role: 'assistant',
                content: response || 'Lo siento, no pude procesar tu solicitud.',
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (error) {
            if (error instanceof ApiError && error.status === 401) {
                logout();
                return;
            }

            const errorMessage: Message = {
                id: `msg_${Date.now()}_error`,
                role: 'assistant',
                content: '❌ Error de conexión. Por favor, intenta de nuevo.',
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
            inputRef.current?.focus();
        }
    };

    // Handle Enter key
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    if (authLoading || !isAuthenticated) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
                <div className="animate-spin h-8 w-8 border-4 border-amber-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    return (
        <div className="flex flex-col min-h-[100dvh] bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 relative">
            {/* Header */}
            <header className="sticky top-0 bg-slate-900/90 backdrop-blur-lg border-b border-white/10 px-4 py-4 flex-shrink-0 z-20">
                <div className="flex items-center gap-3">
                    <Link
                        href="/dashboard"
                        className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center hover:bg-white/20 transition-colors"
                    >
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                    </Link>

                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                        </div>
                        <div>
                            <h1 className="text-lg font-bold text-white">Asistente Hotel</h1>
                            <div className="flex items-center gap-1.5">
                                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                                <span className="text-xs text-slate-400">En línea • Gemini 2.5 Flash</span>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            {/* Messages Area */}
            <div className="flex-1 p-4 space-y-4">
                {messages.map((message) => (
                    <div
                        key={message.id}
                        className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-[85%] px-4 py-3 rounded-2xl ${message.role === 'user'
                                ? 'bg-blue-600 text-white rounded-br-md'
                                : 'bg-white/10 text-white rounded-bl-md'
                                }`}
                        >
                            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                        </div>
                    </div>
                ))}

                {/* Thinking indicator */}
                {isLoading && (
                    <div className="flex justify-start">
                        <div className="bg-white/10 px-4 py-3 rounded-2xl rounded-bl-md">
                            <div className="flex items-center gap-1">
                                <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"></span>
                                <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></span>
                                <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></span>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input Area - Sticky Bottom */}
            <div className="sticky bottom-0 left-0 w-full p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] bg-slate-900 border-t border-white/10 z-30">
                <div className="flex gap-3 max-w-4xl mx-auto">
                    <input
                        ref={inputRef}
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Escribe un mensaje..."
                        disabled={isLoading}
                        className="flex-1 px-4 py-3 bg-white/10 border border-white/10 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/50 disabled:opacity-50"
                    />
                    <button
                        onClick={handleSend}
                        disabled={!input.trim() || isLoading}
                        className="w-12 h-12 rounded-xl bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white flex items-center justify-center shadow-lg shadow-blue-500/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    );
}
