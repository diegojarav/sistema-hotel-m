/**
 * RegistrarPagoModal - Modal for registering a payment against a reservation
 * ==========================================================================
 * Supports EFECTIVO / TRANSFERENCIA / POS with optional reference.
 * EFECTIVO requires an open caja session for the logged-in user.
 */

'use client';

import { useEffect, useMemo, useState } from 'react';
import { registrarPago, PaymentMethod, paymentMethodEmoji } from '@/services/transacciones';
import {
    AcceptedCurrency,
    formatAmount,
    getAcceptedCurrencies,
    getBaseCurrency,
} from '@/services/currencies';

interface Props {
    reservaId: string;
    guestName: string;
    saldoPendiente: number;
    onClose: () => void;
    onSuccess: () => void;
}

export default function RegistrarPagoModal({
    reservaId,
    guestName,
    saldoPendiente,
    onClose,
    onSuccess,
}: Props) {
    const [method, setMethod] = useState<PaymentMethod>('TRANSFERENCIA');
    const [amountStr, setAmountStr] = useState(saldoPendiente.toString());
    const [reference, setReference] = useState('');
    const [description, setDescription] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState('');

    // v1.10.0 Phase 2d — multi-currency
    const [currencies, setCurrencies] = useState<AcceptedCurrency[]>([]);
    const [baseCcy, setBaseCcy] = useState<string>('PYG');
    const [selectedCode, setSelectedCode] = useState<string>('PYG');
    const [currenciesLoading, setCurrenciesLoading] = useState(true);

    useEffect(() => {
        let alive = true;
        (async () => {
            try {
                const [base, list] = await Promise.all([
                    getBaseCurrency(),
                    getAcceptedCurrencies(),
                ]);
                if (!alive) return;
                setBaseCcy(base);
                setCurrencies(list);
                setSelectedCode(base);
            } catch (e) {
                // Best-effort — if the API is unreachable, default to PYG/base
                // and let the receptionist type the amount in base anyway.
                console.warn('Could not load currencies:', e);
            } finally {
                if (alive) setCurrenciesLoading(false);
            }
        })();
        return () => {
            alive = false;
        };
    }, []);

    const selectedCurrency = useMemo(
        () => currencies.find((c) => c.currency_code === selectedCode),
        [currencies, selectedCode],
    );
    const isBase = selectedCode === baseCcy;
    const rate = selectedCurrency?.exchange_rate ?? 1;
    const decimals = selectedCurrency?.decimal_places ?? 0;

    // When the selected currency changes, reset the amount to the saldo's
    // equivalent in the new currency (rounded to the currency's decimals).
    useEffect(() => {
        if (!selectedCurrency) return;
        const eqAmount = isBase
            ? saldoPendiente
            : Number((saldoPendiente / rate).toFixed(decimals));
        setAmountStr(eqAmount.toString());
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedCode]);

    const parsedAmount = useMemo(() => {
        // Spanish-style: dot thousands, comma decimal. Strip dots, swap comma → dot.
        const cleaned = amountStr.replace(/\./g, '').replace(',', '.');
        const n = parseFloat(cleaned);
        return isNaN(n) ? 0 : n;
    }, [amountStr]);

    const convertedToBase = !isBase ? Math.round(parsedAmount * rate) : parsedAmount;

    const handleSubmit = async () => {
        setError('');
        if (!parsedAmount || parsedAmount <= 0) {
            setError('Monto inválido');
            return;
        }

        setIsSubmitting(true);
        try {
            await registrarPago({
                reserva_id: reservaId,
                amount: parsedAmount,
                payment_method: method,
                reference_number: reference || undefined,
                description: description || undefined,
                currency_code: selectedCode,
            });
            onSuccess();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al registrar pago');
        } finally {
            setIsSubmitting(false);
        }
    };

    const setFullAmount = () => {
        const v = isBase
            ? saldoPendiente
            : Number((saldoPendiente / rate).toFixed(decimals));
        setAmountStr(v.toString());
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
            <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 max-w-md w-full shadow-2xl max-h-[90vh] overflow-y-auto">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <h3 className="text-xl font-bold text-gray-900">Registrar Pago</h3>
                        <p className="text-sm text-gray-500">{guestName} — Reserva #{reservaId}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
                    >
                        ✕
                    </button>
                </div>

                {/* Pending balance info (always shown in base currency) */}
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-4">
                    <p className="text-xs text-amber-700 uppercase font-semibold">Saldo pendiente</p>
                    <p className="text-xl font-bold text-amber-900">
                        {saldoPendiente.toLocaleString('es-PY')} {baseCcy === 'PYG' ? 'Gs' : baseCcy}
                    </p>
                </div>

                {/* v1.10.0 Phase 2d — Currency selector (only show when >1 accepted) */}
                {!currenciesLoading && currencies.length > 1 && (
                    <div className="mb-4">
                        <label className="text-sm font-semibold text-gray-700 mb-2 block">
                            💱 Moneda
                        </label>
                        <div className="flex gap-2 overflow-x-auto pb-1">
                            {currencies.map((c) => (
                                <button
                                    key={c.currency_code}
                                    type="button"
                                    onClick={() => setSelectedCode(c.currency_code)}
                                    className={`flex-shrink-0 px-4 py-2 rounded-full border-2 text-sm font-semibold transition-all ${
                                        selectedCode === c.currency_code
                                            ? 'border-emerald-500 bg-emerald-50 text-emerald-700'
                                            : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
                                    }`}
                                >
                                    {c.currency_symbol} {c.currency_code}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Method selector */}
                <div className="mb-4">
                    <label className="text-sm font-semibold text-gray-700 mb-2 block">Método de pago</label>
                    <div className="grid grid-cols-3 gap-2">
                        {(['EFECTIVO', 'TRANSFERENCIA', 'POS'] as PaymentMethod[]).map((m) => (
                            <button
                                key={m}
                                onClick={() => setMethod(m)}
                                className={`p-3 rounded-xl border-2 text-center transition-all ${
                                    method === m
                                        ? 'border-emerald-500 bg-emerald-50'
                                        : 'border-gray-200 bg-white hover:border-gray-300'
                                }`}
                            >
                                <div className="text-2xl">{paymentMethodEmoji(m)}</div>
                                <div className="text-xs font-medium text-gray-700 mt-1">
                                    {m === 'EFECTIVO' ? 'Efectivo' : m === 'TRANSFERENCIA' ? 'Transfer' : 'POS'}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {method === 'EFECTIVO' && (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-2 mb-3 text-xs text-blue-700">
                        ⚠️ EFECTIVO requiere que tengas una sesión de caja abierta.
                    </div>
                )}

                {/* Amount */}
                <div className="mb-4">
                    <div className="flex justify-between items-center mb-2">
                        <label className="text-sm font-semibold text-gray-700">
                            Monto ({selectedCurrency?.currency_symbol ?? baseCcy})
                        </label>
                        <button
                            type="button"
                            onClick={setFullAmount}
                            className="text-xs text-emerald-600 font-medium"
                        >
                            Usar saldo completo
                        </button>
                    </div>
                    <input
                        type="number"
                        inputMode={decimals === 0 ? 'numeric' : 'decimal'}
                        step={decimals === 0 ? 500 : 1}
                        value={amountStr}
                        onChange={(e) => setAmountStr(e.target.value)}
                        onFocus={(e) => e.currentTarget.select()}
                        className="w-full px-4 py-3 rounded-xl border border-gray-300 text-lg font-semibold focus:border-emerald-500 focus:outline-none"
                        placeholder="0"
                    />
                    {/* v1.10.0 Phase 2d — live conversion preview for non-base */}
                    {!isBase && selectedCurrency && parsedAmount > 0 && (
                        <p className="text-xs text-emerald-700 mt-2">
                            💱 Equivale a <strong>{formatAmount(convertedToBase, {
                                currency_code: baseCcy,
                                currency_symbol: baseCcy === 'PYG' ? '₲' : baseCcy,
                                decimal_places: baseCcy === 'PYG' ? 0 : 2,
                            })}</strong>
                            {' · '}
                            TC: 1 {selectedCode} = {rate.toLocaleString('es-PY')} {baseCcy}
                        </p>
                    )}
                </div>

                {/* Reference (TRANSFERENCIA / POS) */}
                {(method === 'TRANSFERENCIA' || method === 'POS') && (
                    <div className="mb-4">
                        <label className="text-sm font-semibold text-gray-700 mb-2 block">
                            Nro. de referencia {method === 'TRANSFERENCIA' ? '(transferencia)' : '(voucher POS)'}
                        </label>
                        <input
                            type="text"
                            value={reference}
                            onChange={(e) => setReference(e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:border-emerald-500 focus:outline-none"
                            placeholder="Ej: 12345678"
                        />
                    </div>
                )}

                {/* Description */}
                <div className="mb-4">
                    <label className="text-sm font-semibold text-gray-700 mb-2 block">
                        Descripción (opcional)
                    </label>
                    <input
                        type="text"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:border-emerald-500 focus:outline-none"
                        placeholder="Ej: Seña / Pago total / Resto"
                    />
                </div>

                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3 text-sm text-red-700">
                        {error}
                    </div>
                )}

                {/* Buttons */}
                <div className="flex gap-2">
                    <button
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="flex-1 py-3 rounded-xl border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 disabled:opacity-50"
                    >
                        Cancelar
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={isSubmitting}
                        className="flex-1 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white font-semibold disabled:opacity-50"
                    >
                        {isSubmitting ? 'Registrando...' : 'Confirmar'}
                    </button>
                </div>
            </div>
        </div>
    );
}
