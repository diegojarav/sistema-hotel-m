'use client';

import { useEffect } from 'react';
import { logoutBeacon, isAuthenticated } from '@/services/auth';

/**
 * BeaconLogout Component
 * =====================
 * 
 * Invisible component that registers a beforeunload handler
 * to send a beacon logout when the user closes the tab/browser.
 * 
 * Place this component once in your root layout or in protected pages.
 */
export function BeaconLogout() {
    useEffect(() => {
        const handleBeforeUnload = () => {
            // Only send beacon if user is authenticated
            if (isAuthenticated()) {
                logoutBeacon();
            }
        };

        // Register the event listener
        window.addEventListener('beforeunload', handleBeforeUnload);

        // Cleanup on unmount
        return () => {
            window.removeEventListener('beforeunload', handleBeforeUnload);
        };
    }, []);

    // This component renders nothing
    return null;
}
