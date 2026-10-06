import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./http";

/**
 * Query defaults (docs/09 §8–9): lists are fresh for 30 s; 429/503/network errors are retried with
 * jittered exponential backoff (no synchronised retry storms on result day); 4xx are not retried.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && ![0, 429, 502, 503, 504].includes(error.status)) return false;
          return failureCount < 4;
        },
        retryDelay: (attempt, error) => {
          const hinted = error instanceof ApiError && error.retryAfter ? error.retryAfter * 1000 : 0;
          const backoff = Math.min(15_000, 1000 * 2 ** attempt);
          return Math.max(hinted, backoff) * (0.6 + Math.random() * 0.8);
        },
      },
      mutations: { retry: false },
    },
  });
}

export function isApiError(error: unknown, status?: number): error is ApiError {
  return error instanceof ApiError && (status === undefined || error.status === status);
}
