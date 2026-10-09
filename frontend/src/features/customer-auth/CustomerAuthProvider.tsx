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
import { useLocation, useNavigate } from "react-router-dom";
import { api, cancelAuthenticatedRequests, getApiErrorCode } from "@/lib/api";
import { setCustomerCartFromServer } from "@/lib/cartCache";
import { customerQueryKeys } from "@/hooks/queries";
import { useTranslate } from "@/lib/i18n";
import {
  clearPendingAdd,
  isPendingAddFresh,
  readPendingAdd,
  writePendingAdd,
  type PendingCustomerAction,
} from "@/lib/pendingCartAdd";
import { useAuthStore } from "@/store/auth";
import type { Cart } from "@/types/api";
import { CustomerCodeDialog } from "@/features/customer-auth/CustomerCodeDialog";
import { useCustomerCodeLogin } from "@/features/customer-auth/useCustomerCodeLogin";

interface CustomerAuthContextValue {
  add: (productId: number, quantity: number, origin: string) => void;
  addFavorite: (productId: number) => void;
  retry: () => void;
  cancelLogin: () => void;
  pending: boolean;
  errorCode: string | null;
  openLogin: () => void;
  logout: () => void;
}

const CustomerAuthContext = createContext<CustomerAuthContextValue | null>(null);

function isPrivateQuery(queryKey: readonly unknown[]): boolean {
  const root = queryKey[0];
  return root === "cart" || root === "orders" || root === "order" || root === "lot-links" ||
    root === "order-history" || root === "order-timeline" ||
    root === "profile" || root === "addresses" || root === "favorites" || root === "favorite-state";
}

function discardPrivateData(
  queryClient: ReturnType<typeof useQueryClient>,
  ownerUserId: string,
): void {
  const isOwnedQuery = (query: { queryKey: readonly unknown[] }) =>
    isPrivateQuery(query.queryKey) && (
      query.queryKey[1] === ownerUserId || typeof query.queryKey[1] !== "string"
    );
  void queryClient.cancelQueries({ predicate: isOwnedQuery });
  queryClient.removeQueries({ predicate: isOwnedQuery });
}

function makeMutationKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

