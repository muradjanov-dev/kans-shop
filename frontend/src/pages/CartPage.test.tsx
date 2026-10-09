import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import axios, { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import type { Cart, Product } from "@/types/api";
import { CartPage } from "@/pages/CartPage";
import { renderWithProviders } from "@/test/renderWithProviders";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const product: Product = {
  id: 12,
  category_id: 1,
  name_uz: "Daftar",
  name_ru: "Тетрадь",
  description_uz: null,
  description_ru: null,
  sku: "NB-12",
  price: "450",
  old_price: null,
  stock_qty: 2,
  unit: "dona",
  min_order_qty: 2,
  is_active: true,
  is_featured: false,
  lot_url: null,
  views_count: 0,
  sold_count: 0,
  images: [],
};

const cart: Cart = {
  items: [{ id: 7, product_id: 12, quantity: 2, price_snapshot: "300", product }],
  subtotal: "900",
  items_count: 2,
};

function jwt(sub: number): string {
  const payload = btoa(JSON.stringify({ sub: String(sub) }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `e30.${payload}.signature`;
}

function response<T>(config: Parameters<AxiosAdapter>[0], data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: new AxiosHeaders(), config };
}

function unauthorized(config: Parameters<AxiosAdapter>[0]): Promise<never> {
  const errorResponse = response(config, {
    error: { code: "UNAUTHORIZED", message: "expired", details: {} },
  }, 401);
  return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse));
}

describe("cart page", () => {
  it("keeps exact decimal values in line totals and the cart subtotal", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const decimalCart: Cart = {
      ...cart,
      items: [{ ...cart.items[0]!, quantity: 2, product: { ...product, price: "300.25" } }],
      subtotal: "600.50",
    };
    const originalAdapter = api.defaults.adapter;
    api.defaults.adapter = async (config) => response(config, decimalCart);

    try {
      renderWithProviders(<CartPage />, "/cart", true);
      expect(await screen.findAllByText(/600\.5\s+so'm/)).toHaveLength(2);
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });

  it("uses the current product price and caps quantity at available stock", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAdapter = api.defaults.adapter;
    const adapter: AxiosAdapter = async (config) => response(config, cart);
    api.defaults.adapter = adapter;

    try {
      renderWithProviders(<CartPage />, "/cart", true);

      expect(await screen.findAllByText(/900\s+so'm/)).toHaveLength(2);
      expect(screen.queryByText("600")).not.toBeInTheDocument();
      const increase = screen.getByRole("button", { name: /increase quantity|miqdorni oshirish/i });
      expect(increase).toBeDisabled();
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });

  it("keeps the rendered quantity unchanged until the server confirms an update", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const initialCart = {
      ...cart,
      items: [{ ...cart.items[0]!, product: { ...product, stock_qty: 5 } }],
    };
    const updatedCart: Cart = {
      ...initialCart,
      items: [{ ...initialCart.items[0]!, quantity: 3 }],
      subtotal: "1350",
      items_count: 3,
    };
    let signalUpdate!: () => void;
    let updateStarted!: () => void;
    const updateStartedPromise = new Promise<void>((resolve) => { updateStarted = resolve; });
    const updateResponse = new Promise<void>((resolve) => { signalUpdate = resolve; });
    const originalAdapter = api.defaults.adapter;
    const adapter: AxiosAdapter = async (config) => {
      if (config.method === "patch") {
        updateStarted();
        await updateResponse;
        return response(config, updatedCart);
      }
      return response(config, initialCart);
    };
    api.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      renderWithProviders(<CartPage />, "/cart", true);
      await screen.findByText("2");
      await user.click(screen.getByRole("button", { name: /miqdorni oshirish/i }));
      await updateStartedPromise;

      expect(screen.getByText("2")).toBeInTheDocument();
      signalUpdate();
      expect(await screen.findByText("3")).toBeInTheDocument();
    } finally {
      signalUpdate();
      api.defaults.adapter = originalAdapter;
    }
  });

  it("shows a localized update failure and does not retry the mutation", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const initialCart = {
      ...cart,
      items: [{ ...cart.items[0]!, product: { ...product, stock_qty: 5 } }],
    };
    const originalAdapter = api.defaults.adapter;
    let patchCalls = 0;
    const adapter: AxiosAdapter = async (config) => {
      if (config.method === "patch") {
        patchCalls += 1;
        const errorResponse = response(config, {
          error: { code: "STOCK_CHANGED", message: "stock changed", details: {} },
        }, 409);
        return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse));
      }
      return response(config, initialCart);
    };
    api.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      renderWithProviders(<CartPage />, "/cart", true);
      await screen.findByText("2");
      await user.click(screen.getByRole("button", { name: /miqdorni oshirish/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Savat miqdorini yangilab bo'lmadi. Yana urinib ko'ring.",
      );
      expect(patchCalls).toBe(1);
      expect(screen.getByText("2")).toBeInTheDocument();
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });

  it("does not show an old cart mutation error after the account changes", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const initialCart = {
      ...cart,
      items: [{ ...cart.items[0]!, product: { ...product, stock_qty: 5 } }],
    };
    const originalAdapter = api.defaults.adapter;
    let releaseUpdate!: () => void;
    let notifyUpdate!: () => void;
    const updateStarted = new Promise<void>((resolve) => { notifyUpdate = resolve; });
    const updateResponse = new Promise<void>((resolve) => { releaseUpdate = resolve; });
    const adapter: AxiosAdapter = async (config) => {
      if (config.method === "patch") {
        notifyUpdate();
        await updateResponse;
        return response(config, initialCart);
      }
      return response(config, initialCart);
    };
    api.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      renderWithProviders(<CartPage />, "/cart", true);
      await screen.findByText("2");
      await user.click(screen.getByRole("button", { name: /miqdorni oshirish/i }));
      await updateStarted;
      useAuthStore.getState().setTokens({
        access_token: jwt(99),
        refresh_token: "refresh-99",
        is_admin: false,
      });
      releaseUpdate();

      await waitFor(() => expect(screen.getByRole("button", { name: /miqdorni oshirish/i })).toBeEnabled());
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(useAuthStore.getState().userId).toBe("99");
    } finally {
      releaseUpdate();
      api.defaults.adapter = originalAdapter;
    }
  });

  it("offers sign-in after the access and refresh tokens expire", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    const adapter: AxiosAdapter = async (config) => unauthorized(config);
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter;

    try {
      renderWithProviders(<CartPage />, "/cart", true);

      expect(await screen.findByRole("button", { name: "Kirish" })).toBeInTheDocument();
      expect(useAuthStore.getState().accessToken).toBeNull();
    } finally {
      api.defaults.adapter = originalAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
    }
  });
});
