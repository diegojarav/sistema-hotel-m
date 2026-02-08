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
    calculatePrice,
    ClientType,
    PriceCalculationResponse
} from '@/services/pricing';
import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/constants/keys';

import DocumentScanner from './components/DocumentScanner';
import GuestForm from './components/GuestForm';
import RoomSelection from './components/RoomSelection';
import PriceSummary from './components/PriceSummary';

const API_URL = `${API_BASE_URL}/api/v1`;

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

export default function NewReservationPage() {
    const router = useRouter();
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Auth state
    const [isLoading, setIsLoading] = useState(true);

    // Categories and rooms
    const [categories, setCategories] = useState<RoomCategory[]>([]);
    const [rooms, setRooms] = useState<RoomStatus[]>([]);
    const [selectedCategory, setSelectedCategory] = useState<RoomCategory | null>(null);

    // Pricing state
    const [clientTypes, setClientTypes] = useState<ClientType[]>([]);
    const [selectedClientType, setSelectedClientType] = useState<ClientType | null>(null);
    const [pricingResponse, setPricingResponse] = useState<PriceCalculationResponse | null>(null);
    const [priceBreakdown, setPriceBreakdown] = useState<string>('{}');

    // Scanning state
    const [isScanning, setIsScanning] = useState(false);
    const [scanError, setScanError] = useState('');

    // Get today and tomorrow for defaults
    const today = new Date().toISOString().split('T')[0];
    const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];

    // Form state
    const [formData, setFormData] = useState({
        apellidos: '',
        nombres: '',
        documento: '',
        nacionalidad: '',
        pais: '',
        fechaNacimiento: '',
        telefono: '',
        checkIn: today,
        checkOut: tomorrow,
        precio: 0,
        parkingNeeded: false,
        vehicleModel: '',
        vehiclePlate: '',
        source: 'Direct',
    });

    // Multi-room selection
    const [selectedRooms, setSelectedRooms] = useState<string[]>([]);

    // Submission state
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitProgress, setSubmitProgress] = useState({ current: 0, total: 0 });
    const [submitError, setSubmitError] = useState('');
    const [submitSuccess, setSubmitSuccess] = useState(false);
    const [createdIds, setCreatedIds] = useState<string[]>([]);

    const calculateNights = (): number => {
        const checkIn = new Date(formData.checkIn);
        const checkOut = new Date(formData.checkOut);
        const diffTime = checkOut.getTime() - checkIn.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return Math.max(1, diffDays);
    };

    const handleFormChange = (updates: Partial<typeof formData>) => {
        setFormData(prev => ({ ...prev, ...updates }));
    };

    // Auth check and data loading
    useEffect(() => {
        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
        if (!token) {
            router.replace('/login');
            return;
        }

        async function loadData() {
            try {
                const [categoriesData, roomsData, clientTypesData] = await Promise.all([
                    getRoomCategories(),
                    getRoomsStatus(),
                    getClientTypes(),
                ]);
                setCategories(categoriesData);
                setRooms(roomsData);
                setClientTypes(clientTypesData);

                if (clientTypesData.length > 0) {
                    const defaultCT = clientTypesData.find(ct => ct.name.toLowerCase().includes('particular')) || clientTypesData[0];
                    setSelectedClientType(defaultCT);
                }
                if (categoriesData.length > 0) {
                    setSelectedCategory(categoriesData[0]);
                }
            } catch (err) {
                console.error('Error loading data:', err);
            } finally {
                setIsLoading(false);
            }
        }

        loadData();
    }, [router]);

    // Update price when category or nights change
    useEffect(() => {
        async function fetchPrice() {
            if (selectedCategory && selectedClientType) {
                const nights = calculateNights();
                try {
                    const res = await calculatePrice(
                        selectedCategory.id,
                        formData.checkIn,
                        nights,
                        selectedClientType.id
                    );
                    setPricingResponse(res);
                    setPriceBreakdown(JSON.stringify(res.breakdown));

                    const roomCount = Math.max(1, selectedRooms.length);
                    setFormData(prev => ({ ...prev, precio: res.final_price * roomCount }));
                } catch (err) {
                    console.error("Pricing error:", err);
                }
            }
        }
        fetchPrice();
    }, [selectedCategory, selectedClientType, selectedRooms.length, formData.checkIn, formData.checkOut]);

    const availableRooms = rooms.filter(room => {
        if (selectedCategory && room.category_id !== selectedCategory.id) return false;
        return room.status.toLowerCase() === 'libre';
    });

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsScanning(true);
        setScanError('');

        try {
            const token = localStorage.getItem(ACCESS_TOKEN_KEY);
            const formDataUpload = new FormData();
            formDataUpload.append('file', file);

            const response = await fetch(`${API_URL}/vision/extract-data`, {
                method: 'POST',
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                body: formDataUpload,
            });

            const result = await response.json();

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

    const handleCategoryChange = (cat: RoomCategory) => {
        setSelectedCategory(cat);
        setSelectedRooms([]);
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

        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
        const guestName = `${formData.nombres} ${formData.apellidos}`.trim() || 'Sin nombre';
        const allCreatedIds: string[] = [];

        for (let i = 0; i < selectedRooms.length; i++) {
            setSubmitProgress({ current: i + 1, total: selectedRooms.length });

            const reservationData = {
                check_in_date: formData.checkIn,
                stay_days: nights,
                guest_name: guestName,
                room_ids: [selectedRooms[i]],
                room_type: selectedCategory?.name || 'Standard',
                price: formData.precio / selectedRooms.length,
                arrival_time: null,
                reserved_by: 'App Móvil',
                contact_phone: formData.telefono,
                received_by: 'mobile_user',
                category_id: selectedCategory?.id,
                client_type_id: selectedClientType?.id,
                price_breakdown: priceBreakdown,
                parking_needed: formData.parkingNeeded,
                vehicle_model: formData.vehicleModel || null,
                vehicle_plate: formData.vehiclePlate || null,
                source: formData.source
            };

            try {
                const response = await fetch(`${API_URL}/reservations`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
                    },
                    body: JSON.stringify(reservationData),
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || `Error en habitación ${selectedRooms[i]}`);
                }

                const ids = await response.json();
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

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
                <div className="animate-spin h-8 w-8 border-4 border-amber-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    const nights = calculateNights();

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col">
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
                    <h1 className="text-xl font-bold text-white">Nueva Reserva</h1>
                </div>
            </header>

            <main className="flex-1 p-4 overflow-y-auto pb-24">
                {submitSuccess && (
                    <div className="mb-6 p-4 rounded-xl bg-green-500/20 border border-green-500/30 text-green-300">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="text-xl">✅</span>
                            <span className="font-semibold">¡{createdIds.length} reserva(s) creada(s)!</span>
                        </div>
                        <p className="text-sm text-green-400/80">Redirigiendo al calendario...</p>
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

                    <RoomSelection
                        formData={formData}
                        onFormChange={handleFormChange}
                        categories={categories}
                        selectedCategory={selectedCategory}
                        onCategoryChange={handleCategoryChange}
                        availableRooms={availableRooms}
                        selectedRooms={selectedRooms}
                        onToggleRoom={toggleRoom}
                        nights={nights}
                    />

                    <PriceSummary
                        formData={formData}
                        onFormChange={handleFormChange}
                        pricingResponse={pricingResponse}
                        selectedCategory={selectedCategory}
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
