import { useSession, signOut } from "next-auth/react";
import { useCallback } from "react";

interface AuthenticatedFetchOptions extends RequestInit {
  skipAuth?: boolean; // Allow some requests to skip auth
}

export function useAuthenticatedFetch() {
  const { data: session, status } = useSession();

  const authenticatedFetch = useCallback(
    async (url: string, options: AuthenticatedFetchOptions = {}) => {
      const { skipAuth = false, ...fetchOptions } = options;

      // Check if user is authenticated (unless skipping auth)
      if (!skipAuth && (status !== "authenticated" || !session?.idToken)) {
        throw new Error("Not authenticated");
      }

      // Add authorization header if we have a token
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(fetchOptions.headers as Record<string, string>),
      };

      if (!skipAuth && session?.idToken) {
        headers['Authorization'] = `Bearer ${session.idToken}`;
      }

      try {
        const response = await fetch(url, {
          ...fetchOptions,
          headers,
        });

        // Handle 401/403 errors globally
        if (response.status === 401 || response.status === 403) {
          console.error("Authentication failed. Token might be expired. Signing out...");
          signOut({ callbackUrl: '/auth/signin' });
          throw new Error("Authentication failed - redirecting to login");
        }

        return response;
      } catch (error) {
        // Re-throw the error to be handled by the calling component
        throw error;
      }
    },
    [session, status]
  );

  return { 
    authenticatedFetch, 
    isAuthenticated: status === "authenticated" && !!session?.idToken,
    isLoading: status === "loading"
  };
} 