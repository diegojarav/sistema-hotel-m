/**
 * Mobile — Kitchen Report (read-only) — v1.7.0 Phase 4
 * =====================================================
 * Read-only view of today's / tomorrow's breakfast count.
 * When meals are disabled: shows a friendly disabled state.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

import { useAuth } from '@/hooks/useAuth';
import { getMealsConfig, type MealsConfig } from '@/services/settings';
import { getKitchenReport, type KitchenReport } from '@/services/meals';

function isoDate(d: Date): string {
    return d.toISOString().slice(0, 10);
}

export default function MealsPage() {
    const { isLoading: authLoading } = useAuth({ required: true });
    const [mealsConfig, setMealsConfig] = useState<MealsConfig | null>(null);
    const [report, setReport] = useState<KitchenReport | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [offsetDays, setOffsetDays] = useState(0); // 0 = hoy, 1 = mañana

    const targetDate = (() => {
        const d = new Date();
        d.setDate(d.getDate() + offsetDays);
        return d;
    })();

    const load = async () => {
        setLoading(true);
        setError('');
        try {
            const cfg = await getMealsConfig();
            setMealsConfig(cfg);
            if (cfg.meals_enabled) {
                const r = await getKitchenReport(isoDate(targetDate));
                setReport(r);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar el reporte');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (authLoading) return;
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading, offsetDays]);

    if (authLoading || loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="animate-spin h-8 w-8 border-4 border-orange-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    // Meals disabled — friendly empty state
    if (mealsConfig && !mealsConfig.meals_enabled) {
        return (
            <div className="min-h-screen bg-gray-50">
                <Header />
                <main className="p-6">
                    <div className="bg-white rounded-2xl p-8 shadow-sm border border-gray-200 text-center">
                        <div className="text-5xl mb-4">🍽️</div>
                        <h2 className="text-lg font-bold text-gray-900 mb-2">
                            Servicio de comidas no habilitado
                        </h2>
                        <p className="text-gray-600 text-sm">
                            Este hotel no tiene activado el servicio de comidas.
                            Puede habilitarlo desde la Configuración (PC).
                        </p>
                    </div>
                </main>
            </div>
        );
    }

    const modeLabels: Record<string, string> = {
        INCLUIDO: 'Desayuno incluido en la tarifa',
        OPCIONAL_PERSONA: 'Opcional — por persona',
        OPCIONAL_HABITACION: 'Opcional — por habitación',
    };
    const modeLabel = report?.mode ? (modeLabels[report.mode] || '—') : '—';

    return (
        <div className="min-h-screen bg-gray-50">
            <Header />
            <main className="p-4 pb-20">
                {/* Date selector (Hoy / Mañana) */}
                <div className="flex gap-2 mb-4">
                    <button
                        type="button"
                        onClick={() => setOffsetDays(0)}
                        className={`px-4 py-2 rounded-xl font-medium text-sm transition ${
                            offsetDays === 0
                                ? 'bg-orange-500 text-white shadow-md'
                                : 'bg-white border border-gray-200 text-gray-700'
                        }`}
                    >
                        Hoy
                    </button>
                    <button
                        type="button"
                        onClick={() => setOffsetDays(1)}
                        className={`px-4 py-2 rounded-xl font-medium text-sm transition ${
                            offsetDays === 1
                                ? 'bg-orange-500 text-white shadow-md'
                                : 'bg-white border border-gray-200 text-gray-700'
                        }`}
                    >
                        Mañana
                    </button>
                </div>

                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl mb-4 text-sm">
                        {error}
                    </div>
                )}

                {/* Summary */}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-200 mb-4">
                    <p className="text-xs text-gray-500 mb-1">{modeLabel}</p>
                    <p className="text-xs text-gray-500 mb-4">
                        {targetDate.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}
                    </p>
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-gray-600">Total desayunos</p>
                            <p className="text-4xl font-bold text-orange-600">
                                {report?.total_with_breakfast ?? 0}
                            </p>
                        </div>
                        {report && report.total_without > 0 && (
                            <div className="text-right">
                                <p className="text-sm text-gray-600">Sin desayuno</p>
                                <p className="text-2xl font-semibold text-gray-400">
                                    {report.total_without}
                                </p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Detail list */}
                <h2 className="text-sm font-semibold text-gray-700 mb-2 px-1">Detalle por habitación</h2>
                {!report?.rooms || report.rooms.length === 0 ? (
                    <div className="bg-white rounded-2xl p-6 text-center text-gray-500 text-sm border border-gray-200">
                        Sin reservas activas para esta fecha.
                    </div>
                ) : (
                    <div className="space-y-2">
                        {report.rooms.map((row) => (
                            <div
                                key={row.reservation_id}
                                className={`bg-white rounded-xl p-4 border ${
                                    row.checkout_today ? 'border-yellow-300 bg-yellow-50' : 'border-gray-200'
                                }`}
                            >
                                <div className="flex items-center justify-between mb-1">
                                    <p className="font-semibold text-gray-900">
                                        Hab. {row.internal_code}
                                        {row.checkout_today && (
                                            <span className="ml-2 text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-200 text-yellow-800">
                                                Sale hoy
                                            </span>
                                        )}
                                    </p>
                                    <p className="text-sm text-gray-600">
                                        {row.breakfast_guests}/{row.guests_count} pax
                                    </p>
                                </div>
                                <p className="text-sm text-gray-700">{row.guest_name}</p>
                                <p className="text-xs text-gray-500 mt-1">
                                    {row.plan_name || '—'} · Check-out: {row.checkout_date}
                                </p>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
}

function Header() {
    return (
        <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
            <div className="flex items-center gap-3">
                <Link href="/dashboard" className="text-gray-500 hover:text-gray-900">
                    ←
                </Link>
                <h1 className="text-xl font-bold text-gray-900">👨‍🍳 Cocina</h1>
            </div>
        </header>
    );
}
