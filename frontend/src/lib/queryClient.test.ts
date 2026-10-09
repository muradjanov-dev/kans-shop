import { afterEach, describe, expect, it } from "vitest";
import { createAppQueryClient } from "@/lib/queryClient";

function rateLimitedError(status: number): Error {
  return Object.assign(new Error(`HTTP ${status}`), {
    isAxiosError: true,
    response: { status },
  });
}

describe("app query retries", () => {
  let queryClient = createAppQueryClient();

  afterEach(() => {
    queryClient.clear();
    queryClient = createAppQueryClient();
  });

  it("does not automatically retry an HTTP 429", async () => {
    const error = rateLimitedError(429);
    let attempts = 0;

    await expect(queryClient.fetchQuery({
      queryKey: ["rate-limited"],
      queryFn: () => {
        attempts += 1;
        throw error;
      },
      retryDelay: 0,
    })).rejects.toBe(error);

    expect(attempts).toBe(1);
  });

  it("preserves the single automatic retry for other errors", async () => {
    const error = rateLimitedError(500);
    let attempts = 0;

    await expect(queryClient.fetchQuery({
      queryKey: ["server-error"],
      queryFn: () => {
        attempts += 1;
        throw error;
      },
      retryDelay: 0,
    })).rejects.toBe(error);

    expect(attempts).toBe(2);
  });
});
