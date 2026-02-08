'use client';

import { RoomCategory, RoomStatus, formatPrice, getCategoryColor } from '@/services/rooms';

interface RoomSelectionProps {
    formData: { checkIn: string; checkOut: string };
    onFormChange: (updates: { checkIn?: string; checkOut?: string }) => void;
    categories: RoomCategory[];
    selectedCategory: RoomCategory | null;
    onCategoryChange: (cat: RoomCategory) => void;
    availableRooms: RoomStatus[];
    selectedRooms: string[];
    onToggleRoom: (roomId: string) => void;
    nights: number;
}

export default function RoomSelection({
    formData, onFormChange,
    categories, selectedCategory, onCategoryChange,
    availableRooms, selectedRooms, onToggleRoom,
    nights
}: RoomSelectionProps) {
    return (
        <>
            {/* Date Range Section */}
            <h3 className="text-lg font-semibold text-white mb-2 mt-6">Fechas de Estadía</h3>

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-slate-400 text-xs mb-1 block">📅 Check-in</label>
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
                        className="w-full px-3 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
                <div>
                    <label className="text-slate-400 text-xs mb-1 block">📅 Check-out</label>
                    <input
                        type="date"
                        value={formData.checkOut}
                        min={formData.checkIn}
                        onChange={(e) => onFormChange({ checkOut: e.target.value })}
                        className="w-full px-3 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                    />
                </div>
            </div>

            {/* Nights Summary */}
            <div className="p-3 bg-amber-500/20 border border-amber-500/30 rounded-xl flex items-center justify-between">
                <span className="text-amber-300 text-sm">🌙 Total de Noches:</span>
                <span className="text-white font-bold text-lg">{nights}</span>
            </div>

            {/* Category Selection */}
            <h3 className="text-lg font-semibold text-white mb-2 mt-6">Categoría de Habitación</h3>

            <div className="grid grid-cols-1 gap-2">
                {categories.map(cat => {
                    const priceColor = getCategoryColor(cat.base_price);
                    const isSelected = selectedCategory?.id === cat.id;

                    return (
                        <button
                            key={cat.id}
                            type="button"
                            onClick={() => onCategoryChange(cat)}
                            className={`p-4 rounded-xl border-2 transition-all text-left ${isSelected
                                ? 'bg-amber-500/20 border-amber-500 shadow-lg shadow-amber-500/20'
                                : 'bg-white/5 border-white/10 hover:bg-white/10'
                                }`}
                        >
                            <div className="flex justify-between items-start">
                                <div>
                                    <p className="text-white font-semibold">{cat.name}</p>
                                    <p className="text-slate-400 text-xs">👥 máx {cat.max_capacity} personas</p>
                                </div>
                                <div className="text-right">
                                    <p className={`font-bold ${priceColor}`}>
                                        {formatPrice(cat.base_price)}
                                    </p>
                                    <p className="text-slate-500 text-xs">/noche</p>
                                </div>
                            </div>
                        </button>
                    );
                })}
            </div>

            {/* Room Selection */}
            {selectedCategory && (
                <>
                    <h3 className="text-lg font-semibold text-white mb-2 mt-6">
                        Habitaciones Disponibles
                        <span className="text-sm font-normal text-slate-400 ml-2">
                            ({selectedRooms.length} seleccionada{selectedRooms.length !== 1 ? 's' : ''})
                        </span>
                    </h3>

                    {availableRooms.length > 0 ? (
                        <div className="grid grid-cols-3 gap-2">
                            {availableRooms.map(room => (
                                <button
                                    key={room.room_id}
                                    type="button"
                                    onClick={() => onToggleRoom(room.room_id)}
                                    className={`py-4 px-2 rounded-xl font-bold text-sm transition-all ${selectedRooms.includes(room.room_id)
                                        ? 'bg-amber-500 text-white border-2 border-amber-400 shadow-lg shadow-amber-500/30'
                                        : 'bg-white/5 text-slate-300 border-2 border-white/10 hover:bg-white/10'
                                        }`}
                                >
                                    <div className="text-lg">{room.internal_code || room.room_id}</div>
                                    {room.floor && (
                                        <div className="text-xs opacity-70">Piso {room.floor}</div>
                                    )}
                                </button>
                            ))}
                        </div>
                    ) : (
                        <div className="p-4 rounded-xl bg-slate-500/20 border border-slate-500/30 text-slate-400 text-center">
                            No hay habitaciones disponibles de esta categoría
                        </div>
                    )}
                </>
            )}
        </>
    );
}
