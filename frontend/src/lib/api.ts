import axios, {
  type AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { useAuthStore, userIdFromAccessToken } from "@/store/auth";
import type { ApiErrorBody, TokenPair } from "@/types/api";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const api = axios.create({ baseURL: API_BASE_URL });

type AuthenticatedRequestConfig = InternalAxiosRequestConfig & {
  _authEpoch?: number;
  _retried?: boolean;
};

api.interceptors.request.use((config) => {
  const auth = useAuthStore.getState();
  const token = auth.accessToken;
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
    (config as AuthenticatedRequestConfig)._authEpoch = auth.authEpoch;
  }
  return config;
});

let refreshPromise: { key: string; promise: Promise<string | null> } | null = null;

async function refreshAccessToken(
  expectedEpoch: number,
  expectedRefreshToken: string,
  expectedUserId: string | null,
): Promise<string | null> {
  const before = useAuthStore.getState();
  if (
    before.authEpoch !== expectedEpoch ||
    before.refreshToken !== expectedRefreshToken
  ) {
    return null;
  }
  try {
    const { data } = await axios.post<TokenPair>(`${API_BASE_URL}/auth/refresh`, {
      refresh_token: expectedRefreshToken,
    });
    const current = useAuthStore.getState();
    if (
      current.authEpoch !== expectedEpoch ||
      current.refreshToken !== expectedRefreshToken
    ) {
      return null;
    }
    const subject = userIdFromAccessToken(data.access_token);
    if (subject !== expectedUserId) return null;
    current.setTokens(data);
    return data.access_token;
  } catch {
    const current = useAuthStore.getState();
    if (
      current.authEpoch === expectedEpoch &&
      current.refreshToken === expectedRefreshToken
    ) {
      current.clear();
    }
    return null;
  }
}

function sharedRefresh(
  epoch: number,
  token: string,
  userId: string | null,
): Promise<string | null> {
  const key = `${epoch}:${token}`;
  if (refreshPromise?.key === key) return refreshPromise.promise;
  const promise = refreshAccessToken(epoch, token, userId).finally(() => {
    if (refreshPromise?.promise === promise) refreshPromise = null;
  });
  refreshPromise = { key, promise };
  return promise;
}

api.interceptors.response.use(
  (response: AxiosResponse) => {
    const request = response.config as AuthenticatedRequestConfig;
    const currentEpoch = useAuthStore.getState().authEpoch;
    if (request._authEpoch !== undefined && request._authEpoch !== currentEpoch) {
      const stale = new Error("The authenticated session changed before this response completed");
      stale.name = "StaleAuthResponseError";
      return Promise.reject(stale);
    }
    return response;
  },
  async (error: AxiosError<ApiErrorBody>) => {
    const original = error.config as AuthenticatedRequestConfig | undefined;
    const current = useAuthStore.getState();
    const requestEpoch = original?._authEpoch;
    const sameSession = requestEpoch !== undefined && requestEpoch === current.authEpoch;

    if (error.response?.status === 401 && original && sameSession && !original._retried && current.refreshToken) {
      original._retried = true;
      const newToken = await sharedRefresh(current.authEpoch, current.refreshToken, current.userId);
      if (newToken) {
        original.headers.set("Authorization", `Bearer ${newToken}`);
        return api(original);
      }
    }

    const latest = useAuthStore.getState();
    if (
      error.response?.status === 401 &&
      original &&
      requestEpoch !== undefined &&
      requestEpoch === latest.authEpoch
    ) {
      useAuthStore.getState().clear();
    }

    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiErrorBody | undefined;
    if (body?.error?.message) return body.error.message;
  }
  return fallback;
}

export function getApiErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null;
  const body = error.response?.data as ApiErrorBody | undefined;
  return body?.error?.code ?? null;
}
