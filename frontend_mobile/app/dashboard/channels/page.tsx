/**
 * Mobile — Channel Manager (read-only) — v1.5.0 Phase 2
 * =====================================================
 * Recepcionist sees feed health + can trigger manual sync.
 * Add/edit/delete remains on PC admin.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

import { useAuth } from '@/hooks/useAuth';
import {
    listFeeds,
    syncAllFeeds,
    syncFeed,
    formatLastSync,
    badgeEmoji,
    badgeColor,
    ChannelFeed,
} from '@/services/channels';

export default function ChannelsPage() {
    const { isLoading: authLoading } = useAuth({ required: true });
    const [feeds, setFeeds] = useState<ChannelFeed[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [syncing, setSyncing] = useState(false);
    const [syncResult, setSyncResult] = useState<string | null>(null);

    const loadFeeds = async () => {
        try {
            const data = await listFeeds();
            setFeeds(data);
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar feeds');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (authLoading) return;
        loadFeeds();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading]);

    const handleSyncAll = async () => {
        setSyncing(true);
        setSyncResult(null);
        try {
            const result = await syncAllFeeds();
            setSyncResult(
                `${result.feeds_synced ?? 0} feeds · ${result.created} nuevas · ${result.updated} actualizadas` +
                    (result.flagged_for_review ? ` · ${result.flagged_for_review} para revisar` : '') +
                    (result.conflicts ? ` · ${result.conflicts} conflictos` : '')
            );
            await loadFeeds();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al sincronizar');
        } finally {
            setSyncing(false);
        }
    };

    const handleSyncOne = async (id: number) => {
        setSyncing(true);
        setSyncResult(null);
        try {
            const result = await syncFeed(id);
            setSyncResult(
                `Feed #${id}: ${result.created} nuevas · ${result.updated} actualizadas` +
                    (result.flagged_for_review ? ` · ${result.flagged_for_review} para revisar` : '')
            );
            await loadFeeds();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al sincronizar');
        } finally {
            setSyncing(false);
        }
    };

    if (authLoading || loading) {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-4 border-emerald-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    const counts = {
        total: feeds.length,
        healthy: feeds.filter((f) => f.health_badge === 'healthy').length,
        warning: feeds.filter((f) => f.health_badge === 'warning').length,
        error: feeds.filter((f) => f.health_badge === 'error').length,
        unknown: feeds.filter((f) => f.health_badge === 'unknown').length,
    };

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 px-4 py-4 sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <Link
                        href="/dashboard"
                        className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center hover:bg-gray-200"
                    >
                        <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                    </Link>
                    <div>
                        <h1 className="text-xl font-bold text-gray-900">Channel Manager</h1>
                        <p className="text-xs text-gray-500">Solo lectura — admin en PC</p>
                    </div>
                </div>
            </header>

            <main className="flex-1 p-4 space-y-4">
                {error && (
                    <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">{error}</div>
                )}

                {/* Health summary */}
                <div className="grid grid-cols-4 gap-2">
                    <div className="bg-white rounded-xl p-3 text-center border border-gray-200">
                        <p className="text-2xl font-bold text-emerald-600">{counts.healthy}</p>
                        <p className="text-xs text-gray-500">🟢 OK</p>
                    </div>
                    <div className="bg-white rounded-xl p-3 text-center border border-gray-200">
                        <p className="text-2xl font-bold text-amber-600">{counts.warning}</p>
                        <p className="text-xs text-gray-500">🟡 Aviso</p>
                    </div>
                    <div className="bg-white rounded-xl p-3 text-center border border-gray-200">
                        <p className="text-2xl font-bold text-red-600">{counts.error}</p>
                        <p className="text-xs text-gray-500">🔴 Error</p>
                    </div>
                    <div className="bg-white rounded-xl p-3 text-center border border-gray-200">
                        <p className="text-2xl font-bold text-gray-500">{counts.unknown}</p>
                        <p className="text-xs text-gray-500">⚪ Nuevo</p>
                    </div>
                </div>

                {/* Sync all button */}
                <button
                    onClick={handleSyncAll}
                    disabled={syncing || feeds.length === 0}
                    className="w-full py-3 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white font-semibold rounded-xl"
                >
                    {syncing ? 'Sincronizando...' : '🔄 Sincronizar todas'}
                </button>

                {syncResult && (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-sm text-emerald-700">
                        ✓ {syncResult}
                    </div>
                )}

                {/* Feed list */}
                {feeds.length === 0 ? (
                    <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
                        <p className="text-gray-500">No hay feeds configurados.</p>
                        <p className="text-xs text-gray-400 mt-2">
                            Configurá los feeds desde la PC admin (Configuración → Channel Manager).
                        </p>
                    </div>
                ) : (
                    <div className="space-y-2">
                        {feeds.map((feed) => {
                            const colors = badgeColor(feed.health_badge);
                            return (
                                <div
                                    key={feed.id}
                                    className="bg-white border border-gray-200 rounded-2xl p-4"
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <div className="flex-1">
                                            <p className="font-bold text-gray-900">{feed.room_label}</p>
                                            <p className="text-sm text-gray-500">{feed.source}</p>
                                        </div>
                                        <span
                                            className={`px-2 py-1 rounded-full text-xs font-semibold ${colors.bg} ${colors.text}`}
                                        >
                                            {badgeEmoji(feed.health_badge)} {feed.health_badge}
                                        </span>
                                    </div>
                                    <div className="text-xs text-gray-500 space-y-1">
                                        <div>Última sync: {formatLastSync(feed.last_synced_at)}</div>
                                        {feed.consecutive_failures > 0 && (
                                            <div className="text-red-600">
                                                ⚠️ {feed.consecutive_failures} fallo(s) consecutivo(s)
                                            </div>
                                        )}
                                        {feed.last_sync_error && (
                                            <details className="mt-1">
                                                <summary className="text-red-600 cursor-pointer">Ver error</summary>
                                                <pre className="text-xs text-red-700 bg-red-50 p-2 rounded mt-1 overflow-auto">
                                                    {feed.last_sync_error}
                                                </pre>
                                            </details>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => handleSyncOne(feed.id)}
                                        disabled={syncing}
                                        className="w-full mt-3 py-2 border border-emerald-500 text-emerald-600 rounded-lg text-sm font-semibold hover:bg-emerald-50 disabled:opacity-50"
                                    >
                                        {syncing ? '...' : '🔄 Sincronizar este feed'}
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                )}
            </main>
        </div>
    );
}
