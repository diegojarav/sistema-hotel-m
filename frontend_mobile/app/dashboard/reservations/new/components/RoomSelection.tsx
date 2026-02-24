'use client';

import { RoomCategory, RoomStatus, formatPrice, getCategoryColor } from '@/services/rooms';

interface RoomSelectionProps {
    formData: { checkIn: string; checkOut: string };
    onFormChange: (updates: { checkIn?: string; checkOut?: string }) => void;
    categories: RoomCategory[];
    availableRooms: RoomStatus[];
    selectedRooms: string[];
    onToggleRoom: (roomId: string) => void;
    nights: number;
}

export default function RoomSelection({
    formData, onFormChange,
    categories, availableRooms, selectedRooms, onToggleRoom,
    nights
}: RoomSelectionProps) {
    return (
        <>
            {/* Date Range Section */}
            <h3 className="text-lg font-semibold text-gray-900 mb-2 mt-6">Fechas de Estadía</h3>

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">📅 Check-in</label>
                    <input
                        type="date"
                        value={formData.checkIn}
                        onChange={(e) => {
                            const newCheckIn = e.target.value;
                            onFormChange({
                                checkIn: newCheckIn,
                                checkOut: formData.checkOut <= newCheckIn
                                    ? new Date(new Date(newCheckIn).getTime() + 86400000).toISOString().split('T')[0]
                                    : undefined
                            });
                        }}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
                <div>
                    <label className="text-gray-600 text-xs mb-1 block">📅 Check-out</label>
                    <input
                        type="date"
                        value={formData.checkOut}
                        min={formData.checkIn}
                        onChange={(e) => onFormChange({ checkOut: e.target.value })}
                        className="w-full px-3 py-3 bg-gray-50 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
            </div>

            {/* Nights Summary */}
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between">
                <span className="text-amber-700 text-sm">🌙 Total de Noches:</span>
                <span className="text-gray-900 font-bold text-lg">{nights}</span>
            </div>

            {/* Room Selection grouped by category */}
            <h3 className="text-lg font-semibold text-gray-900 mb-2 mt-6">
                Selección de Habitaciones
                {selectedRooms.length > 0 && (
                    <span className="text-sm font-normal text-amber-600 ml-2">
                        ({selectedRooms.length} seleccionada{selectedRooms.length !== 1 ? 's' : ''})
                    </span>
                )}
            </h3>

            {categories.map(cat => {
                const catRooms = availableRooms.filter(r => r.category_id === cat.id);
                const selectedInCat = catRooms.filter(r => selectedRooms.includes(r.room_id)).length;
                const priceColor = getCategoryColor(cat.base_price);

                if (catRooms.length === 0) return null;

                return (
                    <div key={cat.id} className="mb-4">
                        {/* Category header */}
                        <div className="flex justify-between items-center mb-2 p-3 bg-white rounded-xl border border-gray-200">
                            <div>
                                <p className="text-gray-900 font-semibold">{cat.name}</p>
                                <p className="text-gray-500 text-xs">
                                    👥 máx {cat.max_capacity} pers. — {catRooms.length} disponibles
                                </p>
                            </div>
                            <div className="text-right">
                                <p className={`font-bold ${priceColor}`}>
                                    {formatPrice(cat.base_price)}
                                </p>
                                <p className="text-gray-400 text-xs">/noche</p>
                                {selectedInCat > 0 && (
                                    <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                                        {selectedInCat} sel.
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Room buttons */}
                        <div className="grid grid-cols-3 gap-2">
                            {catRooms.map(room => (
                                <button
                                    key={room.room_id}
                                    type="button"
                                    onClick={() => onToggleRoom(room.room_id)}
                                    className={`py-4 px-2 rounded-xl font-bold text-sm transition-all ${
                                        selectedRooms.includes(room.room_id)
                                            ? 'bg-amber-500 text-white border-2 border-amber-400 shadow-lg shadow-amber-500/20'
                                            : 'bg-gray-50 text-gray-700 border-2 border-gray-200 hover:bg-gray-100'
                                    }`}
                                >
                                    <div className="text-lg">{room.internal_code || room.room_id}</div>
                                    {room.floor && (
                                        <div className="text-xs opacity-70">Piso {room.floor}</div>
                                    )}
                                </button>
                            ))}
                        </div>
                    </div>
                );
            })}

            {availableRooms.length === 0 && (
                <div className="p-4 rounded-xl bg-gray-50 border border-gray-200 text-gray-500 text-center">
                    No hay habitaciones disponibles para estas fechas
                </div>
            )}
        </>
    );
}
