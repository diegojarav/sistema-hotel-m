/**
 * Hotel Munich - Channel Manager Service (v1.5.0 Phase 2)
 * =========================================================
 * Read-only iCal feed status for the mobile dashboard widget + channels page.
 */

import { apiGet, apiPost } from './api';

export type HealthBadge = 'healthy' | 'warning' | 'error' | 'unknown';

export interface ChannelFeed {
    id: number;
    room_id: string;
    room_label: string;
    source: string;
    ical_url: string;
    last_synced_at: string | null;
    sync_enabled: boolean;
    created_at: string | null;
    last_sync_status: 'OK' | 'ERROR' | 'NEVER';
    last_sync_error: string | null;
    consecutive_failures: number;
    last_sync_attempted_at: string | null;
    health_badge: HealthBadge;
}

export interface SyncResult {
    created: number;
    updated: number;
    flagged_for_review: number;
    conflicts: number;
    errors: string[];
    feeds_synced?: number;
    status?: 'OK' | 'ERROR';
    duration_ms?: number;
}

/**
 * List all configured iCal feeds (with health fields).
 * Requires admin role.
 */
export async function listFeeds(): Promise<ChannelFeed[]> {
    return apiGet<ChannelFeed[]>('/ical/feeds');
}

/**
 * Trigger a sync of all enabled feeds.
 */
export async function syncAllFeeds(): Promise<SyncResult> {
    return apiPost<SyncResult>('/ical/feeds/sync', {});
}

/**
 * Trigger a sync of a single feed.
 */
export async function syncFeed(feedId: number): Promise<SyncResult> {
    return apiPost<SyncResult>(`/ical/feeds/${feedId}/sync`, {});
}

/**
 * Aggregate feed counts for the dashboard widget.
 */
export interface ChannelManagerSummary {
    total: number;
    healthy: number;
    warning: number;
    error: number;
    unknown: number;
}

export async function getSummary(): Promise<ChannelManagerSummary> {
    try {
        const feeds = await listFeeds();
        return {
            total: feeds.length,
            healthy: feeds.filter((f) => f.health_badge === 'healthy').length,
            warning: feeds.filter((f) => f.health_badge === 'warning').length,
            error: feeds.filter((f) => f.health_badge === 'error').length,
            unknown: feeds.filter((f) => f.health_badge === 'unknown').length,
        };
    } catch {
        return { total: 0, healthy: 0, warning: 0, error: 0, unknown: 0 };
    }
}

/**
 * Format ISO timestamp to a friendly local string. Returns "Nunca" if null.
 */
export function formatLastSync(iso: string | null): string {
    if (!iso) return 'Nunca';
    try {
        const d = new Date(iso);
        return d.toLocaleString('es-PY', {
            day: '2-digit',
            month: '2-digit',
            year: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return iso.slice(0, 19).replace('T', ' ');
    }
}

export function badgeEmoji(badge: HealthBadge): string {
    return { healthy: '🟢', warning: '🟡', error: '🔴', unknown: '⚪' }[badge];
}

export function badgeColor(badge: HealthBadge): { bg: string; text: string } {
    return {
        healthy: { bg: 'bg-emerald-500/15', text: 'text-emerald-700' },
        warning: { bg: 'bg-amber-500/15', text: 'text-amber-700' },
        error: { bg: 'bg-red-500/15', text: 'text-red-700' },
        unknown: { bg: 'bg-gray-500/15', text: 'text-gray-700' },
    }[badge];
}
