import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios, { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useAuthStore } from "@/store/auth";
import type { Cart, Product, TokenPair } from "@/types/api";
import { ProductCard } from "@/components/ProductCard";
import { renderWithProviders } from "@/test/renderWithProviders";

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

function RouteLocation() {
  const location = useLocation();
  return <output data-testid="route-location">{location.pathname}{location.search}</output>;
}

function LoginButton() {
  const { openLogin } = useCustomerAuth();
  return <button onClick={openLogin} type="button">Switch account</button>;
}

function jwt(sub: number): string {
  const payload = btoa(JSON.stringify({ sub: String(sub) }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `e30.${payload}.signature`;
}

function failureResponse(config: Parameters<AxiosAdapter>[0]): AxiosResponse {
  return {
    data: {
      error: {
        code: "INVALID_OR_EXPIRED_CODE",
        message: "Invalid or expired login code",
        details: {},
      },
    },
    status: 401,
    statusText: "Unauthorized",
    headers: new AxiosHeaders(),
    config,
  };
}

describe("customer code dialog", () => {
  it("opens bot instructions when a browser guest tries to add an item", async () => {
    renderWithProviders(<ProductCard product={product} />, "/", true);
    const addButton = screen.getByRole("button");

    expect(addButton).toBeEnabled();
    fireEvent.click(addButton);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /telegram/i })).toHaveAttribute(
      "href",
      "https://t.me/kansshopbot?start=web_login",
    );
    expect(screen.getByLabelText(/kirish kodi|код входа/i)).toBeInTheDocument();
  });

  it("keeps the first intent when another product is added while login is open", async () => {
    const secondProduct = { ...product, id: 13, name_uz: "Ruchka" };
    renderWithProviders(
      <>
        <ProductCard product={product} />
        <ProductCard product={secondProduct} />
      </>,
      "/",
      true,
    );
    const [firstAdd, secondAdd] = screen.getAllByRole("button");

    fireEvent.click(firstAdd!);
    fireEvent.click(secondAdd!);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("kans-shop-pending-add") ?? "null")).toMatchObject({
      productId: 12,
    });
  });

  it("shows the same retry guidance for an invalid or expired code", async () => {
    const originalAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    let submittedCode = "";
    const adapter: AxiosAdapter = async (config) => {
      submittedCode = JSON.parse(String(config.data)).code as string;
      return Promise.reject(
        new AxiosError(
          "Request failed",
          "ERR_BAD_REQUEST",
          config,
          undefined,
          failureResponse(config),
        ),
      );
    };
    api.defaults.adapter = adapter;
    axios.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      renderWithProviders(<ProductCard product={product} />, "/", true);
      await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
      await user.type(await screen.findByLabelText("Kirish kodi"), "123456");
      await user.click(screen.getByRole("button", { name: "Kirish" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Kod noto‘g‘ri yoki muddati o‘tgan; botdan yangi kod oling.",
      );
      expect(submittedCode).toBe("123456");
      expect(JSON.parse(localStorage.getItem("kans-shop-pending-add") ?? "null")).toMatchObject({
        productId: 12,
      });
    } finally {
      api.defaults.adapter = originalAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
    }
  });

  it("cancels login, discards the intent, and stays on the product route", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <ProductCard product={product} />
        <RouteLocation />
      </>,
      "/product/12?from=cart",
      true,
    );

    await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: /bekor qilish|отмена/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("route-location")).toHaveTextContent("/product/12?from=cart");
    expect(localStorage.getItem("kans-shop-pending-add")).toBeNull();
  });

  it("does not refresh or clear the current account for an invalid code during account switch", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    let refreshCalls = 0;
    const adapter: AxiosAdapter = async (config) => {
      if (config.url?.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        return {
          ...failureResponse(config),
          data: { access_token: jwt(42), refresh_token: "refresh-42", token_type: "bearer", is_admin: false },
          status: 200,
          statusText: "OK",
        };
      }
      return Promise.reject(
        new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, failureResponse(config)),
      );
    };
    axios.defaults.adapter = adapter;
    const user = userEvent.setup();

    try {
      renderWithProviders(<LoginButton />, "/", true);
      await user.click(screen.getByRole("button", { name: "Switch account" }));
      await user.type(await screen.findByLabelText("Kirish kodi"), "expired");
      await user.click(screen.getByRole("button", { name: "Kirish" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/Kod noto‘g‘ri/);
      expect(refreshCalls).toBe(0);
      expect(useAuthStore.getState().accessToken).toBe(jwt(42));
    } finally {
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
    }
  });

  it("exchanges the code and replays the stored add with its original key", async () => {
    const originalApiAdapter = api.defaults.adapter;
    const originalAxiosAdapter = axios.defaults.adapter;
    const tokens: TokenPair = {
      access_token: jwt(42),
      refresh_token: "refresh-42",
      token_type: "bearer",
      is_admin: false,
    };
    const cart: Cart = { items: [], subtotal: "0", items_count: 0 };
    let loginPath = "";
    let addBody: unknown;
    let addHeader = "";
    let bearer = "";
    axios.defaults.adapter = async (config) => {
      loginPath = String(config.url);
      return {
        data: tokens,
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        config,
      };
    };
    api.defaults.adapter = async (config) => {
      addBody = JSON.parse(String(config.data));
      addHeader = String(config.headers.get("Idempotency-Key"));
      bearer = String(config.headers.get("Authorization"));
      return {
        data: cart,
        status: 201,
        statusText: "Created",
        headers: new AxiosHeaders(),
        config,
      };
    };
    const user = userEvent.setup();

    try {
      renderWithProviders(<ProductCard product={product} />, "/", true);
      await user.click(screen.getByRole("button", { name: /savatga qo'shish/i }));
      const savedIntent = JSON.parse(localStorage.getItem("kans-shop-pending-add") ?? "null") as {
        productId: number;
        quantity: number;
        mutationKey: string;
      };
      await user.type(await screen.findByLabelText("Kirish kodi"), "765432");
      await user.click(screen.getByRole("button", { name: "Kirish" }));

      await waitFor(() => expect(localStorage.getItem("kans-shop-pending-add")).toBeNull());
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(loginPath).toMatch(/\/auth\/customer\/code$/);
      expect(addBody).toEqual({ product_id: 12, quantity: 1 });
      expect(addHeader).toBe(savedIntent.mutationKey);
      expect(bearer).toBe(`Bearer ${tokens.access_token}`);
      expect(useAuthStore.getState().userId).toBe("42");
      expect(localStorage.getItem("kans-shop-pending-add")).toBeNull();
      expect(screen.getByRole("button", { name: /savatga qo'shish/i })).toBeEnabled();
    } finally {
      api.defaults.adapter = originalApiAdapter;
      axios.defaults.adapter = originalAxiosAdapter;
    }
  });

  it("ignores a code exchange that completes after the active account changes", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const originalAxiosAdapter = axios.defaults.adapter;
    const replacementTokens = {
      access_token: jwt(77),
      refresh_token: "refresh-77",
      token_type: "bearer",
      is_admin: false,
    };
    const switchedTokens = {
      access_token: jwt(99),
      refresh_token: "refresh-99",
      token_type: "bearer",
      is_admin: false,
    };
    let resolveLogin!: () => void;
    let startLogin!: () => void;
    const loginStarted = new Promise<void>((resolve) => { startLogin = resolve; });
    const loginReady = new Promise<void>((resolve) => { resolveLogin = resolve; });
    axios.defaults.adapter = async (config) => {
      startLogin();
      await loginReady;
      return {
        data: replacementTokens,
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        config,
      };
    };
    const user = userEvent.setup();

    try {
      renderWithProviders(<LoginButton />, "/", true);
      await user.click(screen.getByRole("button", { name: "Switch account" }));
      await user.type(await screen.findByLabelText("Kirish kodi"), "765432");
      await user.click(screen.getByRole("button", { name: "Kirish" }));
      await loginStarted;

      useAuthStore.getState().setTokens(switchedTokens);
      resolveLogin();

      await waitFor(() => expect(useAuthStore.getState().accessToken).toBe(switchedTokens.access_token));
      expect(useAuthStore.getState().userId).toBe("99");
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    } finally {
      resolveLogin();
      axios.defaults.adapter = originalAxiosAdapter;
    }
  });
});
