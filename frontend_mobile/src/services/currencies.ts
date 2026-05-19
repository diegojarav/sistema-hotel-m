/**
 * Hotel Munich — Currencies Service (v1.10.0 — Phase 2d)
 * =======================================================
 * Read-only access for the mobile app to:
 *   - the property's base currency
 *   - the list of accepted currencies (with current exchange rates)
 *   - the catalogue (for the future "manage currencies on phone" feature)
 *
 * Currency MUTATION endpoints (add / update rate / remove) are admin-only
 * and intentionally NOT exposed here — those live on the PC app.
 */
import { apiGet } from './api';

export interface AcceptedCurrency {
    id: number;
    property_id: string;
    currency_code: string;          // ISO 4217 (PYG, USD, BRL, ...)
    currency_name: string;          // "Dólar estadounidense"
    currency_symbol: string;        // "US$"
    decimal_places: number;
    exchange_rate: number;          // to base (1 unit = N base units)
    rate_updated_at: string | null;
    is_active: boolean;
    sort_order: number;
}

export interface CurrencyCatalogEntry {
    code: string;
    name: string;
    symbol: string;
    decimals: number;
    country: string;
}

export async function getBaseCurrency(): Promise<string> {
    const r = await apiGet<{ base_currency: string }>('/currencies/base');
    return r.base_currency;
}

export async function getAcceptedCurrencies(): Promise<AcceptedCurrency[]> {
    return apiGet<AcceptedCurrency[]>('/currencies?active_only=true');
}

export async function getCurrencyCatalog(): Promise<CurrencyCatalogEntry[]> {
    return apiGet<CurrencyCatalogEntry[]>('/currencies/catalog');
}

/**
 * Format an amount with a currency symbol + correct decimal/separator
 * conventions. Mirrors the backend `CurrencyService.format_amount` so
 * the same value renders identically on PC, mobile, and PDFs.
 *
 * PYG  → "₲ 750.000"
 * USD  → "US$ 100,00"
 * BRL  → "R$ 1.234,50"
 */
export function formatAmount(
    amount: number,
    currency: AcceptedCurrency | { currency_code: string; currency_symbol: string; decimal_places: number },
    withSymbol = true,
): string {
    if (amount == null || isNaN(amount)) return '';
    const decimals = currency.decimal_places ?? 2;
    const rounded = Number(amount.toFixed(decimals));

    let formatted: string;
    if (decimals === 0) {
        // Integer: thousands separator = dot
        formatted = Math.round(rounded).toLocaleString('es-PY');
    } else {
        // Spanish convention: thousands dot, decimal comma.
        // toLocaleString('es-PY') with 2 decimals gives this directly.
        formatted = rounded.toLocaleString('es-PY', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }
    return withSymbol ? `${currency.currency_symbol} ${formatted}` : formatted;
}
