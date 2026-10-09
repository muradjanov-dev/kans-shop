import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  adminApi,
  getAdminApiErrorCode,
  onAdminUnauthorized,
  setAdminCsrfToken,
  StaleAdminResponseError,
  type AdminSession,
} from "@/admin/api";

export type AdminAuthStatus = "checking" | "anonymous" | "authenticated";
export type AdminAuthNotice = "session-expired" | "unavailable" | null;

interface AdminAuthContextValue {
  session: AdminSession | null;
  status: AdminAuthStatus;
  notice: AdminAuthNotice;
  loginErrorCode: string | null;
  login: (code: string) => Promise<void>;
  clearLoginError: () => void;
  retrySessionCheck: () => Promise<void>;
  refreshSession: () => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
}

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSessionState] = useState<AdminSession | null>(null);
  const [status, setStatus] = useState<AdminAuthStatus>("checking");
  const [notice, setNotice] = useState<AdminAuthNotice>(null);
  const [loginErrorCode, setLoginErrorCode] = useState<string | null>(null);
  const sessionRef = useRef<AdminSession | null>(null);

  const setSession = useCallback((nextSession: AdminSession | null) => {
    sessionRef.current = nextSession;
    setSessionState(nextSession);
    setAdminCsrfToken(nextSession?.csrf_token ?? null);
  }, []);

  const clearPrivateData = useCallback(() => {
    const isAdminQuery = (query: { queryKey: readonly unknown[] }) => query.queryKey[0] === "admin";
    void queryClient.cancelQueries({ predicate: isAdminQuery });
    queryClient.removeQueries({ predicate: isAdminQuery });
  }, [queryClient]);

  const clearSession = useCallback((expired: boolean) => {
    setSession(null);
    setStatus("anonymous");
    setNotice(expired ? "session-expired" : null);
    setLoginErrorCode(null);
    clearPrivateData();
  }, [clearPrivateData, setSession]);

  const retrySessionCheck = useCallback(async () => {
    setStatus("checking");
    setNotice(null);
    try {
      setSession(await adminApi.loadSession());
      setStatus("authenticated");
    } catch (error) {
      if (isStaleAdminResponse(error)) return;
      clearSession(Boolean(sessionRef.current));
      setNotice("unavailable");
    }
  }, [clearSession, setSession]);

  useEffect(() => {
    const unsubscribe = onAdminUnauthorized(() => clearSession(Boolean(sessionRef.current)));
    let cancelled = false;

    void adminApi.loadSession().then((loadedSession) => {
      if (cancelled) return;
      setSession(loadedSession);
      setStatus("authenticated");
      setNotice(null);
    }).catch((error: unknown) => {
      if (cancelled || isStaleAdminResponse(error)) return;
      clearSession(Boolean(sessionRef.current));
      if (!isUnauthorized(error)) setNotice("unavailable");
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [clearSession, setSession]);

  const login = useCallback(async (code: string) => {
    setLoginErrorCode(null);
    setNotice(null);
    try {
      setSession(await adminApi.exchangeCode(code));
      setStatus("authenticated");
    } catch (error) {
      if (!isStaleAdminResponse(error)) {
        setLoginErrorCode(getAdminApiErrorCode(error) ?? "ADMIN_LOGIN_FAILED");
      }
      throw error;
    }
  }, [setSession]);

  const clearLoginError = useCallback(() => setLoginErrorCode(null), []);

  const refreshSession = useCallback(async () => {
    try {
      setSession(await adminApi.refreshSession());
      setStatus("authenticated");
      setNotice(null);
    } catch (error) {
      if (isUnauthorized(error)) clearSession(Boolean(sessionRef.current));
      throw error;
    }
  }, [clearSession, setSession]);

  const logout = useCallback(async () => {
    await adminApi.logout();
    clearSession(false);
  }, [clearSession]);

  const logoutAll = useCallback(async () => {
    await adminApi.logoutAll();
    clearSession(false);
  }, [clearSession]);

  return (
    <AdminAuthContext.Provider value={{
      session,
      status,
      notice,
      loginErrorCode,
      login,
      clearLoginError,
      retrySessionCheck,
      refreshSession,
      logout,
      logoutAll,
    }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth(): AdminAuthContextValue {
  const context = useContext(AdminAuthContext);
  if (!context) throw new Error("useAdminAuth must be used inside AdminAuthProvider");
  return context;
}

function isUnauthorized(error: unknown): boolean {
  return typeof error === "object" && error !== null &&
    "response" in error && (error as { response?: { status?: number } }).response?.status === 401;
}

function isStaleAdminResponse(error: unknown): boolean {
  return error instanceof StaleAdminResponseError ||
    (typeof error === "object" && error !== null && "name" in error &&
      (error as { name?: string }).name === "StaleAdminResponseError");
}
