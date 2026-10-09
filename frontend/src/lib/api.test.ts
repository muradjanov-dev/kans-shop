import axios, { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { api, cancelAuthenticatedRequests } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const originalApiAdapter = api.defaults.adapter;
const originalAxiosAdapter = axios.defaults.adapter;

function jwt(sub: number, signature = "signature"): string {
  const payload = btoa(JSON.stringify({ sub: String(sub) }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `e30.${payload}.${signature}`;
}

function response<T>(config: Parameters<AxiosAdapter>[0], data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: new AxiosHeaders(), config };
}

function unauthorized(config: Parameters<AxiosAdapter>[0]): Promise<never> {
  const errorResponse = response(config, { error: { code: "UNAUTHORIZED", message: "expired", details: {} } }, 401);
  return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse));
}

afterEach(() => {
  api.defaults.adapter = originalApiAdapter;
  axios.defaults.adapter = originalAxiosAdapter;
});

describe("authenticated API refresh", () => {
  it("aborts protected API requests owned by a canceled auth epoch", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    let requestStarted!: () => void;
    let requestSignal: AbortSignal | undefined;
    const started = new Promise<void>((resolve) => { requestStarted = resolve; });
    const adapter: AxiosAdapter = (config) => new Promise((_, reject) => {
      requestSignal = config.signal as AbortSignal | undefined;
      requestStarted();
      requestSignal?.addEventListener("abort", () => {
        reject(new AxiosError("Canceled", "ERR_CANCELED", config));
      });
    });
    api.defaults.adapter = adapter;

    const request = api.get("/cart");
    await started;
    cancelAuthenticatedRequests(useAuthStore.getState().authEpoch);

    await expect(request).rejects.toMatchObject({ code: "ERR_CANCELED" });
    expect(requestSignal).toBeInstanceOf(AbortSignal);
    expect(requestSignal?.aborted).toBe(true);
    expect(useAuthStore.getState().accessToken).toBe(jwt(42));
  });

  it("shares one refresh across three simultaneous unauthorized requests", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42, "old"),
      refresh_token: "refresh-old",
      is_admin: false,
    });
    let refreshCalls = 0;
    const adapter: AxiosAdapter = async (config) => {
      if (config.url?.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        return response(config, {
          access_token: jwt(42, "new"),
          refresh_token: "refresh-new",
          token_type: "bearer",
          is_admin: false,
        });
      }
      if (String(config.headers.get("Authorization")).includes(jwt(42, "new"))) {
        return response(config, { ok: true });
      }
      return unauthorized(config);
    };
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter;

    await Promise.all([
      api.get("/resource/one"),
      api.get("/resource/two"),
      api.get("/resource/three"),
    ]);

    expect(refreshCalls).toBe(1);
    expect(useAuthStore.getState().refreshToken).toBe("refresh-new");
  });

  it("does not restore a session when logout happens during refresh", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-old",
      is_admin: false,
    });

    let beginRefresh!: () => void;
    let finishRefresh!: (pair: { access_token: string; refresh_token: string; token_type: string; is_admin: boolean }) => void;
    const refreshStarted = new Promise<void>((resolve) => {
      beginRefresh = resolve;
    });
    const refreshResponse = new Promise<{ access_token: string; refresh_token: string; token_type: string; is_admin: boolean }>((resolve) => {
      finishRefresh = resolve;
    });

    const adapter: AxiosAdapter = async (config) => {
      if (config.url?.endsWith("/auth/refresh")) {
        beginRefresh();
        return response(config, await refreshResponse);
      }
      return unauthorized(config);
    };
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter;

    const pendingRequest = api.get("/private-resource");
    await refreshStarted;
    useAuthStore.getState().clear();
    finishRefresh({
      access_token: jwt(42),
      refresh_token: "refresh-new",
      token_type: "bearer",
      is_admin: false,
    });

    await expect(pendingRequest).rejects.toBeDefined();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });

  it("does not clear the new account when an old account refresh finishes late", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    let beginRefresh!: () => void;
    let finishRefresh!: (pair: { access_token: string; refresh_token: string; token_type: string; is_admin: boolean }) => void;
    const refreshStarted = new Promise<void>((resolve) => { beginRefresh = resolve; });
    const refreshResponse = new Promise<{ access_token: string; refresh_token: string; token_type: string; is_admin: boolean }>((resolve) => {
      finishRefresh = resolve;
    });
    const adapter: AxiosAdapter = async (config) => {
      if (config.url?.endsWith("/auth/refresh")) {
        beginRefresh();
        return response(config, await refreshResponse);
      }
      return unauthorized(config);
    };
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter;

    const pendingRequest = api.get("/private-resource");
    await refreshStarted;
    useAuthStore.getState().setTokens({
      access_token: jwt(99),
      refresh_token: "refresh-99",
      is_admin: false,
    });
    finishRefresh({
      access_token: jwt(42, "refreshed"),
      refresh_token: "refresh-old-next",
      token_type: "bearer",
      is_admin: false,
    });

    await expect(pendingRequest).rejects.toBeDefined();
    expect(useAuthStore.getState().accessToken).toBe(jwt(99));
    expect(useAuthStore.getState().refreshToken).toBe("refresh-99");
  });

  it("rejects a successful response from the previous account epoch", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    let beginRequest!: () => void;
    let finishRequest!: () => void;
    const requestStarted = new Promise<void>((resolve) => { beginRequest = resolve; });
    const responseReady = new Promise<void>((resolve) => { finishRequest = resolve; });
    const adapter: AxiosAdapter = async (config) => {
      beginRequest();
      await responseReady;
      return response(config, { private: "old account" });
    };
    api.defaults.adapter = adapter;

    const pendingRequest = api.get("/private-resource");
    await requestStarted;
    useAuthStore.getState().setTokens({
      access_token: jwt(99),
      refresh_token: "refresh-99",
      is_admin: false,
    });
    finishRequest();

    await expect(pendingRequest).rejects.toMatchObject({ name: "StaleAuthResponseError" });
    expect(useAuthStore.getState().accessToken).toBe(jwt(99));
  });
});