export function CustomerAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const t = useTranslate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  const login = useCustomerCodeLogin();
  const [pendingIntent, setPendingIntent] = useState<PendingCustomerAction | null>(() => readPendingAdd(Date.now()));
  const [dialogOpen, setDialogOpen] = useState(
    () => !useAuthStore.getState().accessToken && readPendingAdd(Date.now()) !== null,
  );
  const [actionPending, setActionPending] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [expiredActionKind, setExpiredActionKind] = useState<PendingCustomerAction["kind"] | null>(null);
  const pendingIntentRef = useRef<PendingCustomerAction | null>(pendingIntent);
  const pendingOwnerRef = useRef<string | null>(useAuthStore.getState().userId);
  const previousAuthRef = useRef({ userId, authEpoch });
  const loginGenerationRef = useRef(0);
  const runningKeysRef = useRef(new Set<string>());
  const attemptedKeysRef = useRef(new Set<string>());

  const setIntent = useCallback((intent: PendingCustomerAction | null) => {
    pendingIntentRef.current = intent;
    setPendingIntent(intent);
    if (!intent) {
      clearPendingAdd();
      pendingOwnerRef.current = null;
    } else {
      writePendingAdd(intent);
    }
  }, []);

  const expireIntent = useCallback((intent: PendingCustomerAction) => {
    if (pendingIntentRef.current?.mutationKey !== intent.mutationKey) return;
    setIntent(null);
    setDialogOpen(false);
    setActionPending(false);
    setErrorCode(null);
    setExpiredActionKind(intent.kind);
  }, [setIntent]);

  const runIntent = useCallback(async (
    intent: PendingCustomerAction,
    expectedEpoch: number,
    expectedUserId: string,
  ) => {
    if (!isPendingAddFresh(intent, Date.now())) {
      expireIntent(intent);
      return;
    }
    if (runningKeysRef.current.has(intent.mutationKey)) return;
    runningKeysRef.current.add(intent.mutationKey);
    if (pendingOwnerRef.current === null) pendingOwnerRef.current = expectedUserId;
    setActionPending(true);
    setErrorCode(null);
    try {
      let cart: Cart | undefined;
      if (intent.kind === "cart_add") {
        const result = await api.post<Cart>(
          "/cart/items",
          { product_id: intent.productId, quantity: intent.quantity },
          { headers: { "Idempotency-Key": intent.mutationKey } },
        );
        cart = result.data;
      } else {
        await api.put<void>(`/favorites/${intent.productId}`, undefined, {
          headers: { "Idempotency-Key": intent.mutationKey },
        });
      }
      const current = useAuthStore.getState();
      if (current.authEpoch !== expectedEpoch || current.userId !== expectedUserId) return;
      if (intent.kind === "cart_add" && cart) {
        const written = await setCustomerCartFromServer(
          queryClient,
          expectedUserId,
          expectedEpoch,
          cart,
        );
        if (!written) return;
      } else if (intent.kind === "favorite_add") {
        void queryClient.invalidateQueries({ queryKey: customerQueryKeys.favoriteState(expectedUserId, intent.productId) });
        void queryClient.invalidateQueries({ queryKey: customerQueryKeys.favoritesRoot(expectedUserId) });
      }
      const afterCartUpdate = useAuthStore.getState();
      if (afterCartUpdate.authEpoch !== expectedEpoch || afterCartUpdate.userId !== expectedUserId) return;
      if (pendingIntentRef.current?.mutationKey === intent.mutationKey) {
        setIntent(null);
        if (intent.kind === "cart_add" && intent.origin.startsWith("/product/")) navigate("/cart");
      }
    } catch (error) {
      const current = useAuthStore.getState();
      if (current.authEpoch !== expectedEpoch || current.userId !== expectedUserId) return;
      setErrorCode(getApiErrorCode(error) ?? "CART_ADD_FAILED");
    } finally {
      runningKeysRef.current.delete(intent.mutationKey);
      const current = useAuthStore.getState();
      if (
        current.authEpoch === expectedEpoch &&
        current.userId === expectedUserId &&
        (!pendingIntentRef.current || pendingIntentRef.current.mutationKey === intent.mutationKey)
      ) {
        setActionPending(false);
      }
    }
  }, [expireIntent, navigate, queryClient, setIntent]);

  useEffect(() => {
    const previous = previousAuthRef.current;
    if (previous.userId !== userId || previous.authEpoch !== authEpoch) {
      if (previous.userId) {
        cancelAuthenticatedRequests(previous.authEpoch);
        discardPrivateData(queryClient, previous.userId);
      }
      if (previous.userId && !userId) {
        setIntent(null);
        setDialogOpen(false);
        setErrorCode(null);
        setActionPending(false);
      } else if (
        previous.userId &&
        userId &&
        previous.userId !== userId &&
        pendingOwnerRef.current === previous.userId
      ) {
        setIntent(null);
        setErrorCode(null);
        setActionPending(false);
      }
      previousAuthRef.current = { userId, authEpoch };
    }
  }, [authEpoch, queryClient, setIntent, userId]);

  useEffect(() => {
    if (!pendingIntent || !accessToken || !userId) return;
    if (attemptedKeysRef.current.has(pendingIntent.mutationKey)) return;
    attemptedKeysRef.current.add(pendingIntent.mutationKey);
    void runIntent(pendingIntent, authEpoch, userId);
  }, [accessToken, authEpoch, pendingIntent, runIntent, userId]);

  const add = useCallback((productId: number, quantity: number, origin: string) => {
    if (pendingIntentRef.current) return;
    setExpiredActionKind(null);
    const normalizedOrigin = origin.startsWith("/") ? origin : "/";
    const intent: Extract<PendingCustomerAction, { kind: "cart_add" }> = {
      kind: "cart_add",
      productId,
      quantity,
      origin: normalizedOrigin,
      mutationKey: makeMutationKey(),
      createdAt: Date.now(),
    };
    pendingOwnerRef.current = useAuthStore.getState().userId;
    setIntent(intent);
    setErrorCode(null);
    if (!useAuthStore.getState().accessToken) setDialogOpen(true);
  }, [setIntent]);

  const addFavorite = useCallback((productId: number) => {
    if (pendingIntentRef.current || useAuthStore.getState().accessToken) return;
    setIntent({
      kind: "favorite_add",
      productId,
      mutationKey: makeMutationKey(),
      createdAt: Date.now(),
    });
    pendingOwnerRef.current = null;
    setErrorCode(null);
    setExpiredActionKind(null);
    setDialogOpen(true);
  }, [setIntent]);

  const retry = useCallback(() => {
    const intent = pendingIntentRef.current;
    if (!intent) return;
    const current = useAuthStore.getState();
    if (!current.accessToken || !current.userId) {
      setDialogOpen(true);
      setErrorCode(null);
      return;
    }
    void runIntent(intent, current.authEpoch, current.userId);
  }, [runIntent]);

  const cancelLogin = useCallback(() => {
    loginGenerationRef.current += 1;
    const intent = pendingIntentRef.current;
    setIntent(null);
    setDialogOpen(false);
    setErrorCode(null);
    setExpiredActionKind(null);
    setActionPending(false);
    if (intent?.kind === "cart_add" && location.pathname + location.search !== intent.origin) {
      navigate(intent.origin);
    }
  }, [location.pathname, location.search, navigate, setIntent]);

  const submitCode = useCallback(async (code: string) => {
    const pending = pendingIntentRef.current;
    if (pending && !isPendingAddFresh(pending, Date.now())) {
      expireIntent(pending);
      return;
    }
    const generation = ++loginGenerationRef.current;
    const expectedEpoch = useAuthStore.getState().authEpoch;
    setErrorCode(null);
    try {
      const tokens = await login.mutateAsync(code);
      const current = useAuthStore.getState();
      if (generation !== loginGenerationRef.current || current.authEpoch !== expectedEpoch) return;
      current.setTokens(tokens);
      setDialogOpen(false);
    } catch (error) {
      const current = useAuthStore.getState();
      if (generation !== loginGenerationRef.current || current.authEpoch !== expectedEpoch) return;
      setErrorCode(getApiErrorCode(error) ?? "CUSTOMER_LOGIN_FAILED");
    }
  }, [expireIntent, login]);

  const openLogin = useCallback(() => {
    setErrorCode(null);
    setExpiredActionKind(null);
    setDialogOpen(true);
  }, []);

  const logout = useCallback(() => {
    loginGenerationRef.current += 1;
    setIntent(null);
    setDialogOpen(false);
    setActionPending(false);
    setErrorCode(null);
    setExpiredActionKind(null);
    const current = useAuthStore.getState();
    if (current.userId) {
      cancelAuthenticatedRequests(current.authEpoch);
      discardPrivateData(queryClient, current.userId);
    }
    current.clear();
  }, [queryClient, setIntent]);

  const value: CustomerAuthContextValue = {
    add,
    addFavorite,
    retry,
    cancelLogin,
    pending: actionPending || login.isPending,
    errorCode,
    openLogin,
    logout,
  };

  return (
    <CustomerAuthContext.Provider value={value}>
      {children}
      <CustomerCodeDialog
        open={dialogOpen}
        pending={login.isPending}
        errorCode={dialogOpen ? errorCode : null}
        onSubmit={(code) => void submitCode(code)}
        onCancel={cancelLogin}
        onCodeChange={() => setErrorCode(null)}
      />
      {errorCode && pendingIntent && !dialogOpen && (
        <div className="fixed bottom-28 left-3 right-3 z-[90] mx-auto flex max-w-md flex-col gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-800 shadow-lg dark:bg-red-950/80 dark:text-red-100" role="alert">
          <p>{t(pendingIntent.kind === "cart_add" ? "cart.action_pending" : "favorite.action_pending")}</p>
          <div className="flex gap-2">
            <button className="rounded-lg bg-brand px-3 py-2 font-semibold text-white" onClick={retry} type="button">
              {t(pendingIntent.kind === "cart_add" ? "cart.retry" : "favorite.retry_action")}
            </button>
            <button className="rounded-lg border border-red-300 px-3 py-2 font-semibold" onClick={cancelLogin} type="button">
              {t(pendingIntent.kind === "cart_add" ? "cart.cancel_pending" : "favorite.cancel_pending")}
            </button>
          </div>
        </div>
      )}
      {expiredActionKind && !dialogOpen && (
        <p className="fixed bottom-28 left-3 right-3 z-[90] mx-auto max-w-md rounded-xl bg-amber-50 p-3 text-sm text-amber-900 shadow-lg dark:bg-amber-950/80 dark:text-amber-100" role="alert">
          {t(expiredActionKind === "cart_add" ? "cart.intent_expired" : "favorite.intent_expired")}
        </p>
      )}
    </CustomerAuthContext.Provider>
  );
}

export function useCustomerAuth(): Pick<CustomerAuthContextValue, "openLogin" | "logout"> {
  const context = useContext(CustomerAuthContext);
  if (!context) throw new Error("useCustomerAuth must be used within CustomerAuthProvider");
  return { openLogin: context.openLogin, logout: context.logout };
}

export function useCustomerAuthActions(): CustomerAuthContextValue {
  const context = useContext(CustomerAuthContext);
  if (!context) throw new Error("useCustomerAuthActions must be used within CustomerAuthProvider");
  return context;
}
