'use client';

import { RefObject } from 'react';

interface DocumentScannerProps {
    fileInputRef: RefObject<HTMLInputElement | null>;
    isScanning: boolean;
    scanError: string;
    onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export default function DocumentScanner({ fileInputRef, isScanning, scanError, onFileChange }: DocumentScannerProps) {
    return (
        <div className="mb-6 bg-gradient-to-r from-purple-500/20 to-blue-500/20 border border-purple-500/30 rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
                <span className="text-2xl">✨</span>
                <h2 className="text-lg font-semibold text-white">Escanear Documento</h2>
            </div>
            <p className="text-slate-400 text-sm mb-4">
                Usa Gemini 2.5 para extraer datos automáticamente
            </p>

            <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                onChange={onFileChange}
                className="hidden"
                id="document-scanner"
            />

            <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isScanning}
                className="w-full py-4 px-6 bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600 text-white font-semibold rounded-xl shadow-lg transition-all duration-200 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {isScanning ? (
                    <>
                        <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Analizando con Gemini 2.5...
                    </>
                ) : (
                    <>
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        📸 Tomar Foto / Subir Documento
                    </>
                )}
            </button>

            {scanError && (
                <div className="mt-3 p-3 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-sm">
                    {scanError}
                </div>
            )}
        </div>
    );
}
