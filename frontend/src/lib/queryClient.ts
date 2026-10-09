import { QueryClient } from "@tanstack/react-query";
import { isRateLimitedError } from "@/lib/api";

function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && !isRateLimitedError(error);
}

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetryQuery,
        staleTime: 30_000,
      },
    },
  });
}
