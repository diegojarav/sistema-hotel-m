'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import Calendar from 'react-calendar';
import { format, isSameDay } from 'date-fns';
import { es } from 'date-fns/locale';

import 'react-calendar/dist/Calendar.css';
import { useAuth } from '@/hooks/useAuth';
import {
    getAllReservations,
    getDatesWithReservations,
    getStatusBadge,
    Reservation,
} from '@/services/reservations';

export default function CalendarPage() {
    const { isLoading: authLoading } = useAuth({ required: true });
    const [reservations, setReservations] = useState<Reservation[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedDate, setSelectedDate] = useState<Date | null>(null);
    const [showCount, setShowCount] = useState(5);
    const [datesWithReservations, setDatesWithReservations] = useState<Set<string>>(new Set());

    // Fetch reservations
    useEffect(() => {
        if (authLoading) return;

        async function fetchReservations() {
            try {
                const data = await getAllReservations();
                setReservations(data);
                setDatesWithReservations(getDatesWithReservations(data));
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Error desconocido');
            } finally {
                setIsLoading(false);
            }
        }

        fetchReservations();
    }, [authLoading]);

    // Get filtered list based on selected date or upcoming
    const getDisplayedReservations = useCallback(() => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        let filtered: Reservation[];

        if (selectedDate) {
            filtered = reservations.filter(res => {
                const checkIn = new Date(res.check_in);
                const checkOut = new Date(res.check_out);
                checkIn.setHours(0, 0, 0, 0);
                checkOut.setHours(0, 0, 0, 0);
                const selectedTime = selectedDate.getTime();
                return selectedTime >= checkIn.getTime() && selectedTime <= checkOut.getTime();
            });
        } else {
            filtered = reservations.filter(res => {
                const checkIn = new Date(res.check_in);
                checkIn.setHours(0, 0, 0, 0);
                return checkIn >= today && res.status.toLowerCase() !== 'cancelada';
            });
        }

        filtered.sort((a, b) => new Date(a.check_in).getTime() - new Date(b.check_in).getTime());

        return filtered;
    }, [reservations, selectedDate]);

    const displayedReservations = getDisplayedReservations();
    const visibleReservations = displayedReservations.slice(0, showCount);
    const hasMore = displayedReservations.length > showCount;

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

    const handleDateClick = (value: Date) => {
        if (selectedDate && isSameDay(selectedDate, value)) {
            setSelectedDate(null);
        } else {
            setSelectedDate(value);
        }
        setShowCount(5);
    };

    const loading = authLoading || isLoading;

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 px-4 py-4 sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <Link
                        href="/dashboard"
                        className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center hover:bg-gray-200 transition-colors"
                    >
                        <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                    </Link>
                    <h1 className="text-xl font-bold text-gray-900">Calendario</h1>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 p-4 overflow-x-hidden">
                {loading && (
                    <div className="space-y-4">
                        <div className="h-64 bg-gray-200 rounded-2xl animate-pulse"></div>
                        <div className="h-24 bg-gray-200 rounded-2xl animate-pulse"></div>
                        <div className="h-24 bg-gray-200 rounded-2xl animate-pulse"></div>
                    </div>
                )}

                {error && (
                    <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-600 text-center">
                        {error}
                    </div>
                )}

                {!loading && !error && (
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
                            <h2 className="text-lg font-semibold text-gray-900">
                                {selectedDate
                                    ? format(selectedDate, "EEEE d 'de' MMMM", { locale: es })
                                    : 'Próximas Reservas'
                                }
                            </h2>
                            {selectedDate && (
                                <button
                                    onClick={() => setSelectedDate(null)}
                                    className="text-sm text-amber-600 hover:text-amber-500"
                                >
                                    Ver todas
                                </button>
                            )}
                        </div>

                        {/* Reservations List */}
                        {displayedReservations.length === 0 ? (
                            <div className="text-center py-16 bg-white rounded-2xl border border-gray-200">
                                <div className="text-4xl mb-4">🏨</div>
                                <p className="text-gray-900 font-medium mb-2">Hotel tranquilo...</p>
                                <p className="text-gray-500 text-sm">
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
                                            className="bg-white border border-gray-200 rounded-2xl p-4 hover:bg-gray-50 transition-all shadow-sm"
                                        >
                                            <div className="flex justify-between items-start mb-2">
                                                <div className="flex items-center gap-3">
                                                    <div className="text-center">
                                                        <div className="text-xs text-gray-500 uppercase">
                                                            {format(checkIn, 'EEE', { locale: es })}
                                                        </div>
                                                        <div className="text-2xl font-bold text-gray-900">
                                                            {format(checkIn, 'd')}
                                                        </div>
                                                        <div className="text-xs text-gray-400">
                                                            {format(checkIn, 'MMM', { locale: es })}
                                                        </div>
                                                    </div>
                                                    <div className="border-l border-gray-200 pl-3">
                                                        <p className="text-gray-900 font-medium">{res.guest_name}</p>
                                                        <p className="text-gray-500 text-sm">Hab. {res.room_internal_code || res.room_id}</p>
                                                    </div>
                                                </div>
                                                <span className={`text-xs font-medium px-2 py-1 rounded-full ${badge.bgClass} ${badge.textClass}`}>
                                                    {badge.label}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}

                                {hasMore && (
                                    <button
                                        onClick={() => setShowCount(14)}
                                        className="w-full py-3 text-amber-600 hover:text-amber-500 text-sm font-medium border border-gray-200 rounded-xl hover:bg-gray-50 transition-all"
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
          background: white !important;
          border: 1px solid #e5e7eb !important;
          border-radius: 1rem !important;
          padding: 0.5rem !important;
          font-family: inherit !important;
        }

        .hotel-calendar .react-calendar__navigation {
          margin-bottom: 0.5rem;
        }

        .hotel-calendar .react-calendar__navigation button {
          color: #111827 !important;
          font-size: 1rem !important;
          background: transparent !important;
          border-radius: 0.5rem;
        }

        .hotel-calendar .react-calendar__navigation button:hover {
          background: #f3f4f6 !important;
        }

        .hotel-calendar .react-calendar__navigation button:disabled {
          background: transparent !important;
        }

        .hotel-calendar .react-calendar__month-view__weekdays {
          text-transform: uppercase;
          font-size: 0.7rem;
          color: #6b7280;
          font-weight: 600;
        }

        .hotel-calendar .react-calendar__month-view__weekdays abbr {
          text-decoration: none !important;
        }

        .hotel-calendar .react-calendar__tile {
          color: #111827 !important;
          background: transparent !important;
          padding: 0.75rem 0.5rem !important;
          border-radius: 0.5rem;
          font-size: 0.875rem;
        }

        .hotel-calendar .react-calendar__tile:hover {
          background: #f3f4f6 !important;
        }

        .hotel-calendar .react-calendar__tile--now {
          background: rgba(245, 158, 11, 0.15) !important;
          border: 1px solid rgba(245, 158, 11, 0.5);
        }

        .hotel-calendar .react-calendar__tile--active {
          background: rgba(245, 158, 11, 0.3) !important;
          border: 1px solid rgb(245, 158, 11);
        }

        .hotel-calendar .react-calendar__tile--active:hover {
          background: rgba(245, 158, 11, 0.4) !important;
        }

        .hotel-calendar .react-calendar__month-view__days__day--neighboringMonth {
          color: #d1d5db !important;
        }
      `}</style>
        </div>
    );
}
