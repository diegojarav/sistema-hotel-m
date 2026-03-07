'use client';

import { PricingSeason } from '@/services/pricing';

interface SeasonSelectorProps {
    seasons: PricingSeason[];
    selectedSeason: PricingSeason | null;
    onSeasonChange: (season: PricingSeason | null) => void;
}

function formatModifier(modifier: number): string {
    const pct = (modifier - 1.0) * 100;
    if (pct === 0) return 'base';
    return pct > 0 ? `+${pct.toFixed(0)}%` : `${pct.toFixed(0)}%`;
}

export default function SeasonSelector({ seasons, selectedSeason, onSeasonChange }: SeasonSelectorProps) {
    return (
        <div className="mb-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1">
                📅 Temporada
                <span className="text-xs font-normal text-gray-400">(override manual)</span>
            </h3>
            <div className="flex flex-wrap gap-2">
                {/* Auto-detect option */}
                <button
                    type="button"
                    onClick={() => onSeasonChange(null)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
                        selectedSeason === null
                            ? 'bg-gray-900 text-white border-gray-900'
                            : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
                    }`}
                >
                    Automática
                </button>

                {/* Season options */}
                {seasons.map(season => {
                    const isSelected = selectedSeason?.id === season.id;
                    return (
                        <button
                            key={season.id}
                            type="button"
                            onClick={() => onSeasonChange(season)}
                            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
                                isSelected
                                    ? 'text-white border-transparent shadow-sm'
                                    : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
                            }`}
                            style={isSelected ? { backgroundColor: season.color } : undefined}
                        >
                            {season.name}
                            <span className="ml-1 opacity-75">({formatModifier(season.price_modifier)})</span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
