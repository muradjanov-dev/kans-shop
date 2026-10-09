import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { CheckoutPage } from "@/pages/CheckoutPage";
import { api } from "@/lib/api";
import { formatExactPrice } from "@/lib/format";
import { renderWithProviders } from "@/test/renderWithProviders";
import { useAuthStore } from "@/store/auth";
import type { Cart, CheckoutQuote, Order, Product, PublicSettings } from "@/types/api";

const cart: Cart = {
  items: [],
  subtotal: "1000.00",
  items_count: 0,
};

const readyQuote: CheckoutQuote = {
  subtotal: "1000.00",
  delivery_fee: "0.01",
  total: "1000.01",
  payment_methods: ["cash", "card_transfer", "tender"],
  ready: true,
  reasons: [],
  quote_fingerprint: "quote-a",
};

const settings: PublicSettings = {
  delivery_fee: 999999,
  free_delivery_from: null,
  min_order_amount: null,
  work_hours: null,
  card_number: "must-not-be-used",
  card_holder: "must-not-be-used",
  support_username: null,
  shop_phone: null,
  is_shop_open: true,
  welcome_text_uz: null,
  welcome_text_ru: null,
  enabled_payment_providers: [],
};

const order: Order = {
  id: 81,
  order_number: "KANS-000081",
  status: "new",
  order_type: "delivery",
  customer_name: "Ali",
  customer_phone: "+998901234567",
  address: "Tashkent",
  address_comment: null,
  comment: null,
  subtotal: "1000.00",
  delivery_fee: "0.01",
  discount: "0.00",
  total: "1000.01",
  payment_method: "cash",
  payment_status: "pending",
  payment_instructions: null,
  receipt_version: 0,
  has_receipt: false,
  receipt_url: null,
  cancel_reason: null,
  created_at: "2026-10-09T00:00:00Z",
  confirmed_at: null,
  completed_at: null,
  cancelled_at: null,
  items: [],
};
const onlineOrder: Order = { ...order, payment_method: "click" };

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

function requestPayload(config: Parameters<AxiosAdapter>[0]): Record<string, string> {
  return typeof config.data === "string"
    ? JSON.parse(config.data) as Record<string, string>
    : config.data as Record<string, string>;
}

const pricedProduct: Product = {
  id: 1,
  category_id: 2,
  name_uz: "Daftar",
  name_ru: "Тетрадь",
  description_uz: null,
  description_ru: null,
  sku: "NB-1",
  price: "100.00",
  old_price: null,
  stock_qty: 12,
  unit: "dona",
  min_order_qty: 1,
  is_active: true,
  is_featured: false,
  lot_url: "https://lots.invalid/1",
  views_count: 0,
  sold_count: 0,
  images: [],
};

function cartAtPrice(price: string): Cart {
  return {
    items: [{
      id: 7,
      product_id: pricedProduct.id,
      quantity: 1,
      price_snapshot: price,
      product: { ...pricedProduct, price },
    }],
    subtotal: price,
    items_count: 1,
  };
}

function apiError(config: Parameters<AxiosAdapter>[0], code: string, status = 409): Promise<never> {
  const errorResponse = response(config, {
    error: { code, message: code, details: {} },
  }, status);
  return Promise.reject(
    new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse),
  );
}

function signedIn(): void {
  useAuthStore.getState().setTokens({
    access_token: jwt(42),
    refresh_token: "refresh-42",
    is_admin: false,
  });
}

async function fillDeliveryForm(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(await screen.findByLabelText("Ismingiz"), "Ali");
  await user.type(await screen.findByLabelText("Telefon raqamingiz"), "+998901234567");
  await user.type(await screen.findByLabelText("Manzil"), "Tashkent");
}

let originalAdapter: typeof api.defaults.adapter;
afterEach(() => {
  if (originalAdapter !== undefined) api.defaults.adapter = originalAdapter;
  originalAdapter = undefined;
  sessionStorage.clear();
});

describe("exact server money formatting", () => {
  it("preserves cents and groups large integer strings without floating-point conversion", () => {
    expect(formatExactPrice("20.01")).toBe("20.01");
    expect(formatExactPrice("1000.00")).toBe("1 000");
    expect(formatExactPrice("123456789012345678901.09")).toBe("123 456 789 012 345 678 901.09");
    expect(formatExactPrice("invalid")).toBe("—");
  });
});

