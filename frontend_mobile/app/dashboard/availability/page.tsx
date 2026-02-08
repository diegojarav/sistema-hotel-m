'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
    RoomStatus,
    getRoomsStatus,
    getStatusDisplay,
    formatPrice,
    getCategoryColor,
} from '@/services/rooms';
import { useAuth } from '@/hooks/useAuth';

export default function AvailabilityPage() {
    const { isLoading: authLoading } = useAuth({ required: true });
    const [rooms, setRooms] = useState<RoomStatus[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        if (authLoading) return;

        async function fetchRooms() {
            try {
                const data = await getRoomsStatus();
                setRooms(data);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Error desconocido');
            } finally {
                setIsLoading(false);
            }
        }

        fetchRooms();
    }, [authLoading]);

    // Group rooms by floor
    const roomsByFloor = rooms.reduce((acc, room) => {
        const floor = room.floor || 1;
        if (!acc[floor]) acc[floor] = [];
        acc[floor].push(room);
        return acc;
    }, {} as Record<number, RoomStatus[]>);

    // Sort floors descending (highest floor first)
    const sortedFloors = Object.keys(roomsByFloor)
        .map(Number)
        .sort((a, b) => b - a);

    // Count stats
    const freeCount = rooms.filter(r => r.status.toLowerCase() === 'libre').length;
    const occupiedCount = rooms.filter(r => r.status.toLowerCase() === 'ocupada').length;

    const loading = authLoading || isLoading;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col">
            {/* Header with Back Button */}
            <header className="bg-white/5 backdrop-blur-lg border-b border-white/10 px-4 py-4 sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <Link
                        href="/dashboard"
                        className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center hover:bg-white/20 transition-colors"
                    >
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                    </Link>
                    <div>
                        <h1 className="text-xl font-bold text-white">Disponibilidad</h1>
                        {!loading && !error && (
                            <p className="text-xs text-slate-400">
                                {freeCount} libres • {occupiedCount} ocupadas
                            </p>
                        )}
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 p-4">
                {loading && (
                    <div className="flex items-center justify-center py-20">
                        <div className="animate-spin h-8 w-8 border-4 border-amber-500 border-t-transparent rounded-full"></div>
                    </div>
                )}

                {error && (
                    <div className="p-4 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-center">
                        {error}
                    </div>
                )}

                {/* Legend */}
                {!loading && !error && (
                    <div className="flex gap-4 mb-6 justify-center flex-wrap">
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full bg-green-500"></div>
                            <span className="text-slate-400 text-xs">Libre</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full bg-red-500"></div>
                            <span className="text-slate-400 text-xs">Ocupada</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                            <span className="text-slate-400 text-xs">Limpieza</span>
                        </div>
                    </div>
                )}

                {/* Rooms by Floor */}
                {!loading && !error && sortedFloors.map((floor) => (
                    <div key={floor} className="mb-6">
                        <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                            <span className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-sm">
                                {floor}
                            </span>
                            Piso {floor}
                        </h2>
                        <div className="grid grid-cols-2 gap-3">
                            {roomsByFloor[floor].map((room) => {
                                const statusInfo = getStatusDisplay(room.status);
                                const priceColor = room.base_price ? getCategoryColor(room.base_price) : 'text-slate-400';

                                return (
                                    <div
                                        key={room.room_id}
                                        className={`${statusInfo.bgClass} border-2 ${statusInfo.borderClass} rounded-2xl p-4 transition-all duration-200`}
                                    >
                                        <div className="flex justify-between items-start mb-2">
                                            <span className="text-2xl font-bold text-white">
                                                {room.internal_code || room.room_id}
                                            </span>
                                            <span className={`text-xs font-medium px-2 py-1 rounded-full ${statusInfo.bgClass} ${statusInfo.textClass}`}>
                                                {statusInfo.label}
                                            </span>
                                        </div>

                                        <p className="text-slate-300 text-sm font-medium mb-1">
                                            {room.category_name}
                                        </p>

                                        {room.base_price && (
                                            <p className={`text-xs ${priceColor} mb-1`}>
                                                {formatPrice(room.base_price)}/noche
                                            </p>
                                        )}

                                        {room.max_capacity && (
                                            <p className="text-xs text-slate-500">
                                                👥 máx {room.max_capacity} pers.
                                            </p>
                                        )}

                                        {room.status.toLowerCase() === 'ocupada' && room.huesped && room.huesped !== '-' && (
                                            <p className="text-white text-sm font-medium truncate mt-2 pt-2 border-t border-white/10">
                                                👤 {room.huesped}
                                            </p>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}

                {!loading && !error && rooms.length === 0 && (
                    <div className="text-center py-20">
                        <p className="text-slate-400">No hay habitaciones disponibles</p>
                    </div>
                )}
            </main>

            <footer className="p-4 text-center">
                <p className="text-slate-500 text-xs">
                    Actualizado: {new Date().toLocaleTimeString('es-ES')}
                </p>
            </footer>
        </div>
    );
}
