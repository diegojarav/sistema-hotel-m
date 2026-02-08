'use client';

import { RoomCategory, formatPrice } from '@/services/rooms';
import { PriceCalculationResponse } from '@/services/pricing';

interface PriceSummaryProps {
    formData: { precio: number };
    onFormChange: (updates: { precio: number }) => void;
    pricingResponse: PriceCalculationResponse | null;
    selectedCategory: RoomCategory | null;
    selectedRooms: string[];
    nights: number;
    isSubmitting: boolean;
    submitSuccess: boolean;
    submitProgress: { current: number; total: number };
    submitError: string;
}

export default function PriceSummary({
    formData, onFormChange,
    pricingResponse, selectedCategory, selectedRooms,
    nights, isSubmitting, submitSuccess, submitProgress, submitError
}: PriceSummaryProps) {
    return (
        <>
            {/* Price Summary */}
            <div className="mt-6 p-4 bg-white/5 border border-white/10 rounded-xl">
                {pricingResponse ? (
                    <div className="mb-4 space-y-2 border-b border-white/10 pb-4">
                        <div className="flex justify-between text-sm text-slate-300">
                            <span>Base ({nights} noches):</span>
                            <span>{formatPrice(pricingResponse.breakdown.base_total)}</span>
                        </div>
                        {pricingResponse.breakdown.modifiers.map((mod, idx) => (
                            <div key={idx} className="flex justify-between text-sm" style={{ color: mod.amount < 0 ? '#4ade80' : '#f87171' }}>
                                <span>{mod.name} ({mod.percent > 0 ? '+' : ''}{mod.percent}%):</span>
                                <span>{mod.amount > 0 ? '+' : ''}{formatPrice(mod.amount)}</span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-slate-400">Precio por noche:</span>
                        <span className="text-white">{formatPrice(selectedCategory?.base_price || 0)}</span>
                    </div>
                )}

                <div className="flex justify-between items-center mb-2">
                    <span className="text-slate-400">Habitaciones:</span>
                    <span className="text-white">{Math.max(1, selectedRooms.length)}</span>
                </div>

                <div className="border-t border-white/10 pt-2 mt-2 flex justify-between items-center">
                    <span className="text-white font-semibold">💰 Total:</span>
                    <span className="text-2xl font-bold text-amber-400">
                        {formatPrice(formData.precio)}
                    </span>
                </div>

                <div className="mt-3">
                    <label className="text-slate-400 text-xs mb-1 block">Ajustar precio manualmente (Gs)</label>
                    <input
                        type="number"
                        min={0}
                        step={10000}
                        value={formData.precio}
                        onChange={(e) => onFormChange({ precio: parseFloat(e.target.value) || 0 })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
            </div>

            {submitError && (
                <div className="p-4 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-sm">
                    {submitError}
                </div>
            )}

            {/* Submit Button */}
            <button
                type="submit"
                disabled={isSubmitting || submitSuccess || selectedRooms.length === 0}
                className="w-full py-4 px-6 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white font-semibold rounded-xl shadow-lg shadow-amber-500/30 transition-all duration-200 flex items-center justify-center gap-3 disabled:opacity-50 mt-6"
            >
                {isSubmitting ? (
                    <>
                        <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Reservando {submitProgress.current} de {submitProgress.total}...
                    </>
                ) : (
                    <>
                        ✅ Confirmar Reserva
                        {selectedRooms.length > 0 && (
                            <span className="text-amber-200">
                                ({selectedRooms.length} hab. × {nights} noche{nights !== 1 ? 's' : ''})
                            </span>
                        )}
                    </>
                )}
            </button>
        </>
    );
}
