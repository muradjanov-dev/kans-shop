import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";

export type AdminRole = "superadmin" | "manager" | "operator";

export interface AdminSession {
  admin_id: number;
  full_name: string;
  role: AdminRole;
  csrf_token: string;
}

type AdminActionResult = { ok: boolean };
type UnauthorizedListener = () => void;
type AdminRequestConfig = InternalAxiosRequestConfig & { _adminSessionGeneration?: number };

export class StaleAdminResponseError extends Error {
  constructor() {
    super("The admin session changed before this response completed");
    this.name = "StaleAdminResponseError";
  }
}

const codeExchangePath = "/auth/admin/code/exchange";
const unsafeMethods = new Set(["post", "put", "patch", "delete"]);
const unauthorizedListeners = new Set<UnauthorizedListener>();
let csrfToken: string | null = null;
let sessionGeneration = 0;

const client: AxiosInstance = axios.create({ baseURL: "/api/v1", withCredentials: true });

client.interceptors.request.use((config) => {
  (config as AdminRequestConfig)._adminSessionGeneration = sessionGeneration;
  const method = config.method?.toLowerCase() ?? "get";
  if (unsafeMethods.has(method) && config.url !== codeExchangePath && csrfToken) {
    config.headers.set("X-CSRF-Token", csrfToken);
  }
  return config;
}, undefined, { synchronous: true });

client.interceptors.response.use(
  (response) => {
    if (isStaleAdminRequest(response.config)) {
      return Promise.reject(new StaleAdminResponseError());
    }
    return response;
  },
  (error: AxiosError) => {
    if (error.config && isStaleAdminRequest(error.config)) {
      return Promise.reject(new StaleAdminResponseError());
    }
    const isCodeExchange = error.config?.url === codeExchangePath;
    if (error.response?.status === 401 && !isCodeExchange) {
      for (const listener of unauthorizedListeners) listener();
    }
    return Promise.reject(error);
  },
);

function data<T>(request: Promise<AxiosResponse<T>>): Promise<T> {
  return request.then((response) => response.data);
}

export const adminApi = Object.assign(client, {
  exchangeCode(code: string): Promise<AdminSession> {
    return data(client.post<AdminSession>(codeExchangePath, { code }));
  },
  loadSession(): Promise<AdminSession> {
    return data(client.get<AdminSession>("/auth/admin/session"));
  },
  refreshSession(): Promise<AdminSession> {
    return data(client.post<AdminSession>("/auth/admin/session/refresh"));
  },
  logout(): Promise<AdminActionResult> {
    return data(client.post<AdminActionResult>("/auth/admin/logout"));
  },
  logoutAll(): Promise<AdminActionResult> {
    return data(client.post<AdminActionResult>("/auth/admin/logout-all"));
  },
});

export function setAdminCsrfToken(token: string | null): void {
  if (token === csrfToken) return;
  csrfToken = token;
  sessionGeneration += 1;
}

export function onAdminUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export function getAdminApiErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null;
  const body = error.response?.data as { error?: { code?: string } } | undefined;
  return body?.error?.code ?? null;
}

function isStaleAdminRequest(config: InternalAxiosRequestConfig): boolean {
  const requestGeneration = (config as AdminRequestConfig)._adminSessionGeneration;
  return requestGeneration !== undefined && requestGeneration !== sessionGeneration;
}
