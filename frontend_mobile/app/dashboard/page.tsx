'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getHotelConfig, getMealsConfig, type MealsConfig } from '@/services/settings';
import { useAuth } from '@/hooks/useAuth';
import { getSummary, ChannelManagerSummary } from '@/services/channels';
import { getKitchenReport } from '@/services/meals';

export default function DashboardPage() {
    const { isLoading, logout } = useAuth({ required: true });
    const [hotelName, setHotelName] = useState('Mi Hotel');
    const [chSummary, setChSummary] = useState<ChannelManagerSummary | null>(null);
    const [mealsConfig, setMealsConfig] = useState<MealsConfig | null>(null);
    const [breakfastsToday, setBreakfastsToday] = useState<number | null>(null);

    // Load hotel name on mount
    useEffect(() => {
        getHotelConfig().then(config => {
            setHotelName(config.hotel_name);
        });
        // Load channel manager summary in parallel (non-blocking)
        getSummary().then(setChSummary).catch(() => setChSummary(null));
        // Meals config (non-blocking). When enabled, fetch today's breakfast count.
        getMealsConfig().then((cfg) => {
            setMealsConfig(cfg);
            if (cfg.meals_enabled) {
                const today = new Date().toISOString().slice(0, 10);
                getKitchenReport(today)
                    .then((rep) => setBreakfastsToday(rep.total_with_breakfast))
                    .catch(() => setBreakfastsToday(null));
            }
        }).catch(() => setMealsConfig(null));
    }, []);

    const chErrors = (chSummary?.error ?? 0) + (chSummary?.warning ?? 0);
    const chTotal = chSummary?.total ?? 0;

    // Show loading while checking auth
    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="animate-spin h-8 w-8 border-4 border-amber-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
                        <svg
                            className="w-5 h-5 text-white"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                            />
                        </svg>
                    </div>
                    <h1 className="text-xl font-bold text-gray-900">{hotelName}</h1>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 p-6">
                {/* Welcome Message */}
                <div className="mb-8">
                    <h2 className="text-2xl font-bold text-gray-900 mb-2">
                        Bienvenido al Panel Móvil
                    </h2>
                    <p className="text-gray-600">
                        Gestiona las operaciones del hotel desde tu dispositivo
                    </p>
                </div>

                {/* Action Grid */}
                <div className="grid grid-cols-2 gap-4 mb-8">
                    {/* Mis Reservas */}
                    <Link
                        href="/dashboard/calendar"
                        className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm"
                    >
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shadow-lg">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                        </div>
                        <span className="text-gray-900 font-medium text-sm">Mis Reservas</span>
                    </Link>

                    {/* Disponibilidad */}
                    <Link
                        href="/dashboard/availability"
                        className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm"
                    >
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-green-400 to-green-600 flex items-center justify-center shadow-lg">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <span className="text-gray-900 font-medium text-sm">Disponibilidad</span>
                    </Link>

                    {/* Asistente IA */}
                    <Link
                        href="/dashboard/chat"
                        className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm"
                    >
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-purple-400 to-blue-600 flex items-center justify-center shadow-lg">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                            </svg>
                        </div>
                        <span className="text-gray-900 font-medium text-sm">Asistente IA</span>
                    </Link>

                    {/* Nueva Reserva */}
                    <Link
                        href="/dashboard/reservations/new"
                        className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm"
                    >
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-amber-400 to-orange-600 flex items-center justify-center shadow-lg">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                        </div>
                        <span className="text-gray-900 font-medium text-sm">Nueva Reserva</span>
                    </Link>

                    {/* Caja */}
                    <Link
                        href="/dashboard/caja"
                        className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm"
                    >
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                        </div>
                        <span className="text-gray-900 font-medium text-sm">Caja &amp; Pagos</span>
                    </Link>

                    {/* Cocina / Desayunos (v1.7.0 — Phase 4) — only when meals enabled */}
                    {mealsConfig?.meals_enabled && (
                        <Link
                            href="/dashboard/meals"
                            className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm"
                        >
                            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-orange-400 to-pink-500 flex items-center justify-center shadow-lg">
                                <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                                </svg>
                            </div>
                            <span className="text-gray-900 font-medium text-sm">Cocina</span>
                            <span className="text-xs text-gray-500">
                                {breakfastsToday !== null
                                    ? `Desayunos hoy: ${breakfastsToday}`
                                    : 'Ver reporte'}
                            </span>
                        </Link>
                    )}

                    {/* Channel Manager (v1.5.0) */}
                    <Link
                        href="/dashboard/channels"
                        className="bg-white border border-gray-200 rounded-2xl p-6 flex flex-col items-center gap-3 hover:bg-gray-50 transition-all duration-200 active:scale-95 shadow-sm relative"
                    >
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center shadow-lg">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                            </svg>
                        </div>
                        <span className="text-gray-900 font-medium text-sm">Canales</span>
                        {chSummary !== null && (
                            <span className="text-xs text-gray-500">
                                {chTotal} feeds
                                {chErrors > 0 && (
                                    <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
                                        {chErrors} alerta{chErrors === 1 ? '' : 's'}
                                    </span>
                                )}
                            </span>
                        )}
                    </Link>
                </div>

                {/* Logout Button */}
                <button
                    onClick={logout}
                    className="w-full py-4 px-6 bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white font-semibold rounded-xl shadow-lg shadow-red-500/20 transition-all duration-200 transform hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-3"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                    Cerrar Sesión
                </button>
            </main>

            {/* Footer */}
            <footer className="p-4 text-center">
                <p className="text-gray-400 text-xs">
                    © 2026 {hotelName} Management System
                </p>
            </footer>
        </div>
    );
}
