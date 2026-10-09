export interface PendingCartAdd {
  kind: "cart_add";
  productId: number;
  quantity: number;
  origin: string;
  mutationKey: string;
  createdAt: number;
}

export interface PendingFavoriteAdd {
  kind: "favorite_add";
  productId: number;
  mutationKey: string;
  createdAt: number;
}

export type PendingCustomerAction = PendingCartAdd | PendingFavoriteAdd;

const STORAGE_KEY = "kans-shop-pending-add";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function isSafeProductId(value: unknown): value is number {
  return Number.isSafeInteger(value) && typeof value === "number" && value > 0;
}

function isFreshTimestamp(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function isMutationKey(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isSafeOrigin(value: unknown): value is string {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//");
}

function isLegacyCartAdd(value: Record<string, unknown>): boolean {
  return (
    !Object.hasOwn(value, "kind") &&
    isSafeProductId(value.productId) &&
    Number.isSafeInteger(value.quantity) && typeof value.quantity === "number" && value.quantity > 0 &&
    isSafeOrigin(value.origin) &&
    isMutationKey(value.mutationKey) &&
    isFreshTimestamp(value.createdAt)
  );
}

function normalizePendingAction(value: unknown): PendingCustomerAction | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const action = value as Record<string, unknown>;
  if (isLegacyCartAdd(action)) {
    return {
      kind: "cart_add",
      productId: action.productId as number,
      quantity: action.quantity as number,
      origin: action.origin as string,
      mutationKey: action.mutationKey as string,
      createdAt: action.createdAt as number,
    };
  }
  if (action.kind === "cart_add") {
    if (
      !isSafeProductId(action.productId) ||
      !Number.isSafeInteger(action.quantity) || typeof action.quantity !== "number" || action.quantity <= 0 ||
      !isSafeOrigin(action.origin) ||
      !isMutationKey(action.mutationKey) ||
      !isFreshTimestamp(action.createdAt)
    ) return null;
    return {
      kind: "cart_add",
      productId: action.productId,
      quantity: action.quantity,
      origin: action.origin,
      mutationKey: action.mutationKey,
      createdAt: action.createdAt,
    };
  }
  if (action.kind === "favorite_add") {
    if (
      !isSafeProductId(action.productId) ||
      !isMutationKey(action.mutationKey) ||
      !isFreshTimestamp(action.createdAt)
    ) return null;
    return {
      kind: "favorite_add",
      productId: action.productId,
      mutationKey: action.mutationKey,
      createdAt: action.createdAt,
    };
  }
  return null;
}

export function isPendingAddFresh(intent: PendingCustomerAction, nowMs: number): boolean {
  return (
    Number.isFinite(nowMs) &&
    intent.createdAt <= nowMs &&
    nowMs - intent.createdAt < MAX_AGE_MS
  );
}

export function readPendingAdd(nowMs: number): PendingCustomerAction | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    const intent = normalizePendingAction(parsed);
    if (!intent || !isPendingAddFresh(intent, nowMs)) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return intent;
  } catch {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage may be unavailable in restricted browser contexts.
    }
    return null;
  }
}

export function writePendingAdd(intent: PendingCustomerAction): void {
  if (!normalizePendingAction(intent)) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(intent));
  } catch {
    // The current page can still retry in memory when storage is unavailable.
  }
}

export function clearPendingAdd(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
}
