export interface PendingCartAdd {
  productId: number;
  quantity: number;
  origin: string;
  mutationKey: string;
  createdAt: number;
}

const STORAGE_KEY = "kans-shop-pending-add";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function isPendingCartAdd(value: unknown): value is PendingCartAdd {
  if (!value || typeof value !== "object") return false;
  const intent = value as Partial<PendingCartAdd>;
  return (
    Number.isSafeInteger(intent.productId) && (intent.productId ?? 0) > 0 &&
    Number.isSafeInteger(intent.quantity) && (intent.quantity ?? 0) > 0 &&
    typeof intent.origin === "string" && intent.origin.startsWith("/") && !intent.origin.startsWith("//") &&
    typeof intent.mutationKey === "string" && intent.mutationKey.length > 0 &&
    typeof intent.createdAt === "number" && Number.isFinite(intent.createdAt) && intent.createdAt > 0
  );
}

export function isPendingAddFresh(intent: PendingCartAdd, nowMs: number): boolean {
  return (
    isPendingCartAdd(intent) &&
    Number.isFinite(nowMs) &&
    intent.createdAt <= nowMs &&
    nowMs - intent.createdAt < MAX_AGE_MS
  );
}

export function readPendingAdd(nowMs: number): PendingCartAdd | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isPendingCartAdd(parsed) || !isPendingAddFresh(parsed, nowMs)) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return {
      productId: parsed.productId,
      quantity: parsed.quantity,
      origin: parsed.origin,
      mutationKey: parsed.mutationKey,
      createdAt: parsed.createdAt,
    };
  } catch {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage may be unavailable in restricted browser contexts.
    }
    return null;
  }
}

export function writePendingAdd(intent: PendingCartAdd): void {
  if (!isPendingCartAdd(intent)) return;
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
