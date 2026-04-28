'use client';

import { useEffect, useRef, useState } from 'react';

import { ClientType } from '@/services/pricing';
import { searchGuests, GuestSearchResult } from '@/services/guests';

interface FormData {
    apellidos: string;
    nombres: string;
    documento: string;
    nacionalidad: string;
    pais: string;
    fechaNacimiento: string;
    telefono: string;
    email: string;
    arrivalTime: string;
    checkIn: string;
    checkOut: string;
    precio: number;
    parkingNeeded: boolean;
    vehicleModel: string;
    vehiclePlate: string;
    // v1.10.0 Phase 2a-ext — color propagates to master GuestVehicle catalog
    vehicleColor: string;
    source: string;
    // v1.10.0 Phase 2a Bug #2 Fix A — explicit master Guest link
    guestId?: number | null;
}

interface GuestFormProps {
    formData: FormData;
    onFormChange: (updates: Partial<FormData>) => void;
    clientTypes: ClientType[];
    selectedClientType: ClientType | null;
    onClientTypeChange: (ct: ClientType) => void;
}

export default function GuestForm({ formData, onFormChange, clientTypes, selectedClientType, onClientTypeChange }: GuestFormProps) {
    // Guest autocomplete (Phase 2a Bug #2 Fix A — mobile parity)
    const [guestQuery, setGuestQuery] = useState('');
    const [guestResults, setGuestResults] = useState<GuestSearchResult[]>([]);
    const [showGuestSuggestions, setShowGuestSuggestions] = useState(false);
    const [pickedGuest, setPickedGuest] = useState<GuestSearchResult | null>(null);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Debounced search whenever the query changes (skip when a guest is locked in)
    useEffect(() => {
        if (pickedGuest) return;
        if (guestQuery.trim().length < 2) {
            setGuestResults([]);
            return;
        }
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(async () => {
            try {
                const results = await searchGuests(guestQuery, 10);
                setGuestResults(results);
                setShowGuestSuggestions(true);
            } catch (err) {
                console.warn('searchGuests failed:', err);
            }
        }, 250);
        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [guestQuery, pickedGuest]);

    const pickGuest = (g: GuestSearchResult) => {
        setPickedGuest(g);
        setGuestQuery(g.label);
        setShowGuestSuggestions(false);
        // Pre-fill the form with master guest data. Only fill blank fields —
        // never override what the user has already typed (e.g. via document scan).
        const updates: Partial<FormData> = { guestId: g.id };
        if (!formData.apellidos.trim() && g.last_name) updates.apellidos = g.last_name;
        if (!formData.nombres.trim() && g.first_name) updates.nombres = g.first_name;
        if (!formData.documento.trim() && g.document_number) updates.documento = g.document_number;
        if (!formData.telefono.trim() && g.phone) updates.telefono = g.phone;
        if (!formData.email.trim() && g.email) updates.email = g.email;
        onFormChange(updates);
    };

    const clearPick = () => {
        setPickedGuest(null);
        setGuestQuery('');
        setGuestResults([]);
        onFormChange({ guestId: null });
    };

    return (
        <>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Datos del Cliente</h3>

            {/* Guest autocomplete (Phase 2a Fix A) */}
            <div className="mb-4">
                <label className="text-gray-600 text-xs mb-1 block">
                    🔍 Buscar huésped existente
                </label>
                {pickedGuest ? (
                    <div className="flex items-center justify-between gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200">
                        <div className="text-sm">
                            <p className="font-semibold text-emerald-900">{pickedGuest.label}</p>
                            {pickedGuest.total_stays > 0 && (
                                <p className="text-xs text-emerald-700 mt-0.5">
                                    {pickedGuest.total_stays} estadía{pickedGuest.total_stays !== 1 ? 's' : ''} previa{pickedGuest.total_stays !== 1 ? 's' : ''}
                                </p>
                            )}
                        </div>
                        <button
                            type="button"
                            onClick={clearPick}
                            className="shrink-0 text-xs text-emerald-700 hover:text-emerald-900 font-medium underline"
                        >
                            Limpiar
                        </button>
                    </div>
                ) : (
                    <div className="relative">
                        <input
                            type="text"
                            value={guestQuery}
                            onChange={(e) => setGuestQuery(e.target.value)}
                            onFocus={() => guestResults.length > 0 && setShowGuestSuggestions(true)}
                            placeholder="Apellido, nombre, doc, email o teléfono…"
                            className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        />
                        {showGuestSuggestions && guestResults.length > 0 && (
                            <ul className="absolute z-10 mt-1 w-full max-h-64 overflow-auto bg-white border border-gray-200 rounded-xl shadow-lg">
                                {guestResults.map((g) => (
                                    <li
                                        key={g.id}
                                        onClick={() => pickGuest(g)}
                                        className="px-3 py-2 text-sm cursor-pointer hover:bg-amber-50 active:bg-amber-100 border-b border-gray-100 last:border-0"
                                    >
                                        <div className="font-medium text-gray-900">{g.last_name}, {g.first_name}</div>
                                        <div className="text-xs text-gray-500 flex flex-wrap gap-x-2">
                                            {g.document_number && <span>Doc {g.document_number}</span>}
                                            {g.phone && <span>📞 {g.phone}</span>}
                                            {g.email && <span>✉️ {g.email}</span>}
                                            {g.total_stays > 0 && <span>· {g.total_stays} est.</span>}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                        {guestQuery.trim().length >= 2 && guestResults.length === 0 && (
                            <p className="text-xs text-gray-400 mt-1">
                                Sin coincidencias. Continuá completando los datos abajo y se creará un nuevo huésped al guardar.
                            </p>
                        )}
                    </div>
                )}
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Apellidos</label>
                    <input
                        type="text"
                        value={formData.apellidos}
                        onChange={(e) => onFormChange({ apellidos: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        placeholder="García"
                    />
                </div>
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Nombres</label>
                    <input
                        type="text"
                        value={formData.nombres}
                        onChange={(e) => onFormChange({ nombres: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        placeholder="Juan"
                    />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Nro. Documento</label>
                    <input
                        type="text"
                        value={formData.documento}
                        onChange={(e) => onFormChange({ documento: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        placeholder="12345678"
                    />
                </div>
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Nacionalidad</label>
                    <input
                        type="text"
                        value={formData.nacionalidad}
                        onChange={(e) => onFormChange({ nacionalidad: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        placeholder="Paraguaya"
                    />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Teléfono</label>
                    <input
                        type="tel"
                        value={formData.telefono}
                        onChange={(e) => onFormChange({ telefono: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        placeholder="0981..."
                    />
                </div>
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Email</label>
                    <input
                        type="email"
                        value={formData.email || ''}
                        onChange={(e) => onFormChange({ email: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                        placeholder="correo@ejemplo.com"
                    />
                </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-3">
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">Hora de Llegada</label>
                    <input
                        type="time"
                        value={formData.arrivalTime}
                        onChange={(e) => onFormChange({ arrivalTime: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
            </div>

            {/* Parking Section */}
            <div className="mt-4 p-4 bg-white border border-gray-200 rounded-xl space-y-4">
                <h3 className="text-gray-900 font-semibold flex items-center gap-2">
                    <span>🚗</span> Estacionamiento
                </h3>

                <label className="flex items-center gap-3 cursor-pointer group">
                    <div className={`w-6 h-6 rounded border flex items-center justify-center transition-colors ${formData.parkingNeeded ? 'bg-amber-500 border-amber-500' : 'border-gray-300 bg-gray-50'}`}>
                        {formData.parkingNeeded && (
                            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                            </svg>
                        )}
                    </div>
                    <input
                        type="checkbox"
                        className="hidden"
                        checked={formData.parkingNeeded}
                        onChange={(e) => onFormChange({ parkingNeeded: e.target.checked })}
                    />
                    <span className="text-gray-700 text-sm font-medium group-hover:text-gray-900 transition-colors">
                        Requiere Estacionamiento
                    </span>
                </label>

                {formData.parkingNeeded && (
                    <>
                        <div className="grid grid-cols-2 gap-3 mt-3">
                            <div>
                                <label className="text-gray-600 text-xs mb-1 block">Modelo</label>
                                <input
                                    type="text"
                                    value={formData.vehicleModel}
                                    onChange={(e) => onFormChange({ vehicleModel: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                                    placeholder="Toyota Corolla"
                                />
                            </div>
                            <div>
                                <label className="text-gray-600 text-xs mb-1 block">Chapa</label>
                                <input
                                    type="text"
                                    value={formData.vehiclePlate}
                                    onChange={(e) => onFormChange({ vehiclePlate: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                                    placeholder="ABC 123"
                                />
                            </div>
                        </div>
                        {/* v1.10.0 Phase 2a-ext — color propagates to master vehicle catalog */}
                        <div className="mt-3">
                            <label className="text-gray-600 text-xs mb-1 block">Color</label>
                            <input
                                type="text"
                                value={formData.vehicleColor}
                                onChange={(e) => onFormChange({ vehicleColor: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                                placeholder="Blanco, Negro, Rojo..."
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Se guarda en el catálogo del huésped — habilita el lookup &quot;¿de quién es el auto blanco?&quot;.
                            </p>
                        </div>
                    </>
                )}
            </div>

            {/* Source Section */}
            <div className="mt-4">
                <label className="text-gray-600 text-xs mb-2 block">🌍 Origen de Reserva</label>
                <select
                    value={formData.source}
                    onChange={(e) => onFormChange({ source: e.target.value })}
                    className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                >
                    <option value="Direct">Directo (Recepción/Teléfono)</option>
                    <option value="Booking.com">Booking.com</option>
                    <option value="Airbnb">Airbnb</option>
                    <option value="Whatsapp">Whatsapp</option>
                    <option value="Facebook">Facebook</option>
                    <option value="Instagram">Instagram</option>
                    <option value="Google">Google</option>
                    <option value="App Móvil">App Móvil</option>
                </select>
            </div>

            {/* Client Type Selection */}
            <div className="mt-4">
                <label className="text-gray-600 text-xs mb-2 block">🏷️ Tipo de Cliente</label>
                <select
                    value={selectedClientType?.id ?? ''}
                    onChange={(e) => {
                        const ct = clientTypes.find(c => c.id === e.target.value);
                        if (ct) onClientTypeChange(ct);
                    }}
                    className="w-full p-3 rounded-xl border border-gray-300 bg-white text-gray-900 text-sm focus:ring-2 focus:ring-amber-400 focus:border-amber-400"
                >
                    <option value="" disabled>Seleccionar tipo de cliente</option>
                    {clientTypes.map(ct => (
                        <option key={ct.id} value={ct.id}>{ct.name}</option>
                    ))}
                </select>
            </div>
        </>
    );
}
