import { describe, expect, it } from "vitest";
import { clearPendingAdd, readPendingAdd, writePendingAdd, type PendingCustomerAction } from "@/lib/pendingCartAdd";

const storageKey = "kans-shop-pending-add";

describe("pending cart intent recovery", () => {
  it("discards an intent that is at least 24 hours old", () => {
    const intent: PendingCustomerAction = {
      kind: "cart_add",
      productId: 12,
      quantity: 2,
      origin: "/product/12",
      mutationKey: "stable-key",
      createdAt: 100,
    };
    writePendingAdd(intent);

    expect(readPendingAdd(100 + 24 * 60 * 60 * 1000)).toBeNull();
    expect(localStorage.getItem(storageKey)).toBeNull();
  });

  it("discards malformed stored intent instead of replaying it", () => {
    localStorage.setItem(storageKey, '{"productId":"wrong"}');

    expect(readPendingAdd(10_000)).toBeNull();
    expect(localStorage.getItem(storageKey)).toBeNull();
  });

  it("keeps a well-formed intent before its expiry boundary", () => {
    const intent: PendingCustomerAction = {
      kind: "cart_add",
      productId: 12,
      quantity: 2,
      origin: "/product/12?variant=blue",
      mutationKey: "stable-key",
      createdAt: 100,
    };
    writePendingAdd(intent);

    expect(readPendingAdd(100 + 24 * 60 * 60 * 1000 - 1)).toEqual(intent);
    clearPendingAdd();
    expect(localStorage.getItem(storageKey)).toBeNull();
  });

  it("upgrades a legacy stored cart intent to the discriminated action shape", () => {
    const legacyIntent = {
      productId: 12,
      quantity: 2,
      origin: "/product/12",
      mutationKey: "legacy-stable-key",
      createdAt: 100,
    };
    localStorage.setItem(storageKey, JSON.stringify(legacyIntent));

    expect(readPendingAdd(10_000)).toEqual({ kind: "cart_add", ...legacyIntent });
  });

  it("reads a well-formed guest favorite action", () => {
    const intent = {
      kind: "favorite_add",
      productId: 12,
      mutationKey: "favorite-stable-key",
      createdAt: 100,
    };
    localStorage.setItem(storageKey, JSON.stringify(intent));

    expect(readPendingAdd(10_000)).toEqual(intent);
  });
});
