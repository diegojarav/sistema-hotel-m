'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

import { useAuth } from '@/hooks/useAuth';
import { getReservationById, getStatusBadge, updateReservationStatus, ReservationDetail } from '@/services/reservations';
import { downloadReservationPdf } from '@/services/documents';
import { getSaldoReserva, SaldoReserva, paymentMethodEmoji, paymentMethodLabel } from '@/services/transacciones';
import RegistrarPagoModal from '@/components/caja/RegistrarPagoModal';

function parseLocalDate(dateStr: string): Date {
    const [y, m, d] = dateStr.split('T')[0].split('-').map(Number);
    return new Date(y, m - 1, d);
}

function formatPrice(price: number): string {
    return price.toLocaleString('es-PY') + ' Gs';
}

export default function ReservationDetailPage() {
    const { isLoading: authLoading } = useAuth({ required: true });
    const params = useParams();
    const id = params.id as string;

    const [reservation, setReservation] = useState<ReservationDetail | null>(null);
    const [saldo, setSaldo] = useState<SaldoReserva | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');
    const [isUpdating, setIsUpdating] = useState(false);
    const [showCancelConfirm, setShowCancelConfirm] = useState(false);
    const [showPagoModal, setShowPagoModal] = useState(false);

    const loadSaldo = async () => {
        try {
            const s = await getSaldoReserva(id);
            setSaldo(s);
        } catch {
            // Saldo is optional — ignore errors
        }
    };

    useEffect(() => {
        if (authLoading || !id) return;

        async function fetchDetail() {
            try {
                const data = await getReservationById(id);
                setReservation(data);
                try {
                    const s = await getSaldoReserva(id);
                    setSaldo(s);
                } catch {
                    // Saldo is optional
                }
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Error al cargar la reserva');
            } finally {
                setIsLoading(false);
            }
        }

        fetchDetail();
    }, [authLoading, id]);

    const handlePagoRegistrado = async () => {
        setShowPagoModal(false);
        // Refresh both reservation (status may have changed) and saldo
        if (reservation) {
            try {
                const [updated, updatedSaldo] = await Promise.all([
                    getReservationById(reservation.id),
                    getSaldoReserva(reservation.id),
                ]);
                setReservation(updated);
                setSaldo(updatedSaldo);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Error al refrescar');
            }
        }
    };

    const handleStatusChange = async (newStatus: string, reason?: string) => {
        if (!reservation) return;
        setIsUpdating(true);
        try {
            await updateReservationStatus(reservation.id, newStatus, reason);
            const updated = await getReservationById(reservation.id);
            setReservation(updated);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cambiar estado');
        } finally {
            setIsUpdating(false);
            setShowCancelConfirm(false);
        }
    };

    const loading = authLoading || isLoading;

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 flex flex-col">
                <header className="bg-white border-b border-gray-200 px-4 py-4 sticky top-0 z-10">
                    <div className="flex items-center gap-3">
                        <Link href="/dashboard/calendar" className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                            <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                            </svg>
                        </Link>
                        <h1 className="text-xl font-bold text-gray-900">Detalle de Reserva</h1>
                    </div>
                </header>
                <main className="flex-1 p-4">
                    <div className="space-y-4">
                        <div className="h-32 bg-gray-200 rounded-2xl animate-pulse"></div>
                        <div className="h-48 bg-gray-200 rounded-2xl animate-pulse"></div>
                        <div className="h-32 bg-gray-200 rounded-2xl animate-pulse"></div>
                    </div>
                </main>
            </div>
        );
    }

    if (error || !reservation) {
        return (
            <div className="min-h-screen bg-gray-50 flex flex-col">
                <header className="bg-white border-b border-gray-200 px-4 py-4 sticky top-0 z-10">
                    <div className="flex items-center gap-3">
                        <Link href="/dashboard/calendar" className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                            <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                            </svg>
                        </Link>
                        <h1 className="text-xl font-bold text-gray-900">Detalle de Reserva</h1>
                    </div>
                </header>
                <main className="flex-1 p-4">
                    <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-600 text-center">
                        {error || 'Reserva no encontrada'}
                    </div>
                </main>
            </div>
        );
    }

    const badge = getStatusBadge(reservation.status);
    const checkIn = parseLocalDate(reservation.check_in);
    const checkOut = parseLocalDate(reservation.check_out);

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 px-4 py-4 sticky top-0 z-10">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Link href="/dashboard/calendar" className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center hover:bg-gray-200 transition-colors">
                            <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                            </svg>
                        </Link>
                        <div>
                            <h1 className="text-xl font-bold text-gray-900">Reserva #{reservation.id}</h1>
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badge.bgClass} ${badge.textClass}`}>
                                {badge.label}
                            </span>
                        </div>
                    </div>
                </div>
            </header>

            <main className="flex-1 p-4 space-y-4">
                {/* Guest Info */}
                <div className="bg-white border border-gray-200 rounded-2xl p-4">
                    <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Huesped</h2>
                    <p className="text-xl font-bold text-gray-900 mb-2">{reservation.guest_name}</p>
                    {reservation.contact_phone && (
                        <div className="flex items-center gap-2 text-gray-600 text-sm">
                            <span>Tel:</span>
                            <a href={`tel:${reservation.contact_phone}`} className="text-amber-600 font-medium">{reservation.contact_phone}</a>
                        </div>
                    )}
                    {reservation.contact_email && (
                        <div className="flex items-center gap-2 text-gray-600 text-sm mt-1">
                            <span>Email:</span>
                            <a href={`mailto:${reservation.contact_email}`} className="text-amber-600 font-medium">{reservation.contact_email}</a>
                        </div>
                    )}
                    {reservation.reserved_by && (
                        <p className="text-gray-500 text-sm mt-1">Reservado por: {reservation.reserved_by}</p>
                    )}
                </div>

                {/* Stay Dates */}
                <div className="bg-white border border-gray-200 rounded-2xl p-4">
                    <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Estadia</h2>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <p className="text-xs text-gray-400">Check-in</p>
                            <p className="text-lg font-semibold text-gray-900">{format(checkIn, 'd MMM yyyy', { locale: es })}</p>
                        </div>
                        <div>
                            <p className="text-xs text-gray-400">Check-out</p>
                            <p className="text-lg font-semibold text-gray-900">{format(checkOut, 'd MMM yyyy', { locale: es })}</p>
                        </div>
                    </div>
                    <div className="mt-3 flex items-center gap-4 text-sm text-gray-600">
                        <span>{reservation.stay_days} noche{reservation.stay_days !== 1 ? 's' : ''}</span>
                        {reservation.arrival_time && (
                            <span>Llegada: {reservation.arrival_time}</span>
                        )}
                    </div>
                </div>

                {/* Room & Price */}
                <div className="bg-white border border-gray-200 rounded-2xl p-4">
                    <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Habitacion y Precio</h2>
                    <div className="flex justify-between items-center">
                        <div>
                            <p className="text-lg font-bold text-gray-900">{reservation.room_internal_code || reservation.room_id}</p>
                            {reservation.room_type && <p className="text-sm text-gray-500">{reservation.room_type}</p>}
                        </div>
                        <div className="text-right">
                            <p className="text-2xl font-bold text-amber-600">{formatPrice(reservation.price)}</p>
                            {reservation.stay_days > 1 && (
                                <p className="text-xs text-gray-400">{formatPrice(reservation.price / reservation.stay_days)}/noche</p>
                            )}
                        </div>
                    </div>
                </div>

                {/* Saldo de Pagos */}
                {saldo && (
                    <div className="bg-white border border-gray-200 rounded-2xl p-4">
                        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Estado de Pago</h2>
                        <div className="grid grid-cols-3 gap-2 mb-3">
                            <div className="text-center p-2 bg-gray-50 rounded-lg">
                                <p className="text-xs text-gray-400">Total</p>
                                <p className="text-sm font-bold text-gray-900">{formatPrice(saldo.total)}</p>
                            </div>
                            <div className="text-center p-2 bg-green-50 rounded-lg">
                                <p className="text-xs text-gray-400">Pagado</p>
                                <p className="text-sm font-bold text-green-700">{formatPrice(saldo.paid)}</p>
                            </div>
                            <div className="text-center p-2 bg-amber-50 rounded-lg">
                                <p className="text-xs text-gray-400">Saldo</p>
                                <p className="text-sm font-bold text-amber-700">{formatPrice(saldo.pending)}</p>
                            </div>
                        </div>
                        {saldo.transacciones.length > 0 && (
                            <div className="space-y-1 border-t border-gray-100 pt-2 mt-2">
                                <p className="text-xs text-gray-400 uppercase">Pagos registrados</p>
                                {saldo.transacciones.map((t) => (
                                    <div key={t.id} className="flex justify-between items-center text-sm">
                                        <span className="text-gray-700">
                                            {paymentMethodEmoji(t.payment_method)} {paymentMethodLabel(t.payment_method)}
                                            {t.reference_number ? ` (${t.reference_number})` : ''}
                                        </span>
                                        <span className="font-medium text-gray-900">{formatPrice(t.amount)}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Source */}
                {reservation.source && (
                    <div className="bg-white border border-gray-200 rounded-2xl p-4">
                        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Origen</h2>
                        <p className="text-gray-900">{reservation.source}</p>
                    </div>
                )}

                {/* Parking */}
                {reservation.parking_needed && (
                    <div className="bg-white border border-gray-200 rounded-2xl p-4">
                        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Estacionamiento</h2>
                        <div className="flex items-center gap-2 text-gray-900">
                            <span className="text-lg">🚗</span>
                            <span>{reservation.vehicle_model || 'Vehiculo'}</span>
                            {reservation.vehicle_plate && (
                                <span className="ml-auto font-mono bg-gray-100 px-2 py-1 rounded text-sm">{reservation.vehicle_plate}</span>
                            )}
                        </div>
                    </div>
                )}

                {/* Cancellation Info */}
                {reservation.cancellation_reason && (
                    <div className="bg-red-50 border border-red-200 rounded-2xl p-4">
                        <h2 className="text-sm font-semibold text-red-500 uppercase tracking-wide mb-2">Cancelacion</h2>
                        <p className="text-red-700">{reservation.cancellation_reason}</p>
                        {reservation.cancelled_by && (
                            <p className="text-red-400 text-sm mt-1">Cancelado por: {reservation.cancelled_by}</p>
                        )}
                    </div>
                )}

                {/* Actions */}
                <div className="space-y-3 pt-2">
                    <button
                        onClick={() => downloadReservationPdf(reservation.id)}
                        className="w-full py-3 px-4 bg-amber-500 hover:bg-amber-600 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
                    >
                        Descargar PDF
                    </button>

                    {/* Registrar Pago — shown for all active states with pending balance */}
                    {['pendiente', 'reservada', 'señada', 'senada', 'confirmada'].includes(reservation.status.toLowerCase()) && saldo && saldo.pending > 0 && (
                        <button
                            onClick={() => setShowPagoModal(true)}
                            disabled={isUpdating}
                            className="w-full py-3 px-4 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
                        >
                            💰 Registrar Pago
                        </button>
                    )}

                    {['pendiente', 'reservada', 'señada', 'senada', 'confirmada'].includes(reservation.status.toLowerCase()) && (
                        <button
                            onClick={() => setShowCancelConfirm(true)}
                            disabled={isUpdating}
                            className="w-full py-3 px-4 bg-red-500 hover:bg-red-600 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
                        >
                            Cancelar Reserva
                        </button>
                    )}
                </div>
            </main>

            {/* Registrar Pago Modal */}
            {showPagoModal && reservation && saldo && (
                <RegistrarPagoModal
                    reservaId={reservation.id}
                    guestName={reservation.guest_name}
                    saldoPendiente={saldo.pending}
                    onClose={() => setShowPagoModal(false)}
                    onSuccess={handlePagoRegistrado}
                />
            )}

            {/* Cancel Confirmation Modal */}
            {showCancelConfirm && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
                        <h3 className="text-xl font-bold text-gray-900 text-center mb-2">
                            ¿Cancelar esta reserva?
                        </h3>
                        <p className="text-gray-500 text-sm text-center mb-6">
                            {reservation.guest_name} — {reservation.room_internal_code}
                        </p>
                        <div className="space-y-3">
                            <button
                                onClick={() => handleStatusChange('Cancelada', 'Cancelado desde app movil')}
                                disabled={isUpdating}
                                className="w-full py-3 px-4 bg-red-500 hover:bg-red-600 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors"
                            >
                                {isUpdating ? 'Cancelando...' : 'Si, cancelar'}
                            </button>
                            <button
                                onClick={() => setShowCancelConfirm(false)}
                                className="w-full py-2 px-4 text-gray-500 hover:text-gray-700 text-sm transition-colors"
                            >
                                No, volver
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
