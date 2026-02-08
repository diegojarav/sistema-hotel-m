'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Calendar from 'react-calendar';
import { format, isSameDay } from 'date-fns';
import { es } from 'date-fns/locale';

import 'react-calendar/dist/Calendar.css';
import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

const API_URL = `${API_BASE_URL}/api/v1`;

interface Reservation {
    id: string;
    room_id: string;
    guest_name: string;
    status: string;
    check_in: string;
    check_out: string;
}

function getStatusBadge(status: string) {
    const s = status.toLowerCase();
    if (s === 'confirmada' || s === 'confirmed') {
        return { bg: 'bg-green-500/20', text: 'text-green-400', label: 'Confirmada' };
    }
    if (s === 'pendiente' || s === 'pending') {
        return { bg: 'bg-amber-500/20', text: 'text-amber-400', label: 'Pendiente' };
    }
    if (s === 'cancelada' || s === 'cancelled') {
        return { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Cancelada' };
    }
    if (s === 'ocupada' || s === 'checked_in') {
        return { bg: 'bg-blue-500/20', text: 'text-blue-400', label: 'Hospedado' };
    }
    return { bg: 'bg-slate-500/20', text: 'text-slate-400', label: status };
}

export default function CalendarPage() {
    const router = useRouter();
    const [reservations, setReservations] = useState<Reservation[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedDate, setSelectedDate] = useState<Date | null>(null);
    const [showCount, setShowCount] = useState(5);
    const [datesWithReservations, setDatesWithReservations] = useState<Set<string>>(new Set());

    // Fetch reservations
    useEffect(() => {
        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
        if (!token) {
            router.replace('/login');
            return;
        }

        async function fetchReservations() {
            try {
                const response = await fetch(`${API_URL}/reservations`, {
                    headers: { 'Authorization': `Bearer ${token}` },
                });

                if (!response.ok) {
                    if (response.status === 401) {
                        router.replace('/login');
                        return;
                    }
                    throw new Error('Error al cargar reservas');
                }

                const data: Reservation[] = await response.json();
                setReservations(data);

                // Build set of dates with reservations
                const dates = new Set<string>();
                data.forEach(res => {
                    const checkIn = new Date(res.check_in);
                    const checkOut = new Date(res.check_out);
                    const current = new Date(checkIn);
                    while (current <= checkOut) {
                        dates.add(current.toISOString().split('T')[0]);
                        current.setDate(current.getDate() + 1);
                    }
                });
                setDatesWithReservations(dates);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Error desconocido');
            } finally {
                setIsLoading(false);
            }
        }

        fetchReservations();
    }, [router]);

    // Get filtered list based on selected date or upcoming
    const getDisplayedReservations = useCallback(() => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        let filtered: Reservation[];

        if (selectedDate) {
            // Filter by selected date
            filtered = reservations.filter(res => {
                const checkIn = new Date(res.check_in);
                const checkOut = new Date(res.check_out);
                checkIn.setHours(0, 0, 0, 0);
                checkOut.setHours(0, 0, 0, 0);
                const selectedTime = selectedDate.getTime();
                return selectedTime >= checkIn.getTime() && selectedTime <= checkOut.getTime();
            });
        } else {
            // Upcoming: check_in >= today && not cancelled
            filtered = reservations.filter(res => {
                const checkIn = new Date(res.check_in);
                checkIn.setHours(0, 0, 0, 0);
                return checkIn >= today && res.status.toLowerCase() !== 'cancelada';
            });
        }

        // Sort by check_in ASC
        filtered.sort((a, b) => new Date(a.check_in).getTime() - new Date(b.check_in).getTime());

        return filtered;
    }, [reservations, selectedDate]);

    const displayedReservations = getDisplayedReservations();
    const visibleReservations = displayedReservations.slice(0, showCount);
    const hasMore = displayedReservations.length > showCount;

    // Calendar tile content - add dot for days with reservations
    const tileContent = ({ date, view }: { date: Date; view: string }) => {
        if (view !== 'month') return null;
        const dateStr = date.toISOString().split('T')[0];
        if (datesWithReservations.has(dateStr)) {
            return (
                <div className="flex justify-center mt-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500"></div>
                </div>
            );
        }
        return null;
    };

    // Handle date click
    const handleDateClick = (value: Date) => {
        if (selectedDate && isSameDay(selectedDate, value)) {
            setSelectedDate(null); // Deselect
        } else {
            setSelectedDate(value);
        }
        setShowCount(5); // Reset pagination
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col">
            {/* Header */}
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
                    <h1 className="text-xl font-bold text-white">Calendario</h1>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 p-4 overflow-x-hidden">
                {/* Loading */}
                {isLoading && (
                    <div className="space-y-4">
                        <div className="h-64 bg-white/5 rounded-2xl animate-pulse"></div>
                        <div className="h-24 bg-white/5 rounded-2xl animate-pulse"></div>
                        <div className="h-24 bg-white/5 rounded-2xl animate-pulse"></div>
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div className="p-4 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-center">
                        {error}
                    </div>
                )}

                {!isLoading && !error && (
                    <>
                        {/* Calendar Section */}
                        <div className="mb-6 calendar-container">
                            <Calendar
                                onChange={(value) => handleDateClick(value as Date)}
                                value={selectedDate}
                                tileContent={tileContent}
                                locale="es-ES"
                                className="hotel-calendar"
                            />
                        </div>

                        {/* Selected Date Header */}
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-white">
                                {selectedDate
                                    ? format(selectedDate, "EEEE d 'de' MMMM", { locale: es })
                                    : 'Próximas Reservas'
                                }
                            </h2>
                            {selectedDate && (
                                <button
                                    onClick={() => setSelectedDate(null)}
                                    className="text-sm text-amber-400 hover:text-amber-300"
                                >
                                    Ver todas
                                </button>
                            )}
                        </div>

                        {/* Reservations List */}
                        {displayedReservations.length === 0 ? (
                            <div className="text-center py-16 bg-white/5 rounded-2xl border border-white/10">
                                <div className="text-4xl mb-4">🏨</div>
                                <p className="text-white font-medium mb-2">Hotel tranquilo...</p>
                                <p className="text-slate-400 text-sm">
                                    {selectedDate
                                        ? 'No hay reservas para este día'
                                        : 'No hay reservas próximas'
                                    }
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {visibleReservations.map((res) => {
                                    const badge = getStatusBadge(res.status);
                                    const checkIn = new Date(res.check_in);

                                    return (
                                        <div
                                            key={res.id}
                                            className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-2xl p-4 hover:bg-white/10 transition-all"
                                        >
                                            <div className="flex justify-between items-start mb-2">
                                                <div className="flex items-center gap-3">
                                                    <div className="text-center">
                                                        <div className="text-xs text-slate-400 uppercase">
                                                            {format(checkIn, 'EEE', { locale: es })}
                                                        </div>
                                                        <div className="text-2xl font-bold text-white">
                                                            {format(checkIn, 'd')}
                                                        </div>
                                                        <div className="text-xs text-slate-400">
                                                            {format(checkIn, 'MMM', { locale: es })}
                                                        </div>
                                                    </div>
                                                    <div className="border-l border-white/10 pl-3">
                                                        <p className="text-white font-medium">{res.guest_name}</p>
                                                        <p className="text-slate-400 text-sm">Hab. {res.room_id}</p>
                                                    </div>
                                                </div>
                                                <span className={`text-xs font-medium px-2 py-1 rounded-full ${badge.bg} ${badge.text}`}>
                                                    {badge.label}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}

                                {/* Ver más button */}
                                {hasMore && (
                                    <button
                                        onClick={() => setShowCount(14)}
                                        className="w-full py-3 text-amber-400 hover:text-amber-300 text-sm font-medium border border-white/10 rounded-xl hover:bg-white/5 transition-all"
                                    >
                                        Ver más ({displayedReservations.length - showCount} restantes)
                                    </button>
                                )}
                            </div>
                        )}
                    </>
                )}
            </main>

            {/* Custom Calendar Styles */}
            <style jsx global>{`
        .hotel-calendar {
          width: 100% !important;
          background: rgba(255, 255, 255, 0.05) !important;
          border: 1px solid rgba(255, 255, 255, 0.1) !important;
          border-radius: 1rem !important;
          padding: 0.5rem !important;
          font-family: inherit !important;
        }
        
        .hotel-calendar .react-calendar__navigation {
          margin-bottom: 0.5rem;
        }
        
        .hotel-calendar .react-calendar__navigation button {
          color: white !important;
          font-size: 1rem !important;
          background: transparent !important;
          border-radius: 0.5rem;
        }
        
        .hotel-calendar .react-calendar__navigation button:hover {
          background: rgba(255, 255, 255, 0.1) !important;
        }
        
        .hotel-calendar .react-calendar__navigation button:disabled {
          background: transparent !important;
        }
        
        .hotel-calendar .react-calendar__month-view__weekdays {
          text-transform: uppercase;
          font-size: 0.7rem;
          color: rgba(148, 163, 184, 0.8);
          font-weight: 600;
        }
        
        .hotel-calendar .react-calendar__month-view__weekdays abbr {
          text-decoration: none !important;
        }
        
        .hotel-calendar .react-calendar__tile {
          color: white !important;
          background: transparent !important;
          padding: 0.75rem 0.5rem !important;
          border-radius: 0.5rem;
          font-size: 0.875rem;
        }
        
        .hotel-calendar .react-calendar__tile:hover {
          background: rgba(255, 255, 255, 0.1) !important;
        }
        
        .hotel-calendar .react-calendar__tile--now {
          background: rgba(245, 158, 11, 0.2) !important;
          border: 1px solid rgba(245, 158, 11, 0.5);
        }
        
        .hotel-calendar .react-calendar__tile--active {
          background: rgba(245, 158, 11, 0.4) !important;
          border: 1px solid rgb(245, 158, 11);
        }
        
        .hotel-calendar .react-calendar__tile--active:hover {
          background: rgba(245, 158, 11, 0.5) !important;
        }
        
        .hotel-calendar .react-calendar__month-view__days__day--neighboringMonth {
          color: rgba(148, 163, 184, 0.4) !important;
        }
      `}</style>
        </div>
    );
}
