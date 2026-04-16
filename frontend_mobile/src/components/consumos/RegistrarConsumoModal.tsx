/**
 * RegistrarConsumoModal — Add a product/service charge to a reservation
 * ======================================================================
 * Lists active products grouped by category, lets the user pick quantity,
 * and submits to POST /api/v1/consumos. Warns on low stock.
 */

'use client';

import { useEffect, useMemo, useState } from 'react';
import {
    listProducts,
    registrarConsumo,
    groupByCategory,
    categoryEmoji,
    formatPriceGs,
    Producto,
} from '@/services/consumos';

interface Props {
    reservaId: string;
    guestName: string;
    onClose: () => void;
    onSuccess: () => void;
}

export default function RegistrarConsumoModal({
    reservaId,
    guestName,
    onClose,
    onSuccess,
}: Props) {
    const [products, setProducts] = useState<Producto[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [quantity, setQuantity] = useState(1);
    const [description, setDescription] = useState('');
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        listProducts()
            .then(setProducts)
            .catch((err) => setError(err instanceof Error ? err.message : 'Error al cargar productos'))
            .finally(() => setLoading(false));
    }, []);

    const selected = useMemo(
        () => products.find((p) => p.id === selectedId) || null,
        [products, selectedId],
    );

    const grouped = useMemo(() => groupByCategory(products), [products]);

    const stockLow =
        selected?.is_stocked &&
        selected.stock_minimum !== null &&
        selected.stock_current !== null &&
        selected.stock_current <= selected.stock_minimum;

    const insufficientStock =
        selected?.is_stocked &&
        selected.stock_current !== null &&
        selected.stock_current < quantity;

    const total = selected ? selected.price * quantity : 0;

    const handleSubmit = async () => {
        if (!selected) return;
        setError('');
        setSubmitting(true);
        try {
            await registrarConsumo({
                reserva_id: reservaId,
                producto_id: selected.id,
                quantity,
                description: description || undefined,
            });
            onSuccess();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al registrar consumo');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
            <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 max-w-md w-full shadow-2xl max-h-[90vh] overflow-y-auto">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <h3 className="text-xl font-bold text-gray-900">Registrar Consumo</h3>
                        <p className="text-sm text-gray-500">
                            {guestName} — Reserva #{reservaId}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200"
                    >
                        ✕
                    </button>
                </div>

                {loading ? (
                    <div className="py-8 text-center text-gray-500">Cargando productos...</div>
                ) : products.length === 0 ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
                        No hay productos activos. Agregá productos desde PC &gt; Inventario.
                    </div>
                ) : (
                    <>
                        {/* Product selector grouped by category */}
                        <div className="mb-4">
                            <label className="text-sm font-semibold text-gray-700 mb-2 block">
                                Producto
                            </label>
                            <div className="space-y-3 max-h-64 overflow-y-auto">
                                {Object.entries(grouped).map(([cat, items]) => (
                                    <div key={cat}>
                                        <div className="text-xs uppercase text-gray-500 mb-1 font-semibold">
                                            {categoryEmoji(cat)} {cat}
                                        </div>
                                        <div className="space-y-1">
                                            {items.map((p) => {
                                                const isSelected = selectedId === p.id;
                                                const outOfStock =
                                                    p.is_stocked &&
                                                    (p.stock_current ?? 0) <= 0;
                                                return (
                                                    <button
                                                        key={p.id}
                                                        type="button"
                                                        disabled={outOfStock}
                                                        onClick={() => setSelectedId(p.id)}
                                                        className={`w-full text-left p-3 rounded-lg border-2 transition-all ${
                                                            isSelected
                                                                ? 'border-blue-500 bg-blue-50'
                                                                : 'border-gray-200 bg-white hover:border-gray-300'
                                                        } ${outOfStock ? 'opacity-40 cursor-not-allowed' : ''}`}
                                                    >
                                                        <div className="flex justify-between items-center">
                                                            <span className="font-medium text-gray-900 text-sm">
                                                                {p.name}
                                                            </span>
                                                            <span className="text-sm text-gray-700 font-semibold">
                                                                {formatPriceGs(p.price)}
                                                            </span>
                                                        </div>
                                                        {p.is_stocked && (
                                                            <div className="text-xs text-gray-500 mt-0.5">
                                                                Stock: {p.stock_current ?? 0}
                                                                {outOfStock && ' · sin stock'}
                                                            </div>
                                                        )}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Quantity + description */}
                        {selected && (
                            <>
                                <div className="mb-3">
                                    <label className="text-sm font-semibold text-gray-700 mb-2 block">
                                        Cantidad
                                    </label>
                                    <div className="flex items-center gap-3">
                                        <button
                                            type="button"
                                            onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                                            className="w-10 h-10 rounded-lg bg-gray-100 text-lg font-bold hover:bg-gray-200"
                                        >
                                            −
                                        </button>
                                        <input
                                            type="number"
                                            min={1}
                                            value={quantity}
                                            onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                                            className="flex-1 px-3 py-2 rounded-lg border border-gray-300 text-center text-lg font-semibold focus:border-blue-500 focus:outline-none"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setQuantity((q) => q + 1)}
                                            className="w-10 h-10 rounded-lg bg-gray-100 text-lg font-bold hover:bg-gray-200"
                                        >
                                            +
                                        </button>
                                    </div>
                                </div>

                                {stockLow && (
                                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-2 mb-3 text-xs text-amber-700">
                                        ⚠️ Stock bajo: quedan {selected.stock_current} unidad(es).
                                    </div>
                                )}

                                {insufficientStock && (
                                    <div className="bg-red-50 border border-red-200 rounded-lg p-2 mb-3 text-xs text-red-700">
                                        ❌ Stock insuficiente. Solo hay {selected.stock_current} disponibles.
                                    </div>
                                )}

                                <div className="mb-4">
                                    <label className="text-sm font-semibold text-gray-700 mb-2 block">
                                        Nota (opcional)
                                    </label>
                                    <input
                                        type="text"
                                        value={description}
                                        onChange={(e) => setDescription(e.target.value)}
                                        placeholder="Ej: consumido durante la cena"
                                        className="w-full px-3 py-2 rounded-lg border border-gray-300 focus:border-blue-500 focus:outline-none"
                                    />
                                </div>

                                <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 mb-4">
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm font-semibold text-blue-900">Total</span>
                                        <span className="text-xl font-bold text-blue-900">
                                            {formatPriceGs(total)}
                                        </span>
                                    </div>
                                </div>
                            </>
                        )}

                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3 text-sm text-red-700">
                                {error}
                            </div>
                        )}

                        <div className="flex gap-2">
                            <button
                                onClick={onClose}
                                disabled={submitting}
                                className="flex-1 py-3 rounded-xl border border-gray-300 text-gray-700 font-semibold hover:bg-gray-50 disabled:opacity-50"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleSubmit}
                                disabled={submitting || !selected || insufficientStock}
                                className="flex-1 py-3 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-semibold disabled:opacity-50"
                            >
                                {submitting ? 'Registrando...' : 'Registrar'}
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
