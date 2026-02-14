'use client';

import { formatPrice } from '@/services/rooms';
import { CategoryPricingResult } from '../page';

interface PriceSummaryProps {
    formData: { precio: number };
    onFormChange: (updates: { precio: number }) => void;
    pricingResults: CategoryPricingResult[];
    selectedRooms: string[];
    nights: number;
    isSubmitting: boolean;
    submitSuccess: boolean;
    submitProgress: { current: number; total: number };
    submitError: string;
}

export default function PriceSummary({
    formData, onFormChange,
    pricingResults, selectedRooms,
    nights, isSubmitting, submitSuccess, submitProgress, submitError
}: PriceSummaryProps) {
    return (
        <>
            {/* Price Summary */}
            <div className="mt-6 p-4 bg-white border border-gray-200 rounded-xl">
                {pricingResults.length > 0 ? (
                    <div className="mb-4 space-y-3 border-b border-gray-200 pb-4">
                        {pricingResults.map((result) => (
                            <div key={result.catId} className="space-y-1">
                                <div className="flex justify-between text-sm text-gray-900 font-medium">
                                    <span>{result.catName} ({result.roomCount} hab.)</span>
                                    <span>{formatPrice(result.response.final_price * result.roomCount)}</span>
                                </div>
                                <div className="flex justify-between text-xs text-gray-500 pl-3">
                                    <span>Base ({nights} noches):</span>
                                    <span>{formatPrice(result.response.breakdown.base_total)}</span>
                                </div>
                                {result.response.breakdown.modifiers.map((mod, idx) => (
                                    <div
                                        key={idx}
                                        className="flex justify-between text-xs pl-3"
                                        style={{ color: mod.amount < 0 ? '#4ade80' : '#f87171' }}
                                    >
                                        <span>{mod.name} ({mod.percent > 0 ? '+' : ''}{mod.percent.toFixed(0)}%):</span>
                                        <span>{mod.amount > 0 ? '+' : ''}{formatPrice(mod.amount)}</span>
                                    </div>
                                ))}
                                {result.roomCount > 1 && (
                                    <div className="flex justify-between text-xs text-gray-500 pl-3">
                                        <span>{formatPrice(result.response.final_price)} x {result.roomCount} hab.</span>
                                        <span>{formatPrice(result.response.final_price * result.roomCount)}</span>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-gray-500">Seleccione habitaciones para ver precios</span>
                    </div>
                )}

                <div className="flex justify-between items-center mb-2">
                    <span className="text-gray-500">Habitaciones:</span>
                    <span className="text-gray-900">{selectedRooms.length}</span>
                </div>

                <div className="border-t border-gray-200 pt-2 mt-2 flex justify-between items-center">
                    <span className="text-gray-900 font-semibold">💰 Total:</span>
                    <span className="text-2xl font-bold text-amber-600">
                        {formatPrice(formData.precio)}
                    </span>
                </div>

                <div className="mt-3">
                    <label className="text-gray-600 text-xs mb-1 block">Ajustar precio manualmente (Gs)</label>
                    <input
                        type="number"
                        min={0}
                        step={10000}
                        value={formData.precio}
                        onChange={(e) => onFormChange({ precio: parseFloat(e.target.value) || 0 })}
                        className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
            </div>

            {submitError && (
                <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-600 text-sm">
                    {submitError}
                </div>
            )}

            {/* Submit Button */}
            <button
                type="submit"
                disabled={isSubmitting || submitSuccess || selectedRooms.length === 0}
                className="w-full py-4 px-6 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white font-semibold rounded-xl shadow-lg shadow-amber-500/20 transition-all duration-200 flex items-center justify-center gap-3 disabled:opacity-50 mt-6"
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
