import axios, { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { Address, CheckoutQuote, Page, Product, Profile } from "@/types/api";
import { FavoriteButton } from "@/components/storefront/FavoriteButton";
import { AddressesPage } from "@/pages/AddressesPage";
import { CheckoutPage } from "@/pages/CheckoutPage";
import { FavoritesPage } from "@/pages/FavoritesPage";
import { ProfilePage } from "@/pages/ProfilePage";

const initialProfile: Profile = {
  display_name: "Madina Karimova",
  phone: "+998901234567",
  language: "uz",
};

const savedAddress: Address = {
  id: 7,
  label: "Uy",
  address_text: "Toshkent, Amir Temur ko‘chasi 10",
  address_comment: "2-qavat, 14-xonadon",
  is_default: true,
};

const product: Product = {
  id: 18,
  category_id: 2,
  name_uz: "Serverdan kelgan daftar",
  name_ru: "Тетрадь с сервера",
  description_uz: null,
  description_ru: null,
  sku: "NB-18",
  price: "12000.00",
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

const readyQuote: CheckoutQuote = {
  subtotal: "12000.00",
  delivery_fee: "0.00",
  total: "12000.00",
  payment_methods: ["cash"],
  ready: true,
  reasons: [],
  quote_fingerprint: "confirmed-quote",
};

function jwt(sub: number): string {
  const payload = btoa(JSON.stringify({ sub: String(sub) }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `e30.${payload}.signature`;
}

function signedIn(sub = 42): void {
  useAuthStore.getState().setTokens({
    access_token: jwt(sub),
    refresh_token: `refresh-${sub}`,
    is_admin: false,
  });
}

function response<T>(config: Parameters<AxiosAdapter>[0], data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: new AxiosHeaders(), config };
}

function apiError(config: Parameters<AxiosAdapter>[0], status: number, code: string): Promise<never> {
  const errorResponse = response(config, { error: { code, message: code, details: {} } }, status);
  return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse));
}

function requestPayload(config: Parameters<AxiosAdapter>[0]): Record<string, unknown> {
  return typeof config.data === "string"
    ? JSON.parse(config.data) as Record<string, unknown>
    : config.data as Record<string, unknown>;
}

function page<T>(items: T[]): Page<T> {
  return { items, total: items.length, page: 1, limit: 24, total_pages: 1 };
}

let originalApiAdapter: typeof api.defaults.adapter;
let originalAxiosAdapter: typeof axios.defaults.adapter;
afterEach(() => {
  if (originalApiAdapter !== undefined) api.defaults.adapter = originalApiAdapter;
  if (originalAxiosAdapter !== undefined) axios.defaults.adapter = originalAxiosAdapter;
  originalApiAdapter = undefined;
  originalAxiosAdapter = undefined;
});

describe("customer profile, favorites and addresses", () => {
  it("keeps profile drafts after a recoverable error and sends only editable profile fields", async () => {
    signedIn();
    originalApiAdapter = api.defaults.adapter;
    let patch: Record<string, unknown> | null = null;
    api.defaults.adapter = async (config) => {
      if (config.url === "/profile" && config.method === "get") return response(config, initialProfile);
      if (config.url === "/profile" && config.method === "patch") {
        patch = requestPayload(config);
        return apiError(config, 403, "PROFILE_FORBIDDEN");
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<ProfilePage />, "/profile", true);
    const name = await screen.findByLabelText("Ism familiya");
    await user.clear(name);
    await user.type(name, "Draft name");
    await user.clear(screen.getByLabelText("Telefon raqami"));
    await user.type(screen.getByLabelText("Telefon raqami"), "+998911234567");
    await user.selectOptions(screen.getByLabelText("Til"), "ru");
    await user.click(screen.getByRole("button", { name: "Saqlash" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(name).toHaveValue("Draft name");
    expect(screen.getByLabelText("Telefon raqami")).toHaveValue("+998911234567");
    expect(screen.getByLabelText("Til")).toHaveValue("ru");
    expect(screen.queryByLabelText(/Telegram ID|Telegram foydalanuvchi nomi|Admin|Rol/i)).not.toBeInTheDocument();
    expect(patch).toEqual({ display_name: "Draft name", phone: "+998911234567", language: "ru" });
  });

  it("queues one guest favorite for login, ignores a second action, then sends the first exactly once", async () => {
    originalApiAdapter = api.defaults.adapter;
    originalAxiosAdapter = axios.defaults.adapter;
    const favoriteAdds: number[] = [];
    api.defaults.adapter = async (config) => {
      if (config.url?.startsWith("/favorites/") && config.method === "get") {
        return response(config, { is_favorite: false });
      }
      if (config.url?.startsWith("/favorites/") && config.method === "put") {
        favoriteAdds.push(Number(config.url.split("/").at(-1)));
        return response(config, null, 204);
      }
      throw new Error(`Unexpected API request: ${config.method} ${config.url}`);
    };
    axios.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/auth/customer/code")) {
        return response(config, {
          access_token: jwt(42),
          refresh_token: "refresh-42",
          token_type: "bearer",
          is_admin: false,
        });
      }
      throw new Error(`Unexpected auth request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(
      <>
        <FavoriteButton productId={18} productName="Birinchi mahsulot" />
        <FavoriteButton productId={19} productName="Ikkinchi mahsulot" />
      </>,
      "/product/18",
      true,
    );
    const favoriteButtons = await screen.findAllByRole("button", { name: /Sevimlilar/ });
    await user.click(favoriteButtons[0]!);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("kans-shop-pending-add") ?? "null")).toMatchObject({
      kind: "favorite_add",
      productId: 18,
    });

    await user.click(favoriteButtons[1]!);
    expect(JSON.parse(localStorage.getItem("kans-shop-pending-add") ?? "null")).toMatchObject({
      kind: "favorite_add",
      productId: 18,
    });
    await user.type(screen.getByLabelText("Kirish kodi"), "123456");
    await user.click(screen.getByRole("button", { name: "Kirish" }));

    await waitFor(() => expect(favoriteAdds).toEqual([18]));
    expect(localStorage.getItem("kans-shop-pending-add")).toBeNull();
  });

  it("discards a pending guest favorite when login is cancelled", async () => {
    originalApiAdapter = api.defaults.adapter;
    let favoriteAdds = 0;
    api.defaults.adapter = async (config) => {
      if (config.url?.startsWith("/favorites/") && config.method === "put") favoriteAdds += 1;
      throw new Error(`Unexpected API request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<FavoriteButton productId={18} productName="Daftar" />, "/product/18", true);
    await user.click(await screen.findByRole("button", { name: /Sevimlilar/ }));
    await user.click(screen.getByRole("button", { name: "Bekor qilish" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(localStorage.getItem("kans-shop-pending-add")).toBeNull();
    expect(favoriteAdds).toBe(0);
  });

  it("retains an address draft after a recoverable API error and can retry it", async () => {
    signedIn();
    originalApiAdapter = api.defaults.adapter;
    let createAttempts = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/addresses" && config.method === "get") return response(config, []);
      if (config.url === "/addresses" && config.method === "post") {
        createAttempts += 1;
        if (createAttempts === 1) return apiError(config, 403, "ADDRESS_FORBIDDEN");
        return response(config, { id: 8, ...requestPayload(config), is_default: true }, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<AddressesPage />, "/profile/addresses", true);
    await user.click(await screen.findByRole("button", { name: "Manzil qo‘shish" }));
    const dialog = screen.getByRole("dialog", { name: "Manzil qo‘shish" });
    await user.type(within(dialog).getByLabelText("Manzil nomi"), "Uy");
    await user.type(within(dialog).getByLabelText("Manzil matni"), "Toshkent, test manzili");
    await user.click(within(dialog).getByRole("button", { name: "Saqlash" }));

    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Manzil nomi")).toHaveValue("Uy");
    expect(within(dialog).getByLabelText("Manzil matni")).toHaveValue("Toshkent, test manzili");
    await user.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(createAttempts).toBe(2));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("renders the favorites returned by the server and removes a favorite through its API", async () => {
    signedIn();
    originalApiAdapter = api.defaults.adapter;
    let favoriteItems = [product];
    let deletes = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/favorites" && config.method === "get") return response(config, page(favoriteItems));
      if (config.url === "/favorites/18" && config.method === "get") return response(config, { is_favorite: true });
      if (config.url === "/favorites/18" && config.method === "delete") {
        deletes += 1;
        favoriteItems = [];
        return response(config, null, 204);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<FavoritesPage />, "/favorites", true);
    expect(await screen.findByText("Serverdan kelgan daftar")).toBeInTheDocument();
    const remove = await screen.findByRole("button", { name: /Sevimlilar/ });
    expect(remove).toHaveAttribute("aria-pressed", "true");
    await user.click(remove);

    await waitFor(() => expect(deletes).toBe(1));
    await waitFor(() => expect(screen.queryByText("Serverdan kelgan daftar")).not.toBeInTheDocument());
  });

  it("validates address lengths and performs add, edit, default and delete with the address-book contract", async () => {
    signedIn();
    originalApiAdapter = api.defaults.adapter;
    const addresses: Address[] = [{ ...savedAddress }];
    const requests: Array<{ method: string; url: string; payload?: Record<string, unknown> }> = [];
    api.defaults.adapter = async (config) => {
      const method = (config.method ?? "get").toLowerCase();
      if (config.url === "/addresses" && method === "get") return response(config, addresses);
      requests.push({ method, url: config.url ?? "", ...(config.data ? { payload: requestPayload(config) } : {}) });
      if (config.url === "/addresses" && method === "post") {
        const created = { id: 8, ...requestPayload(config), address_comment: "Darvoza yonida", is_default: false } as Address;
        addresses.push(created);
        return response(config, created, 201);
      }
      if (config.url === "/addresses/8" && method === "patch") {
        const updated = { ...addresses.find(({ id }) => id === 8)!, ...requestPayload(config) } as Address;
        addresses[addresses.findIndex(({ id }) => id === 8)] = updated;
        return response(config, updated);
      }
      if (config.url === "/addresses/8/default" && method === "put") {
        const updated = { ...addresses.find(({ id }) => id === 8)!, is_default: true };
        addresses.splice(0, addresses.length, ...addresses.map((item) => ({ ...item, is_default: item.id === 8 })));
        return response(config, updated);
      }
      if (config.url === "/addresses/8" && method === "delete") {
        addresses.splice(addresses.findIndex(({ id }) => id === 8), 1);
        return response(config, null, 204);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<AddressesPage />, "/profile/addresses", true);
    await user.click(await screen.findByRole("button", { name: "Manzil qo‘shish" }));
    const dialog = screen.getByRole("dialog", { name: "Manzil qo‘shish" });
    expect(within(dialog).getByLabelText("Manzil nomi")).toHaveAttribute("maxLength", "60");
    expect(within(dialog).getByLabelText("Manzil matni")).toHaveAttribute("maxLength", "1000");
    expect(within(dialog).getByLabelText("Qo‘shimcha izoh")).toHaveAttribute("maxLength", "500");
    await user.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    expect(await within(dialog).findByText("Manzil nomini kiriting")).toBeInTheDocument();
    expect(requests.filter(({ method }) => method === "post")).toHaveLength(0);

    await user.type(within(dialog).getByLabelText("Manzil nomi"), "Ishxona");
    await user.type(within(dialog).getByLabelText("Manzil matni"), "Toshkent, Mustaqillik ko‘chasi 5");
    await user.type(within(dialog).getByLabelText("Qo‘shimcha izoh"), "Darvoza yonida");
    await user.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await screen.findByRole("button", { name: "Tahrirlash: Ishxona" });
    expect(requests.find(({ method }) => method === "post")?.payload).toEqual({
      label: "Ishxona",
      address_text: "Toshkent, Mustaqillik ko‘chasi 5",
      address_comment: "Darvoza yonida",
    });

    await user.click(screen.getByRole("button", { name: "Asosiy qilib belgilash: Ishxona" }));
    await waitFor(() => expect(requests.some(({ method, url }) => method === "put" && url === "/addresses/8/default")).toBe(true));
    await user.click(screen.getByRole("button", { name: "Tahrirlash: Ishxona" }));
    const editDialog = screen.getByRole("dialog", { name: "Manzilni tahrirlash" });
    await user.clear(within(editDialog).getByLabelText("Manzil matni"));
    await user.type(within(editDialog).getByLabelText("Manzil matni"), "Yangi matn");
    await user.click(within(editDialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(requests.find(({ method, url }) => method === "patch" && url === "/addresses/8")?.payload).toEqual({
      label: "Ishxona",
      address_text: "Yangi matn",
      address_comment: "Darvoza yonida",
    }));
    await user.click(screen.getByRole("button", { name: "O‘chirish: Ishxona" }));
    await waitFor(() => expect(requests.some(({ method, url }) => method === "delete" && url === "/addresses/8")).toBe(true));
  });

  it("prefills checkout from profile and sends the confirmed address snapshot without IDs or coordinates", async () => {
    signedIn();
    originalApiAdapter = api.defaults.adapter;
    const orderRequests: Record<string, unknown>[] = [];
    const addressRequests: Array<Record<string, unknown>> = [];
    api.defaults.adapter = async (config) => {
      if (config.url === "/profile" && config.method === "get") return response(config, initialProfile);
      if (config.url === "/addresses" && config.method === "get") return response(config, [savedAddress]);
      if (config.url === "/addresses" && config.method === "post") {
        addressRequests.push(requestPayload(config));
        return response(config, { ...savedAddress, id: 8, ...requestPayload(config) }, 201);
      }
      if (config.url === "/cart") {
        return response(config, {
          items: [{ id: 1, product_id: product.id, quantity: 1, price_snapshot: product.price, product }],
          subtotal: product.price,
          items_count: 1,
        });
      }
      if (config.url === "/settings/public") {
        return response(config, {
          delivery_fee: null,
          free_delivery_from: null,
          min_order_amount: null,
          work_hours: null,
          card_number: null,
          card_holder: null,
          support_username: null,
          shop_phone: null,
          is_shop_open: true,
          welcome_text_uz: null,
          welcome_text_ru: null,
          enabled_payment_providers: [],
        });
      }
      if (config.url === "/orders/quote") return response(config, readyQuote);
      if (config.url === "/orders" && config.method === "post") {
        orderRequests.push(requestPayload(config));
        return response(config, {
          id: 99,
          order_number: "KANS-000099",
          status: "new",
          order_type: "delivery",
          customer_name: "Madina Karimova",
          customer_phone: "+998901234567",
          address: savedAddress.address_text,
          address_comment: savedAddress.address_comment,
          comment: null,
          subtotal: readyQuote.subtotal,
          delivery_fee: readyQuote.delivery_fee,
          discount: "0.00",
          total: readyQuote.total,
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
        }, 201);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    const rendered = renderWithProviders(<CheckoutPage />, "/checkout", true);
    expect(await screen.findByLabelText("Ismingiz")).toHaveValue("Madina Karimova");
    expect(screen.getByLabelText("Telefon raqamingiz")).toHaveValue("+998901234567");
    await user.selectOptions(await screen.findByLabelText("Saqlangan manzil"), "7");
    const confirmedAddressText = "Toshkent, Amir Temur ko‘chasi 10";
    expect(screen.getByLabelText("Manzil")).toHaveValue(confirmedAddressText);
    expect(screen.getByLabelText("Manzilga izoh")).toHaveValue("2-qavat, 14-xonadon");
    rendered.queryClient.setQueryData(["addresses", "42"], [{
      ...savedAddress,
      address_text: "Boshqa tabda yangilangan manzil",
      address_comment: "Yangi izoh",
    }]);
    expect(screen.getByLabelText("Manzil")).toHaveValue(confirmedAddressText);
    expect(screen.getByLabelText("Manzilga izoh")).toHaveValue("2-qavat, 14-xonadon");

    await user.type(screen.getByLabelText("Saqlanadigan manzil nomi"), "Ishxona");
    await user.click(screen.getByRole("button", { name: "Keyingi safar uchun saqlash" }));
    await waitFor(() => expect(addressRequests).toEqual([{
      label: "Ishxona",
      address_text: confirmedAddressText,
      address_comment: "2-qavat, 14-xonadon",
    }]));
    expect(screen.getByLabelText("Manzil")).toHaveValue(confirmedAddressText);

    await user.click(screen.getByRole("button", { name: "Buyurtmani tasdiqlash" }));
    await waitFor(() => expect(orderRequests).toHaveLength(1));
    expect(orderRequests[0]).toMatchObject({ address: confirmedAddressText, address_comment: "2-qavat, 14-xonadon" });
    expect(orderRequests[0]).not.toHaveProperty("address_id");
    expect(orderRequests[0]).not.toHaveProperty("latitude");
    expect(orderRequests[0]).not.toHaveProperty("longitude");
  });

  it("test_customer_cache_isolated_after_account_switch", async () => {
    signedIn(42);
    originalApiAdapter = api.defaults.adapter;
    let releaseOldProfile!: () => void;
    let oldProfileStarted!: () => void;
    const oldProfileGate = new Promise<void>((resolve) => { releaseOldProfile = resolve; });
    const oldRequestStarted = new Promise<void>((resolve) => { oldProfileStarted = resolve; });
    api.defaults.adapter = async (config) => {
      if (config.url === "/profile" && config.method === "get") {
        const authorization = String(config.headers.get("Authorization"));
        if (authorization.includes(jwt(42))) {
          oldProfileStarted();
          await oldProfileGate;
          return response(config, { ...initialProfile, display_name: "Old account" });
        }
        return response(config, { ...initialProfile, display_name: "New account" });
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const rendered = renderWithProviders(<ProfilePage />, "/profile", true);
    rendered.queryClient.setQueryData(["profile", "42"], initialProfile);
    rendered.queryClient.setQueryData(["addresses", "42"], [savedAddress]);
    rendered.queryClient.setQueryData(["favorites", "42", 1], page([product]));
    rendered.queryClient.setQueryData(["favorite-state", "42", 18], { is_favorite: true });
    const user = userEvent.setup();

    await oldRequestStarted;
    const name = await screen.findByLabelText("Ism familiya");
    await user.clear(name);
    await user.type(name, "Unsent old-account draft");
    signedIn(43);
    await waitFor(() => expect(screen.getByLabelText("Ism familiya")).toHaveValue("New account"));
    releaseOldProfile();
    await waitFor(() => {
      expect(rendered.queryClient.getQueryData(["profile", "42"])).toBeUndefined();
      expect(rendered.queryClient.getQueryData(["addresses", "42"])).toBeUndefined();
      expect(rendered.queryClient.getQueryData(["favorites", "42", 1])).toBeUndefined();
      expect(rendered.queryClient.getQueryData(["favorite-state", "42", 18])).toBeUndefined();
    });
    expect(rendered.queryClient.getQueryData<Profile>(["profile", "43"])?.display_name).toBe("New account");
    await user.click(screen.getByRole("button", { name: "Chiqish" }));
    await waitFor(() => expect(rendered.queryClient.getQueryData(["profile", "43"])).toBeUndefined());
    expect(screen.getByRole("button", { name: "Kirish" })).toBeInTheDocument();
  });
});
