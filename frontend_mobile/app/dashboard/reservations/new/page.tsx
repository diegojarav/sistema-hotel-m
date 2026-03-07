'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
    RoomCategory,
    RoomStatus,
    getRoomCategories,
    getRoomsStatus,
} from '@/services/rooms';
import {
    getClientTypes,
    getSeasons,
    calculatePrice,
    ClientType,
    PricingSeason,
    PriceCalculationResponse
} from '@/services/pricing';
import { createReservation } from '@/services/reservations';
import { scanDocument } from '@/services/vision';
import { useAuth } from '@/hooks/useAuth';
import { getPropertySettings, PropertySettings } from '@/services/settings';

import DocumentScanner from './components/DocumentScanner';
import GuestForm from './components/GuestForm';
import RoomSelection from './components/RoomSelection';
import SeasonSelector from './components/SeasonSelector';
import PriceSummary from './components/PriceSummary';

interface ExtractedData {
    Apellidos: string | null;
    Nombres: string | null;
    Nacionalidad: string | null;
    Fecha_Nacimiento: string | null;
    Nro_Documento: string | null;
    Pais: string | null;
    Sexo: string | null;
    Estado_Civil: string | null;
    Procedencia: string | null;
}

export interface CategoryPricingResult {
    catId: string;
    catName: string;
    response: PriceCalculationResponse;
    roomCount: number;
}