describe("quote-based checkout flow", () => {
  it("keeps submit disabled while the server quote is loading, then blocks an unavailable quote", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    let releaseQuote!: () => void;
    const quoteResponse = new Promise<void>((resolve) => { releaseQuote = resolve; });
    const user = userEvent.setup();
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") {
        await quoteResponse;
        return response(config, { ...readyQuote, ready: false, reasons: ["shop_closed"], total: null, quote_fingerprint: null });
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    await fillDeliveryForm(user);

    expect(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" })).toBeDisabled();
    releaseQuote();
    expect(await screen.findByRole("button", { name: "Buyurtmani tasdiqlash" })).toBeDisabled();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("validates fields on blur and derives the submitted money and checkout key from the quote", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const requests: Array<{ payload: Record<string, unknown>; key: string | undefined }> = [];
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") return response(config, readyQuote);
      if (config.url === "/orders" && config.method === "post") {
        requests.push({ payload: requestPayload(config), key: String(config.headers.get("Idempotency-Key")) });
        return response(config, order, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    const name = await screen.findByLabelText("Ismingiz");
    await user.click(name);
    await user.tab();
    expect(await screen.findByText("Ismingizni kiriting")).toBeInTheDocument();
    await user.type(name, "Ali");
    await user.type(screen.getByPlaceholderText("+998901234567"), "+998901234567");
    await user.type(await screen.findByLabelText("Manzil"), "Tashkent");

    expect(screen.getByText(/1 000\.01/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Buyurtmani tasdiqlash" }));
    await waitFor(() => expect(requests).toHaveLength(1));

    expect(requests[0]?.payload).toMatchObject({
      purchase_contract_version: 1,
      expected_total: "1000.01",
      expected_quote: "quote-a",
    });
    expect(requests[0]?.key).toMatch(/^[0-9a-f-]{36}$/i);
    expect(screen.queryByText("must-not-be-used")).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /KANS-000081/i })).toHaveAttribute("href", "/orders/81");
  });

  it("retries a lost response with the same key and freezes edited fields until the outcome is known", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const keys: string[] = [];
    let checkoutCalls = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") return response(config, readyQuote);
      if (config.url === "/orders" && config.method === "post") {
        checkoutCalls += 1;
        keys.push(String(config.headers.get("Idempotency-Key")));
        if (checkoutCalls === 1) throw new AxiosError("connection lost", "ERR_NETWORK", config);
        return response(config, order, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    await fillDeliveryForm(user);
    await user.click(await screen.findByRole("button", { name: "Buyurtmani tasdiqlash" }));

    const retry = await screen.findByRole("button", { name: "Qayta urinish" });
    expect(screen.getByLabelText("Telefon raqamingiz")).toBeDisabled();
    const recoveryData = sessionStorage.getItem("kans-checkout-recovery:42");
    expect(recoveryData).toBeTruthy();
    expect(recoveryData).not.toMatch(/Ali|998901234567|Tashkent/);
    await user.click(retry);

    expect(await screen.findByRole("link", { name: /KANS-000081/i })).toHaveAttribute("href", "/orders/81");
    expect(checkoutCalls).toBe(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("shows order recovery after reload without restoring form data or resubmitting", async () => {
    signedIn();
    sessionStorage.setItem("kans-checkout-recovery:42", JSON.stringify({
      checkoutKey: "opaque-key",
      quoteFingerprint: "quote-a",
      attemptId: "opaque-attempt",
    }));
    originalAdapter = api.defaults.adapter;
    let orderPosts = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, cart);
      if (config.url === "/orders" && config.method === "post") orderPosts += 1;
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    renderWithProviders(<CheckoutPage />, "/checkout", true);

    expect(await screen.findByRole("alert")).toHaveTextContent("Avvalgi buyurtma urinishi yakunlanmadi.");
    expect(screen.getByRole("link", { name: "Buyurtmalar" })).toHaveAttribute("href", "/orders");
    expect(screen.queryByLabelText("Ismingiz")).not.toBeInTheDocument();
    expect(orderPosts).toBe(0);
  });

  it("requires renewed confirmation for a changed quote even when the total is unchanged", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const firstKey: string[] = [];
    const submittedQuotes: string[] = [];
    let quoteRequests = 0;
    let checkoutCalls = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") {
        quoteRequests += 1;
        return response(config, quoteRequests === 1 ? readyQuote : { ...readyQuote, quote_fingerprint: "quote-b" });
      }
      if (config.url === "/orders" && config.method === "post") {
        checkoutCalls += 1;
        firstKey.push(String(config.headers.get("Idempotency-Key")));
        submittedQuotes.push(requestPayload(config).expected_quote!);
        if (checkoutCalls === 1) return apiError(config, "QUOTE_CHANGED");
        return response(config, order, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    await fillDeliveryForm(user);
    await user.click(await screen.findByRole("button", { name: "Buyurtmani tasdiqlash" }));
    await user.click(await screen.findByRole("button", { name: "Yangi summani tasdiqlash" }));

    expect(await screen.findByRole("link", { name: /KANS-000081/i })).toBeInTheDocument();
    expect(submittedQuotes).toEqual(["quote-a", "quote-b"]);
    expect(firstKey[0]).not.toBe(firstKey[1]);
  });

  it("keeps the created order and retries a failed payment link against that same order", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    let orderPosts = 0;
    const payRequests: Array<{ url: string | undefined; provider: string }> = [];
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") return response(config, { ...readyQuote, payment_methods: ["cash", "click"] });
      if (config.url === "/orders" && config.method === "post") {
        orderPosts += 1;
        return response(config, onlineOrder, 201);
      }
      if (config.url === "/orders/81/pay" && config.method === "post") {
        payRequests.push({ url: config.url, provider: requestPayload(config).provider! });
        if (payRequests.length === 1) return apiError(config, "PAY_LINK_TEMPORARY_FAILURE", 503);
        return response(config, { payment_url: "https://pay.invalid/order-81" });
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    await fillDeliveryForm(user);
    await user.click(await screen.findByRole("button", { name: "Click" }));
    await user.click(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("To'lov havolasini olib bo'lmadi");
    expect(screen.getByRole("link", { name: /KANS-000081/ })).toHaveAttribute("href", "/orders/81");
    await user.click(screen.getByRole("button", { name: "To'lov havolasini qayta olish" }));

    expect(await screen.findByRole("button", { name: "To'lovga o'tish" })).toBeInTheDocument();
    expect(orderPosts).toBe(1);
    expect(payRequests).toEqual([
      { url: "/orders/81/pay", provider: "click" },
      { url: "/orders/81/pay", provider: "click" },
    ]);
    expect(screen.getByText("To'lov kutilmoqda")).toBeInTheDocument();
  });

  it.each(["UNSUPPORTED_PURCHASE_CONTRACT_VERSION", "CLIENT_UPDATE_REQUIRED"]) (
    "surfaces %s without creating a success state",
    async (code) => {
      signedIn();
      originalAdapter = api.defaults.adapter;
      const keys: string[] = [];
      api.defaults.adapter = async (config) => {
        if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
        if (config.url === "/settings/public") return response(config, settings);
        if (config.url === "/orders/quote") return response(config, readyQuote);
        if (config.url === "/orders" && config.method === "post") {
          keys.push(String(config.headers.get("Idempotency-Key")));
          return apiError(config, code, 422);
        }
        throw new Error(`Unexpected request: ${config.method} ${config.url}`);
      };
      const user = userEvent.setup();

      renderWithProviders(<CheckoutPage />, "/checkout", true);
      await fillDeliveryForm(user);
      await user.click(await screen.findByRole("button", { name: "Buyurtmani tasdiqlash" }));

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.queryByText(/KANS-000081/)).not.toBeInTheDocument();
      const name = screen.getByLabelText("Ismingiz");
      await user.clear(name);
      await user.type(name, "Madina");
      await user.click(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" }));
      await waitFor(() => expect(keys).toHaveLength(2));
      expect(keys[0]).not.toBe(keys[1]);
    },
  );

  it("uses only quote-enabled payment methods and omits address, payment, and delivery fee for preorder", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const quoteRequests: Array<Record<string, string>> = [];
    const checkoutRequests: Array<Record<string, string>> = [];
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, { ...cart, items_count: 1, items: [{ id: 1, product_id: 1, quantity: 1, price_snapshot: "1000", product: {} }] });
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") {
        const payload = requestPayload(config);
        quoteRequests.push(payload);
        return response(config, {
          ...readyQuote,
          delivery_fee: payload.order_type === "preorder" ? null : "0.01",
          payment_methods: ["cash", "card_transfer", "tender"],
          reasons: payload.payment_method === "tender" ? ["Some tender lots have no link."] : [],
        });
      }
      if (config.url === "/orders" && config.method === "post") {
        checkoutRequests.push(requestPayload(config));
        return response(config, { ...order, order_type: "preorder", address: null, address_comment: null }, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    await screen.findByLabelText("Ismingiz");
    expect(screen.queryByRole("button", { name: "Payme" })).not.toBeInTheDocument();
    await fillDeliveryForm(user);
    await user.click(screen.getByRole("button", { name: "Tender (lot)" }));
    expect(await screen.findByText("Some tender lots have no link.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" })).toBeEnabled();
    expect(screen.getByText("Some tender lots have no link.")).toHaveAttribute("role", "note");

    await user.click(screen.getByRole("button", { name: "Olib ketish" }));
    await waitFor(() => expect(quoteRequests.at(-1)?.order_type).toBe("pickup"));
    expect(screen.queryByLabelText("Manzil")).not.toBeInTheDocument();
    expect(screen.queryByText("Yetkazib berish narxi")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Oldindan buyurtma" }));

    await waitFor(() => expect(quoteRequests.at(-1)?.order_type).toBe("preorder"));
    expect(screen.queryByLabelText("Manzil")).not.toBeInTheDocument();
    expect(screen.queryByText("To'lov usuli")).not.toBeInTheDocument();
    expect(screen.queryByText("Yetkazib berish narxi")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" }));
    await screen.findByRole("link", { name: /KANS-000081/ });
    expect(checkoutRequests[0]).toMatchObject({
      order_type: "preorder",
      payment_method: "cash",
      address: null,
      address_comment: null,
    });
  });

  it("disables checkout when a ready quote omits the selected method, including preorder's cash placeholder", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const quoteRequests: Array<Record<string, string>> = [];
    let orderPosts = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, cartAtPrice("1000.00"));
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") {
        const payload = requestPayload(config);
        quoteRequests.push(payload);
        return response(config, {
          ...readyQuote,
          ready: true,
          payment_methods: payload.order_type === "preorder" ? ["tender"] : [],
        });
      }
      if (config.url === "/orders" && config.method === "post") {
        orderPosts += 1;
        return response(config, order, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<CheckoutPage />, "/checkout", true);
    await fillDeliveryForm(user);
    await waitFor(() => expect(quoteRequests).toHaveLength(1));
    expect(quoteRequests[0]).toMatchObject({ order_type: "delivery", payment_method: "cash" });
    expect(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Olib ketish" }));
    await waitFor(() => expect(quoteRequests).toHaveLength(2));
    expect(quoteRequests[1]).toMatchObject({ order_type: "pickup", payment_method: "cash" });
    expect(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Oldindan buyurtma" }));
    await waitFor(() => expect(quoteRequests).toHaveLength(3));
    expect(quoteRequests[2]).toMatchObject({ order_type: "preorder", payment_method: "cash" });
    expect(screen.queryByText("To'lov usuli")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Bu buyurtma uchun to'lov usuli mavjud emas.");
    expect(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" })).toBeDisabled();
    expect(orderPosts).toBe(0);
  });

  it("fetches a fresh quote when cart price and subtotal change with the same product and quantity", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    let cartVersion = 0;
    let quoteCalls = 0;
    let releaseUpdatedQuote!: () => void;
    let startUpdatedQuote!: () => void;
    const updatedQuoteGate = new Promise<void>((resolve) => { releaseUpdatedQuote = resolve; });
    const updatedQuoteStarted = new Promise<void>((resolve) => { startUpdatedQuote = resolve; });
    api.defaults.adapter = async (config) => {
      if (config.url === "/cart") return response(config, cartVersion === 0 ? cartAtPrice("100.00") : cartAtPrice("101.00"));
      if (config.url === "/settings/public") return response(config, settings);
      if (config.url === "/orders/quote") {
        quoteCalls += 1;
        if (quoteCalls === 1) return response(config, { ...readyQuote, subtotal: "100.00", total: "100.00" });
        startUpdatedQuote();
        await updatedQuoteGate;
        return response(config, {
          ...readyQuote,
          subtotal: "101.00",
          total: "101.00",
          quote_fingerprint: "price-changed-quote",
        });
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();
    const rendered = renderWithProviders(<CheckoutPage />, "/checkout", true);

    await fillDeliveryForm(user);
    const submit = await screen.findByRole("button", { name: "Buyurtmani tasdiqlash" });
    await waitFor(() => expect(quoteCalls).toBe(1));
    expect(submit).toBeEnabled();

    cartVersion = 1;
    rendered.queryClient.setQueryData(["cart", "42"], cartAtPrice("101.00"));
    await updatedQuoteStarted;
    expect(quoteCalls).toBe(2);
    expect(submit).toBeDisabled();
    releaseUpdatedQuote();

    await waitFor(() => expect(submit).toBeEnabled());
    expect(screen.getAllByText(/101/)).toHaveLength(2);
  });
});
