import { QueryClient } from "@tanstack/react-query";

/** Cached data stays fresh for 5 minutes — no refetch when navigating back. */
export const ADMIN_STALE_TIME = 5 * 60 * 1000;

/** Keep unused admin data in memory for 30 minutes. */
export const ADMIN_GC_TIME = 30 * 60 * 1000;

export function createAdminQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: ADMIN_STALE_TIME,
        gcTime: ADMIN_GC_TIME,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
}