export default function NewReservationPage() {
    const router = useRouter();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { isLoading: authLoading, accessToken } = useAuth({ required: true });

    // Categories and rooms
    const [isLoading, setIsLoading] = useState(true);
    const [categories, setCategories] = useState<RoomCategory[]>([]);
    const [rooms, setRooms] = useState<RoomStatus[]>([]);

    // Pricing state
    const [clientTypes, setClientTypes] = useState<ClientType[]>([]);
    const [selectedClientType, setSelectedClientType] = useState<ClientType | null>(null);
    const [seasons, setSeasons] = useState<PricingSeason[]>([]);
    const [selectedSeason, setSelectedSeason] = useState<PricingSeason | null>(null);
    const [pricingResults, setPricingResults] = useState<CategoryPricingResult[]>([]);
    const [priceBreakdown, setPriceBreakdown] = useState<string>('{}');

    // Scanning state
    const [isScanning, setIsScanning] = useState(false);
    const [scanError, setScanError] = useState('');

    // Form state — dates initialized empty to avoid SSR hydration mismatch,
    // then set to today/tomorrow on client mount via useEffect below.
    const [formData, setFormData] = useState({
        apellidos: '',
        nombres: '',
        documento: '',
        nacionalidad: '',
        pais: '',
        fechaNacimiento: '',
        telefono: '',
        arrivalTime: '',
        checkIn: '',
        checkOut: '',
        precio: 0,
        parkingNeeded: false,
        vehicleModel: '',
        vehiclePlate: '',
        source: 'Direct',
    });

    // Set default dates on client only (avoids SSR hydration mismatch)
    const datesInitialized = useRef(false);
    useEffect(() => {
        if (!datesInitialized.current) {
            const today = new Date().toISOString().split('T')[0];
            const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];
            setFormData(prev => ({ ...prev, checkIn: today, checkOut: tomorrow }));
            datesInitialized.current = true;
        }
    }, []);

    // Multi-room selection (across categories)
    const [selectedRooms, setSelectedRooms] = useState<string[]>([]);

    // Submission state
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitProgress, setSubmitProgress] = useState({ current: 0, total: 0 });
    const [submitError, setSubmitError] = useState('');
    const [submitSuccess, setSubmitSuccess] = useState(false);
    const [createdIds, setCreatedIds] = useState<string[]>([]);
    const [propertySettings, setPropertySettings] = useState<PropertySettings | null>(null);

    const calculateNights = (): number => {
        if (!formData.checkIn || !formData.checkOut) return 1;
        const [y1, m1, d1] = formData.checkIn.split('-').map(Number);
        const [y2, m2, d2] = formData.checkOut.split('-').map(Number);
        const checkIn = new Date(y1, m1 - 1, d1);
        const checkOut = new Date(y2, m2 - 1, d2);
        const diffTime = checkOut.getTime() - checkIn.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays > 0 ? diffDays : 1;
    };

    const handleFormChange = (updates: Partial<typeof formData>) => {
        setFormData(prev => ({ ...prev, ...updates }));
    };

    // Load categories + client types once on mount
    useEffect(() => {
        if (authLoading) return;

        async function loadStaticData() {
            try {
                const [categoriesData, clientTypesData, seasonsData, settingsData] = await Promise.all([
                    getRoomCategories(),
                    getClientTypes(),
                    getSeasons(),
                    getPropertySettings(),
                ]);
                setCategories(categoriesData);
                setClientTypes(clientTypesData);
                setSeasons(seasonsData);
                setPropertySettings(settingsData);

                if (clientTypesData.length > 0) {
                    const defaultCT = clientTypesData.find(ct => ct.name.toLowerCase().includes('particular')) || clientTypesData[0];
                    setSelectedClientType(defaultCT);
                }
            } catch (err) {
                console.error('Error loading static data:', err);
            } finally {
                setIsLoading(false);
            }
        }

        loadStaticData();
    }, [authLoading]);

    // Re-fetch room availability when dates change (prevents overbooking)
    useEffect(() => {
        if (authLoading || !formData.checkIn || !formData.checkOut) return;

        async function loadRooms() {
            try {
                const roomsData = await getRoomsStatus(undefined, formData.checkIn, formData.checkOut);
                setRooms(roomsData);
                setSelectedRooms([]); // Clear selection — availability changed
            } catch (err) {
                console.error('Error loading room availability:', err);
            }
        }

        loadRooms();
    }, [authLoading, formData.checkIn, formData.checkOut]);

    // ALL free rooms (no category filter)
    const availableRooms = rooms.filter(room => room.status.toLowerCase() === 'libre');

    // Update price per category when rooms, dates, or client type change
    useEffect(() => {
        async function fetchPrices() {
            if (!selectedClientType || selectedRooms.length === 0) {
                setPricingResults([]);
                setFormData(prev => ({ ...prev, precio: 0 }));
                return;
            }

            const nights = calculateNights();

            // Group selected rooms by category
            const roomsByCategory = new Map<string, string[]>();
            for (const roomId of selectedRooms) {
                const room = rooms.find(r => r.room_id === roomId);
                const catId = room?.category_id || '';
                if (!roomsByCategory.has(catId)) roomsByCategory.set(catId, []);
                roomsByCategory.get(catId)!.push(roomId);
            }

            try {
                // Calculate price for each unique category in parallel
                const promises = Array.from(roomsByCategory.entries()).map(
                    ([catId, catRoomIds]) =>
                        calculatePrice(catId, formData.checkIn, nights, selectedClientType.id, undefined, selectedSeason?.id)
                            .then(res => {
                                const cat = categories.find(c => c.id === catId);
                                return {
                                    catId,
                                    catName: cat?.name || catId,
                                    response: res,
                                    roomCount: catRoomIds.length,
                                } as CategoryPricingResult;
                            })
                );

                const results = await Promise.all(promises);
                setPricingResults(results);

                const total = results.reduce(
                    (sum, r) => sum + r.response.final_price * r.roomCount, 0
                );
                setPriceBreakdown(JSON.stringify(
                    Object.fromEntries(results.map(r => [r.catId, r.response.breakdown]))
                ));
                setFormData(prev => ({ ...prev, precio: total }));
            } catch (err) {
                console.error("Pricing error:", err);
            }
        }

        fetchPrices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedClientType, selectedSeason, selectedRooms, formData.checkIn, formData.checkOut]);

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsScanning(true);
        setScanError('');

        try {
            const result = await scanDocument(file);

            if (result.success && result.data) {
                const data: ExtractedData = result.data;
                setFormData(prev => ({
                    ...prev,
                    apellidos: data.Apellidos || prev.apellidos,
                    nombres: data.Nombres || prev.nombres,
                    documento: data.Nro_Documento || prev.documento,
                    nacionalidad: data.Nacionalidad || prev.nacionalidad,
                    pais: data.Pais || prev.pais,
                    fechaNacimiento: data.Fecha_Nacimiento || prev.fechaNacimiento,
                }));
            } else {
                setScanError(result.error || 'No se pudo extraer datos del documento');
            }
        } catch (err) {
            setScanError(err instanceof Error ? err.message : 'Error al escanear documento');
        } finally {
            setIsScanning(false);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    };

    const toggleRoom = (roomId: string) => {
        setSelectedRooms(prev =>
            prev.includes(roomId)
                ? prev.filter(r => r !== roomId)
                : [...prev, roomId]
        );
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (selectedRooms.length === 0) {
            setSubmitError('Por favor, seleccione al menos una habitación');
            return;
        }

        const nights = calculateNights();
        if (nights < 1) {
            setSubmitError('La fecha de salida debe ser posterior a la de entrada');
            return;
        }

        setIsSubmitting(true);
        setSubmitError('');
        setSubmitProgress({ current: 0, total: selectedRooms.length });
        setCreatedIds([]);

        const guestName = `${formData.nombres} ${formData.apellidos}`.trim() || 'Sin nombre';
        const allCreatedIds: string[] = [];

        for (let i = 0; i < selectedRooms.length; i++) {
            setSubmitProgress({ current: i + 1, total: selectedRooms.length });

            // Resolve this room's category
            const room = rooms.find(r => r.room_id === selectedRooms[i]);
            const roomCatId = room?.category_id || '';
            const roomCat = categories.find(c => c.id === roomCatId);

            const reservationData = {
                check_in_date: formData.checkIn,
                stay_days: nights,
                guest_name: guestName,
                room_ids: [selectedRooms[i]],
                room_type: roomCat?.name || 'Standard',
                price: formData.precio / selectedRooms.length,
                arrival_time: formData.arrivalTime || null,
                reserved_by: 'App Móvil',
                contact_phone: formData.telefono,
                received_by: 'mobile_user',
                category_id: roomCatId,
                client_type_id: selectedClientType?.id,
                price_breakdown: priceBreakdown,
                parking_needed: formData.parkingNeeded,
                vehicle_model: formData.vehicleModel || null,
                vehicle_plate: formData.vehiclePlate || null,
                source: formData.source,
                // FEAT-LINK-01: Identity fields from document scan (auto-creates CheckIn)
                document_number: formData.documento || '',
                guest_last_name: formData.apellidos || '',
                guest_first_name: formData.nombres || '',
                nationality: formData.nacionalidad || '',
                birth_date: formData.fechaNacimiento || null,
                country: formData.pais || ''
            };

            try {
                const ids = await createReservation(reservationData);
                allCreatedIds.push(...ids);
            } catch (err) {
                setSubmitError(err instanceof Error ? err.message : 'Error desconocido');
                setIsSubmitting(false);
                return;
            }
        }

        setCreatedIds(allCreatedIds);
        setSubmitSuccess(true);
        setIsSubmitting(false);

        setTimeout(() => {
            router.push('/dashboard/calendar');
        }, 2500);
    };

    if (authLoading || isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="animate-spin h-8 w-8 border-4 border-amber-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    const nights = calculateNights();

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col">
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
                    <h1 className="text-xl font-bold text-gray-900">Nueva Reserva</h1>
                </div>
            </header>

            <main className="flex-1 p-4 overflow-y-auto pb-24">
                {submitSuccess && (
                    <div className="mb-6 p-4 rounded-xl bg-green-50 border border-green-200 text-green-700 space-y-2">
                        <div className="flex items-center gap-2">
                            <span className="text-xl">✅</span>
                            <span className="font-semibold">¡{createdIds.length} reserva(s) creada(s)!</span>
                        </div>
                        {propertySettings && (
                            <div className="text-sm text-green-600 space-y-1 pt-2 border-t border-green-200">
                                <p>🕐 Check-in: {propertySettings.check_in_start} - {propertySettings.check_in_end} hs</p>
                                <p>🕐 Check-out: {propertySettings.check_out_time} hs</p>
                                <p>🍳 {propertySettings.breakfast_included ? 'Desayuno incluido' : 'Desayuno no incluido'}</p>
                            </div>
                        )}
                        <p className="text-sm text-green-600">Redirigiendo al calendario...</p>
                    </div>
                )}

                <DocumentScanner
                    fileInputRef={fileInputRef}
                    isScanning={isScanning}
                    scanError={scanError}
                    onFileChange={handleFileChange}
                />

                <form onSubmit={handleSubmit} className="space-y-4">
                    <GuestForm
                        formData={formData}
                        onFormChange={handleFormChange}
                        clientTypes={clientTypes}
                        selectedClientType={selectedClientType}
                        onClientTypeChange={setSelectedClientType}
                    />

                    <SeasonSelector
                        seasons={seasons}
                        selectedSeason={selectedSeason}
                        onSeasonChange={setSelectedSeason}
                    />

                    <RoomSelection
                        formData={formData}
                        onFormChange={handleFormChange}
                        categories={categories}
                        availableRooms={availableRooms}
                        selectedRooms={selectedRooms}
                        onToggleRoom={toggleRoom}
                        nights={nights}
                    />

                    <PriceSummary
                        formData={formData}
                        onFormChange={handleFormChange}
                        pricingResults={pricingResults}
                        selectedRooms={selectedRooms}
                        nights={nights}
                        isSubmitting={isSubmitting}
                        submitSuccess={submitSuccess}
                        submitProgress={submitProgress}
                        submitError={submitError}
                    />
                </form>
            </main>
        </div>
    );
}
