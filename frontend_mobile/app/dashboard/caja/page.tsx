/**
 * Mobile — Caja (Cash Register) Management Page
 * ================================================
 * Open / close the cash register session, view current movements, close with
 * reconciliation of expected vs declared balance.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

import { useAuth } from '@/hooks/useAuth';
import {
    getCajaActual,
    getCajaDetalle,
    abrirCaja,
    cerrarCaja,
    formatGs,
    CajaSesion,
} from '@/services/caja';
import { paymentMethodEmoji, paymentMethodLabel, PaymentMethod } from '@/services/transacciones';

interface CajaDetalle extends CajaSesion {
    transactions: Array<{
        id: number;
        reserva_id: string | null;
        amount: number;
        payment_method: string;
        reference_number: string | null;
        description: string | null;
        created_at: string;
        created_by: string | null;
        voided: boolean;
        void_reason: string | null;
    }>;
    total_efectivo: number;
    total_transferencia: number;
    total_pos: number;
}

export default function CajaPage() {
    const { isLoading: authLoading } = useAuth({ required: true });
    const [sesion, setSesion] = useState<CajaSesion | null>(null);
    const [detalle, setDetalle] = useState<CajaDetalle | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Abrir form
    const [showAbrir, setShowAbrir] = useState(false);
    const [openingBalance, setOpeningBalance] = useState('0');
    const [openNotes, setOpenNotes] = useState('');

    // Cerrar form
    const [showCerrar, setShowCerrar] = useState(false);
    const [closingDeclared, setClosingDeclared] = useState('');
    const [closeNotes, setCloseNotes] = useState('');

    const [isSubmitting, setIsSubmitting] = useState(false);

    const loadSesion = async () => {
        try {
            const current = await getCajaActual();
            setSesion(current);
            if (current) {
                const det = await getCajaDetalle(current.id);
                setDetalle(det as CajaDetalle);
                setClosingDeclared(
                    ((current.opening_balance || 0) + (det.total_efectivo || 0)).toString()
                );
            } else {
                setDetalle(null);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar caja');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (authLoading) return;
        loadSesion();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [authLoading]);

    const handleAbrir = async () => {
        setError('');
        const balance = parseFloat(openingBalance);
        if (isNaN(balance) || balance < 0) {
            setError('Balance inicial inválido');
            return;
        }
        setIsSubmitting(true);
        try {
            await abrirCaja({ opening_balance: balance, notes: openNotes || undefined });
            setShowAbrir(false);
            setOpeningBalance('0');
            setOpenNotes('');
            await loadSesion();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al abrir caja');
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleCerrar = async () => {
        if (!sesion) return;
        setError('');
        const declared = parseFloat(closingDeclared);
        if (isNaN(declared) || declared < 0) {
            setError('Monto declarado inválido');
            return;
        }
        setIsSubmitting(true);
        try {
            await cerrarCaja({
                session_id: sesion.id,
                closing_balance_declared: declared,
                notes: closeNotes || undefined,
            });
            setShowCerrar(false);
            setCloseNotes('');
            await loadSesion();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cerrar caja');
        } finally {
            setIsSubmitting(false);
        }
    };

    if (authLoading || loading) {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-4 border-emerald-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    const expected = sesion ? (sesion.opening_balance || 0) + (detalle?.total_efectivo || 0) : 0;

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
                    <h1 className="text-xl font-bold text-gray-900">Caja</h1>
                </div>
            </header>

            <main className="flex-1 p-4 space-y-4">
                {error && (
                    <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
                        {error}
                    </div>
                )}

                {/* NO SESSION OPEN */}
                {!sesion && (
                    <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
                        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
                            <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                            </svg>
                        </div>
                        <h2 className="text-lg font-bold text-gray-900 mb-2">No hay caja abierta</h2>
                        <p className="text-sm text-gray-500 mb-4">
                            Abrí una sesión de caja antes de registrar pagos en efectivo.
                        </p>
                        {!showAbrir ? (
                            <button
                                onClick={() => setShowAbrir(true)}
                                className="w-full py-3 bg-emerald-500 hover:bg-emerald-600 text-white font-semibold rounded-xl"
                            >
                                💰 Abrir Caja
                            </button>
                        ) : (
                            <div className="space-y-3 text-left">
                                <div>
                                    <label className="text-sm font-semibold text-gray-700 block mb-1">
                                        Balance inicial (Gs)
                                    </label>
                                    <input
                                        type="number"
                                        value={openingBalance}
                                        onChange={(e) => setOpeningBalance(e.target.value)}
                                        className="w-full px-3 py-2 rounded-lg border border-gray-300 focus:border-emerald-500 focus:outline-none"
                                    />
                                </div>
                                <div>
                                    <label className="text-sm font-semibold text-gray-700 block mb-1">
                                        Notas (opcional)
                                    </label>
                                    <input
                                        type="text"
                                        value={openNotes}
                                        onChange={(e) => setOpenNotes(e.target.value)}
                                        className="w-full px-3 py-2 rounded-lg border border-gray-300"
                                        placeholder="Ej: Turno mañana"
                                    />
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setShowAbrir(false)}
                                        disabled={isSubmitting}
                                        className="flex-1 py-2 border border-gray-300 rounded-lg font-semibold text-gray-700"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        onClick={handleAbrir}
                                        disabled={isSubmitting}
                                        className="flex-1 py-2 bg-emerald-500 text-white rounded-lg font-semibold disabled:opacity-50"
                                    >
                                        {isSubmitting ? 'Abriendo...' : 'Confirmar'}
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* SESSION OPEN */}
                {sesion && detalle && (
                    <>
                        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4">
                            <div className="flex justify-between items-center mb-3">
                                <div>
                                    <p className="text-xs text-emerald-600 uppercase font-semibold">Caja abierta</p>
                                    <p className="text-sm text-gray-700">
                                        {sesion.user_name} • {format(new Date(sesion.opened_at), "d MMM 'a las' HH:mm", { locale: es })}
                                    </p>
                                </div>
                                <span className="px-2 py-1 bg-emerald-500 text-white text-xs font-bold rounded-full">
                                    ABIERTA
                                </span>
                            </div>

                            <div className="grid grid-cols-2 gap-3 mb-3">
                                <div className="bg-white p-3 rounded-lg">
                                    <p className="text-xs text-gray-400">Apertura</p>
                                    <p className="text-lg font-bold text-gray-900">{formatGs(sesion.opening_balance)}</p>
                                </div>
                                <div className="bg-white p-3 rounded-lg">
                                    <p className="text-xs text-gray-400">Efectivo ingresado</p>
                                    <p className="text-lg font-bold text-gray-900">{formatGs(detalle.total_efectivo)}</p>
                                </div>
                            </div>
                            <div className="bg-white p-3 rounded-lg border border-emerald-300">
                                <p className="text-xs text-emerald-600 uppercase">Esperado en caja</p>
                                <p className="text-2xl font-bold text-emerald-700">{formatGs(expected)}</p>
                            </div>
                        </div>

                        {/* Other payment methods totals */}
                        <div className="bg-white border border-gray-200 rounded-2xl p-4">
                            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                                Movimientos del turno
                            </h2>
                            <div className="space-y-2">
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-700">💵 Efectivo</span>
                                    <span className="font-bold text-gray-900">{formatGs(detalle.total_efectivo)}</span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-700">🏦 Transferencia</span>
                                    <span className="font-bold text-gray-900">{formatGs(detalle.total_transferencia)}</span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-700">💳 POS</span>
                                    <span className="font-bold text-gray-900">{formatGs(detalle.total_pos)}</span>
                                </div>
                            </div>
                        </div>

                        {/* Transactions list */}
                        {detalle.transactions.length > 0 && (
                            <div className="bg-white border border-gray-200 rounded-2xl p-4">
                                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                                    Transacciones ({detalle.transactions.filter(t => !t.voided).length})
                                </h2>
                                <div className="space-y-2 max-h-64 overflow-y-auto">
                                    {detalle.transactions.map((t) => (
                                        <div
                                            key={t.id}
                                            className={`p-2 rounded-lg border ${
                                                t.voided ? 'bg-gray-50 border-gray-200 opacity-50' : 'border-gray-100'
                                            }`}
                                        >
                                            <div className="flex justify-between items-center">
                                                <span className="text-sm text-gray-700">
                                                    {paymentMethodEmoji(t.payment_method as PaymentMethod)}{' '}
                                                    {paymentMethodLabel(t.payment_method as PaymentMethod)}
                                                </span>
                                                <span className="font-bold text-sm text-gray-900">
                                                    {formatGs(t.amount)}
                                                </span>
                                            </div>
                                            <div className="text-xs text-gray-400 mt-1">
                                                {t.reserva_id && `Reserva #${t.reserva_id} • `}
                                                {format(new Date(t.created_at), 'HH:mm')}
                                                {t.voided && ` • ANULADA: ${t.void_reason}`}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Cerrar caja */}
                        {!showCerrar ? (
                            <button
                                onClick={() => setShowCerrar(true)}
                                className="w-full py-3 bg-red-500 hover:bg-red-600 text-white font-semibold rounded-xl"
                            >
                                Cerrar Caja
                            </button>
                        ) : (
                            <div className="bg-white border border-red-200 rounded-2xl p-4 space-y-3">
                                <h3 className="font-bold text-gray-900">Cerrar Caja</h3>
                                <div>
                                    <label className="text-sm font-semibold text-gray-700 block mb-1">
                                        Balance declarado (Gs)
                                    </label>
                                    <input
                                        type="number"
                                        value={closingDeclared}
                                        onChange={(e) => setClosingDeclared(e.target.value)}
                                        className="w-full px-3 py-2 rounded-lg border border-gray-300 text-lg font-bold focus:border-red-500 focus:outline-none"
                                    />
                                    <p className="text-xs text-gray-400 mt-1">
                                        Esperado: {formatGs(expected)}
                                    </p>
                                </div>
                                <div>
                                    <label className="text-sm font-semibold text-gray-700 block mb-1">
                                        Notas (opcional)
                                    </label>
                                    <input
                                        type="text"
                                        value={closeNotes}
                                        onChange={(e) => setCloseNotes(e.target.value)}
                                        className="w-full px-3 py-2 rounded-lg border border-gray-300"
                                        placeholder="Ej: Cierre sin novedad"
                                    />
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setShowCerrar(false)}
                                        disabled={isSubmitting}
                                        className="flex-1 py-2 border border-gray-300 rounded-lg font-semibold text-gray-700"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        onClick={handleCerrar}
                                        disabled={isSubmitting}
                                        className="flex-1 py-2 bg-red-500 text-white rounded-lg font-semibold disabled:opacity-50"
                                    >
                                        {isSubmitting ? 'Cerrando...' : 'Confirmar Cierre'}
                                    </button>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}
