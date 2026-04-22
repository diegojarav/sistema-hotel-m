/**
 * EnviarEmailModal — Queue a reservation confirmation email (v1.8.0 — Phase 5)
 * =============================================================================
 * Pre-fills the guest's `contact_email` when available.
 * On 429 (rate-limit exceeded) shows the backend message verbatim.
 * On success, calls `onSuccess(email)` so the parent can refresh history.
 */

'use client';

import { useState } from 'react';
import { sendReservationEmail } from '@/services/email';

interface Props {
    reservaId: string;
    guestName: string;
    initialEmail?: string | null;
    onClose: () => void;
    onSuccess: (recipient: string) => void;
}

export default function EnviarEmailModal({
    reservaId,
    guestName,
    initialEmail,
    onClose,
    onSuccess,
}: Props) {
    const [email, setEmail] = useState(initialEmail || '');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async () => {
        setError('');
        const trimmed = email.trim();
        if (!trimmed || !trimmed.includes('@')) {
            setError('Ingresá un email válido');
            return;
        }

        setIsSubmitting(true);
        try {
            // Only pass the override when it differs from what the guest already had.
            // That way the backend won't mutate contact_email unnecessarily.
            const override = trimmed !== (initialEmail || '').trim() ? trimmed : null;
            await sendReservationEmail(reservaId, override);
            onSuccess(trimmed);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al enviar correo');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
            <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 max-w-md w-full shadow-2xl">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <h3 className="text-xl font-bold text-gray-900">Enviar por correo</h3>
                        <p className="text-sm text-gray-500">
                            {guestName} — Reserva #{reservaId}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200 disabled:opacity-50"
                    >
                        ✕
                    </button>
                </div>

                <p className="text-sm text-gray-600 mb-3">
                    Se enviará la confirmación con el PDF de la reserva al email indicado.
                </p>

                <label className="block text-sm font-medium text-gray-700 mb-1">
                    Email destinatario
                </label>
                <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="guest@email.com"
                    disabled={isSubmitting}
                    className="w-full px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:ring-2 focus:ring-amber-400 focus:border-amber-400 mb-2"
                />
                {initialEmail && email === initialEmail && (
                    <p className="text-xs text-gray-500 mb-2">
                        Email registrado del huésped.
                    </p>
                )}

                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl p-2 mb-3">
                        {error}
                    </div>
                )}

                <div className="flex gap-2 mt-4">
                    <button
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="flex-1 py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold rounded-xl transition-colors disabled:opacity-50"
                    >
                        Cancelar
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={isSubmitting}
                        className="flex-1 py-3 px-4 bg-amber-500 hover:bg-amber-600 text-white font-semibold rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {isSubmitting ? (
                            <>
                                <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                Enviando...
                            </>
                        ) : (
                            <>📧 Enviar</>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
