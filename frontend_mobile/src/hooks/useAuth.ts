'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated, getAccessToken, logout, refreshTokens } from '@/services/auth';

interface UseAuthOptions {
    /** Redirect to login if not authenticated */
    required?: boolean;
    /** Path to redirect to for login */
    loginPath?: string;
}

interface AuthState {
    isLoading: boolean;
    isAuthenticated: boolean;
    accessToken: string | null;
}

/**
 * Hook to manage authentication state.
 * Use in protected pages to redirect unauthenticated users.
 */
export function useAuth(options: UseAuthOptions = {}): AuthState & { logout: () => void } {
    const { required = false, loginPath = '/login' } = options;
    const router = useRouter();

    const [state, setState] = useState<AuthState>({
        isLoading: true,
        isAuthenticated: false,
        accessToken: null,
    });

    useEffect(() => {
        const checkAuth = async () => {
            const authenticated = isAuthenticated();
            const token = getAccessToken();

            if (!authenticated && required) {
                // Try to refresh tokens first
                const refreshed = await refreshTokens();
                if (refreshed) {
                    setState({
                        isLoading: false,
                        isAuthenticated: true,
                        accessToken: refreshed.access_token,
                    });
                    return;
                }

                // No valid tokens, redirect to login
                router.replace(loginPath);
                return;
            }

            setState({
                isLoading: false,
                isAuthenticated: authenticated,
                accessToken: token,
            });
        };

        checkAuth();
    }, [required, loginPath, router]);

    const handleLogout = async () => {
        await logout();
        setState({
            isLoading: false,
            isAuthenticated: false,
            accessToken: null,
        });
        router.replace(loginPath);
    };

    return {
        ...state,
        logout: handleLogout,
    };
}
