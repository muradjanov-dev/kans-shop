import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import axios from "axios";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import type { Cart, Product } from "@/types/api";
import { CartPage } from "@/pages/CartPage";
import { renderWithProviders } from "@/test/renderWithProviders";
import { ProductCard } from "@/components/ProductCard";
import { ProductPage } from "@/pages/ProductPage";
import { App } from "@/App";
import { Layout } from "@/components/Layout";
import { useCart } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";

const product: Product = {
  id: 12,
  category_id: 1,
  name_uz: "Daftar",
  name_ru: "Тетрадь",
  description_uz: null,
  description_ru: null,
  sku: "NB-12",
  price: "1000",
  old_price: null,
  stock_qty: 8,
  unit: "dona",
  min_order_qty: 1,
  is_active: true,
  is_featured: false,
  lot_url: null,
  views_count: 0,
  sold_count: 0,
  images: [],
};

function jwt(sub: number): string {
  const payload = btoa(JSON.stringify({ sub: String(sub) }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `e30.${payload}.signature`;
}

function response<T>(config: Parameters<AxiosAdapter>[0], data: T, status = 201): AxiosResponse<T> {
  return { data, status, statusText: status === 200 ? "OK" : "Created", headers: new AxiosHeaders(), config };
}

function ProductToCartRoutes() {
  const location = useLocation();
  return (
    <>
      <Routes>
        <Route path="/product/:id" element={<ProductPage />} />
        <Route path="/cart" element={<p>Cart destination</p>} />
      </Routes>
      <output data-testid="route-location">{location.pathname}</output>
    </>
  );
}

function ProductToCartWithCartRead() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const isAuthenticated = Boolean(accessToken && userId);
  useCart(isAuthenticated);
  return (
    <Routes>
      <Route path="/product/:id" element={<ProductCard product={product} />} />
      <Route path="/cart" element={<CartPage />} />
    </Routes>
  );
}

function TestLogoutButton() {
  const { logout } = useCustomerAuth();
  return <button onClick={logout} type="button">Sign out test session</button>;
}

function TestSwitchAccountButton() {
  return (
    <button
      onClick={() => useAuthStore.getState().setTokens({
        access_token: jwt(99),
        refresh_token: "refresh-99",
        is_admin: false,
      })}
      type="button"
    >
      Switch test account
    </button>
  );
}

describe("cart action recovery", () => {
  it("keeps a saved language when Telegram advertises a different locale", async () => {
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    useLanguageStore.getState().setLanguage("ru");
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "signed-init-data",
          initDataUnsafe: { user: { id: 999, language_code: "uz" } },
        },
      },
    });
    axios.defaults.adapter = async (config) => ({
      data: {
        access_token: jwt(42),
        refresh_token: "refresh-42",
        token_type: "bearer",
        is_admin: false,
      },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
    });
    api.defaults.adapter = async (config) => response(
      config,
      config.url?.endsWith("/catalog/categories")
        ? []
        : { items: [], subtotal: "0", items_count: 0 },
      200,
    );

    try {
      renderWithProviders(<App />);
      expect(await screen.findByRole("heading", { name: "Категории" })).toBeInTheDocument();
      expect(useLanguageStore.getState().language).toBe("ru");
    } finally {
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
      delete (window as Window & { Telegram?: unknown }).Telegram;
    }
  });

  it("offers a browser login action instead of requiring Telegram", () => {
    renderWithProviders(<CartPage />, "/cart", true);

    expect(screen.getByRole("button", { name: /sign in|kirish|войти/i })).toBeInTheDocument();
  });

  it("offers sign-in immediately in a plain browser and keeps the catalog available", () => {
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    Object.defineProperty(window, "Telegram", { configurable: true, value: undefined });
    api.defaults.adapter = async (config) => response(config, []);

    try {
      renderWithProviders(<App />);

      expect(screen.getByRole("button", { name: "Kirish" })).toBeInTheDocument();
      expect(screen.getByText("Kategoriyalar")).toBeInTheDocument();
    } finally {
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
      delete (window as Window & { Telegram?: unknown }).Telegram;
    }
  });

  it("keeps automatic validated auth for a Telegram Mini App", async () => {
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    const token = jwt(42);
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "signed-init-data",
          initDataUnsafe: { user: { id: 999, language_code: "ru" } },
        },
      },
    });
    axios.defaults.adapter = async (config) => ({
      data: {
        access_token: token,
        refresh_token: "refresh-42",
        token_type: "bearer",
        is_admin: false,
      },
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
    });
    api.defaults.adapter = async (config) => response(
      config,
      config.url?.endsWith("/cart") ? { items: [], subtotal: "0", items_count: 0 } : [],
    );

    try {
      renderWithProviders(<App />);

      expect(await screen.findByRole("button", { name: "Сменить аккаунт" })).toBeInTheDocument();
      expect(useAuthStore.getState().accessToken).toBe(token);
      expect(useAuthStore.getState().userId).toBe("42");
      const user = userEvent.setup();
      await user.click(screen.getByRole("button", { name: "Сменить аккаунт" }));
      await screen.findByRole("dialog");
      await user.click(screen.getByRole("button", { name: "Отмена" }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Выйти" }));
      expect(useAuthStore.getState().accessToken).toBeNull();
      expect(await screen.findByRole("button", { name: "Войти" })).toBeInTheDocument();
    } finally {
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
      delete (window as Window & { Telegram?: unknown }).Telegram;
    }
  });

  it("starts at minimum quantity and stops at available stock on the detail page", async () => {
    const detailProduct = { ...product, min_order_qty: 3, stock_qty: 5 };
    const originalAdapter = api.defaults.adapter;
    const adapter: AxiosAdapter = async (config) => response(config, detailProduct);
    api.defaults.adapter = adapter;
    const user = userEvent.setup();
    function ProductRoute() {
      return (
        <Routes>
          <Route path="/product/:id" element={<ProductPage />} />
        </Routes>
      );
    }

    try {
      renderWithProviders(<ProductRoute />, "/product/12", true);
      expect(await screen.findByText("3")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /orqaga/i })).toHaveClass("min-h-11", "focus-visible:outline-2");
      expect(screen.getByRole("button", { name: /miqdorni kamaytirish/i })).toBeDisabled();

      const increase = screen.getByRole("button", { name: /miqdorni oshirish/i });
      await user.click(increase);
      await user.click(increase);

      expect(screen.getByText("5")).toBeInTheDocument();
      expect(increase).toBeDisabled();
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });

  it("navigates from product detail to the cart only after add succeeds", async () => {
    const detailProduct = { ...product, min_order_qty: 2 };
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    const tokens = {
      access_token: jwt(42),
      refresh_token: "refresh-42",
      token_type: "bearer",
      is_admin: false,
    };
    const cart: Cart = { items: [], subtotal: "0", items_count: 0 };
    let releaseAdd!: () => void;
    let startAdd!: () => void;
    const addStarted = new Promise<void>((resolve) => { startAdd = resolve; });
    const addResponse = new Promise<void>((resolve) => { releaseAdd = resolve; });
    api.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/catalog/products/12")) return response(config, detailProduct, 200);
      if (config.url?.endsWith("/cart/items")) {
        startAdd();
        await addResponse;
        return response(config, cart);
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`);
    };
    axios.defaults.adapter = async (config) => ({
      data: tokens,
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
    });
    const user = userEvent.setup();

    try {
      renderWithProviders(<ProductToCartRoutes />, "/product/12", true);
      await screen.findByText("Daftar");
      await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
      await user.type(await screen.findByLabelText("Kirish kodi"), "765432");
      await user.click(screen.getByRole("button", { name: "Kirish" }));
      await addStarted;

      expect(screen.getByTestId("route-location")).toHaveTextContent("/product/12");
      expect(screen.queryByText("Cart destination")).not.toBeInTheDocument();
      releaseAdd();

      expect(await screen.findByText("Cart destination")).toBeInTheDocument();
      expect(screen.getByTestId("route-location")).toHaveTextContent("/cart");
    } finally {
      releaseAdd();
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
    }
  });

  it("does not increment the cart badge until the add request succeeds", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const emptyCart: Cart = { items: [], subtotal: "0", items_count: 0 };
    const addedCart: Cart = {
      items: [{ id: 7, product_id: 12, quantity: 1, price_snapshot: "1000", product }],
      subtotal: "1000",
      items_count: 1,
    };
    const originalAdapter = api.defaults.adapter;
    let releaseAdd!: () => void;
    let signalAdd!: () => void;
    const addStarted = new Promise<void>((resolve) => { signalAdd = resolve; });
    const addResponse = new Promise<void>((resolve) => { releaseAdd = resolve; });
    const adapter: AxiosAdapter = async (config) => {
      if (config.method === "get") return response(config, emptyCart, 200);
      if (config.method === "post") {
        signalAdd();
        await addResponse;
        return response(config, addedCart);
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`);
    };
    api.defaults.adapter = adapter;
    const user = userEvent.setup();
    function StorefrontRoute() {
      return (
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<ProductCard product={product} />} />
          </Route>
        </Routes>
      );
    }

    try {
      renderWithProviders(<StorefrontRoute />, "/", true);
      const nav = screen.getByRole("navigation", { name: "Mobil menyu" });
      await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
      await addStarted;
      expect(within(nav).queryByText("1")).not.toBeInTheDocument();

      releaseAdd();
      expect(await within(nav).findByText("1")).toBeInTheDocument();
    } finally {
      releaseAdd();
      api.defaults.adapter = originalAdapter;
    }
  });

  it("does not let a late empty cart read overwrite a successful guest add", async () => {
    useAuthStore.getState().clear();
    localStorage.removeItem("kans-shop-pending-add");
    useLanguageStore.getState().setLanguage("uz");
    const emptyCart: Cart = { items: [], subtotal: "0", items_count: 0 };
    const addedCart: Cart = {
      items: [{ id: 7, product_id: 12, quantity: 1, price_snapshot: "1000", product }],
      subtotal: "1000",
      items_count: 1,
    };
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    let releaseCartRead!: () => void;
    let signalCartRead!: () => void;
    const cartReadGate = new Promise<void>((resolve) => { releaseCartRead = resolve; });
    const cartReadStarted = new Promise<void>((resolve) => { signalCartRead = resolve; });
    let cartReadCount = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart" && config.method === "get") {
        cartReadCount += 1;
        if (cartReadCount === 1) {
          signalCartRead();
          await cartReadGate;
          return response(config, emptyCart, 200);
        }
        return response(config, addedCart, 200);
      }
      if (config.url === "/cart/items" && config.method === "post") {
        await cartReadStarted;
        return response(config, addedCart);
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`);
    };
    axios.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/auth/customer/code")) {
        return response(config, {
          access_token: jwt(42),
          refresh_token: "refresh-42",
          token_type: "bearer",
          is_admin: false,
        }, 200);
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    try {
      const rendered = renderWithProviders(<ProductToCartWithCartRead />, "/product/12", true);
      await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
      await user.type(await screen.findByLabelText("Kirish kodi"), "12345678");
      await user.click(screen.getByRole("button", { name: "Kirish" }));
      await cartReadStarted;
      expect(await screen.findByText("Daftar", { exact: true })).toBeInTheDocument();
      expect(rendered.queryClient.getQueryData(["cart", "42"])).toEqual(addedCart);

      releaseCartRead();
      await waitFor(() => {
        expect(rendered.queryClient.getQueryState(["cart", "42"])?.fetchStatus).toBe("idle");
      });

      expect(rendered.queryClient.getQueryData(["cart", "42"])).toEqual(addedCart);
      expect(screen.getByText("Daftar", { exact: true })).toBeInTheDocument();
      expect(screen.queryByText("Savatingiz bo'sh")).not.toBeInTheDocument();
    } finally {
      releaseCartRead();
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
      useAuthStore.getState().clear();
    }
  });

  it("removes the previous account cart when a second account signs in", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAdapter = api.defaults.adapter;
    const emptyCart: Cart = { items: [], subtotal: "0", items_count: 0 };
    api.defaults.adapter = async (config) => response(config, emptyCart, 200);

    try {
      const { queryClient } = renderWithProviders(<CartPage />, "/cart", true);
      queryClient.setQueryData(["cart", "42"], {
        items: [],
        subtotal: "500",
        items_count: 1,
      });

      useAuthStore.getState().setTokens({
        access_token: jwt(99),
        refresh_token: "refresh-99",
        is_admin: false,
      });

      await waitFor(() => expect(queryClient.getQueryData(["cart", "42"])).toBeUndefined());
      expect(useAuthStore.getState().userId).toBe("99");
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });

  it("reuses its mutation key after a timeout and provider remount under StrictMode", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAdapter = api.defaults.adapter;
    const keys: string[] = [];
    let addCalls = 0;
    const cart: Cart = { items: [], subtotal: "0", items_count: 0 };
    const adapter: AxiosAdapter = async (config) => {
      if (config.url?.endsWith("/cart/items")) {
        addCalls += 1;
        keys.push(String(config.headers.get("Idempotency-Key")));
        if (addCalls === 1) {
          throw new AxiosError("Timeout", "ECONNABORTED", config);
        }
        return response(config, cart);
      }
      throw new Error(`Unexpected request ${config.method} ${config.url}`);
    };
    api.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      const firstMount = renderWithProviders(<ProductCard product={product} />, "/", true, true);
      await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
      await screen.findByRole("alert");
      expect(addCalls).toBe(1);
      const savedIntent = JSON.parse(localStorage.getItem("kans-shop-pending-add") ?? "null") as {
        mutationKey: string;
      };

      firstMount.unmount();
      renderWithProviders(<ProductCard product={product} />, "/", true, true);

      await waitFor(() => expect(localStorage.getItem("kans-shop-pending-add")).toBeNull());
      expect(addCalls).toBe(2);
      expect(keys).toEqual([savedIntent.mutationKey, savedIntent.mutationKey]);
      expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/i);
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });

  it("aborts a cart update when the customer logs out", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAdapter = api.defaults.adapter;
    let updateSignal: AbortSignal | undefined;
    let releaseUpdate!: () => void;
    let signalUpdate!: () => void;
    const updateStarted = new Promise<void>((resolve) => { signalUpdate = resolve; });
    const updateResponse = new Promise<void>((resolve) => { releaseUpdate = resolve; });
    const initialCart: Cart = {
      items: [{ id: 7, product_id: 12, quantity: 2, price_snapshot: "300", product: { ...product, stock_qty: 5 } }],
      subtotal: "600",
      items_count: 2,
    };
    const adapter: AxiosAdapter = async (config) => {
      if (config.method === "patch") {
        updateSignal = config.signal as AbortSignal;
        signalUpdate();
        await updateResponse;
        return response(config, initialCart);
      }
      return response(config, initialCart, 200);
    };
    api.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      renderWithProviders(
        <>
          <CartPage />
          <TestLogoutButton />
        </>,
        "/cart",
        true,
      );
      await screen.findByText("2");
      await user.click(screen.getByRole("button", { name: /miqdorni oshirish/i }));
      await updateStarted;

      await user.click(screen.getByRole("button", { name: "Sign out test session" }));

      expect(updateSignal).toBeInstanceOf(AbortSignal);
      expect(updateSignal?.aborted).toBe(true);
    } finally {
      releaseUpdate();
      api.defaults.adapter = originalAdapter;
    }
  });

  it("aborts the previous cart mutation when a different account signs in", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAdapter = api.defaults.adapter;
    let updateSignal: AbortSignal | undefined;
    let releaseUpdate!: () => void;
    let signalUpdate!: () => void;
    const updateStarted = new Promise<void>((resolve) => { signalUpdate = resolve; });
    const updateResponse = new Promise<void>((resolve) => { releaseUpdate = resolve; });
    const initialCart: Cart = {
      items: [{ id: 7, product_id: 12, quantity: 2, price_snapshot: "300", product: { ...product, stock_qty: 5 } }],
      subtotal: "600",
      items_count: 2,
    };
    api.defaults.adapter = async (config) => {
      if (config.method === "patch") {
        updateSignal = config.signal as AbortSignal;
        signalUpdate();
        await updateResponse;
        return response(config, initialCart);
      }
      return response(config, initialCart, 200);
    };
    const user = userEvent.setup();

    try {
      renderWithProviders(
        <>
          <CartPage />
          <TestSwitchAccountButton />
        </>,
        "/cart",
        true,
      );
      await screen.findByText("2");
      await user.click(screen.getByRole("button", { name: /miqdorni oshirish/i }));
      await updateStarted;
      await user.click(screen.getByRole("button", { name: "Switch test account" }));
      await waitFor(() => expect(updateSignal?.aborted).toBe(true));
      expect(updateSignal).toBeInstanceOf(AbortSignal);
      expect(useAuthStore.getState().userId).toBe("99");
    } finally {
      releaseUpdate();
      api.defaults.adapter = originalAdapter;
    }
  });

  it("does not retry a pending add after its 24-hour expiry", async () => {
    const createdAt = 1_800_000_000_000;
    const now = vi.spyOn(Date, "now").mockReturnValue(createdAt);
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    localStorage.setItem("kans-shop-pending-add", JSON.stringify({
      productId: 12,
      quantity: 1,
      origin: "/",
      mutationKey: "stable-key",
      createdAt,
    }));
    const originalAdapter = api.defaults.adapter;
    let addCalls = 0;
    const adapter: AxiosAdapter = async (config) => {
      if (config.url === "/cart/items" && config.method === "post") addCalls += 1;
      throw new AxiosError("Timeout", "ECONNABORTED", config);
    };
    api.defaults.adapter = adapter;

    try {
      renderWithProviders(<ProductCard product={product} />, "/", true);
      await screen.findByRole("alert");
      now.mockReturnValue(createdAt + 24 * 60 * 60 * 1000);
      fireEvent.click(screen.getByRole("button", { name: "Qayta urinish" }));

      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Savat harakati muddati tugadi."));
      expect(addCalls).toBe(1);
      expect(localStorage.getItem("kans-shop-pending-add")).toBeNull();
    } finally {
      now.mockRestore();
      api.defaults.adapter = originalAdapter;
    }
  });
});
