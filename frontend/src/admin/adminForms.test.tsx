import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AdminAuthProvider } from "@/admin/AdminAuthProvider";
import { adminApi, setAdminCsrfToken } from "@/admin/api";
import { CatalogPage } from "@/admin/pages/CatalogPage";
import { BroadcastsPage } from "@/admin/pages/BroadcastsPage";
import { SettingsPage } from "@/admin/pages/SettingsPage";
import { adminRouteRegistry } from "@/admin/adminRoutes";

const originalAdapter = adminApi.defaults.adapter;
const route = (id: "catalog" | "settings" | "broadcasts") => adminRouteRegistry.find((entry) => entry.id === id)!;

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

function renderPage(page: React.ReactNode, path = "/admin") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}><AdminAuthProvider>{page}</AdminAuthProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

function conflict(config: Parameters<AxiosAdapter>[0]) {
  return new AxiosError("Conflict", "ERR_BAD_REQUEST", config, undefined, {
    config, data: { error: { code: "ENTITY_CONFLICT", message: "This record changed." } },
    status: 409, statusText: "Conflict", headers: new AxiosHeaders(),
  });
}

describe("admin forms use the versioned REST contracts", () => {
  afterEach(() => {
    adminApi.defaults.adapter = originalAdapter;
    setAdminCsrfToken(null);
  });

  it("keeps a settings draft after a conflict and only refreshes on request", async () => {
    const user = userEvent.setup();
    let settingsReads = 0;
    let firstSave = true;
    const settingsWrites: Array<Record<string, unknown>> = [];
    adminApi.defaults.adapter = async (config) => {
      if (config.url === "/auth/admin/session") return response(config, { admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" });
      if (config.url === "/admin/settings" && config.method === "get") {
        settingsReads += 1;
        return response(config, {
          version: settingsReads === 1 ? 1 : 2,
          delivery_fee: null, free_delivery_from: null, min_order_amount: null,
          work_hours: null, card_number: null, card_holder: null, support_username: null,
          shop_phone: null, is_shop_open: null, welcome_text_uz: null, welcome_text_ru: null,
          readiness: { delivery_fee: false, free_delivery_from: false, min_order_amount: false, work_hours: false, card_number: false, card_holder: false, support_username: false, shop_phone: false, is_shop_open: false, welcome_text_uz: false, welcome_text_ru: false },
        });
      }
      if (config.url === "/admin/settings" && config.method === "patch" && firstSave) {
        settingsWrites.push(typeof config.data === "string" ? JSON.parse(config.data) as Record<string, unknown> : config.data as Record<string, unknown>);
        firstSave = false;
        throw conflict(config);
      }
      if (config.url === "/admin/settings" && config.method === "patch") {
        settingsWrites.push(typeof config.data === "string" ? JSON.parse(config.data) as Record<string, unknown> : config.data as Record<string, unknown>);
        return response(config, {
          version: 3, delivery_fee: "15000", free_delivery_from: null, min_order_amount: null,
          work_hours: null, card_number: null, card_holder: null, support_username: null,
          shop_phone: null, is_shop_open: null, welcome_text_uz: null, welcome_text_ru: null,
          readiness: { delivery_fee: true, free_delivery_from: false, min_order_amount: false, work_hours: false, card_number: false, card_holder: false, support_username: false, shop_phone: false, is_shop_open: false, welcome_text_uz: false, welcome_text_ru: false },
        });
      }
      return response(config, {});
    };

    renderPage(<SettingsPage route={route("settings")} />);
    const fee = await screen.findByLabelText(/yetkazib berish narxi/i);
    expect(fee).toHaveDisplayValue("");
    expect(await screen.findAllByText(/sozlanmagan/i)).not.toHaveLength(0);
    await user.clear(fee);
    await user.type(fee, "15000");
    await user.click(screen.getByRole("button", { name: /sozlamalarni saqlash/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/yozuv boshqa sessiyada o'zgargan/i);
    expect(fee).toHaveValue(15000);

    await user.click(screen.getByRole("button", { name: /eng so'nggi versiyani ko'rish/i }));
    await waitFor(() => expect(settingsReads).toBe(2));
    expect(fee).toHaveValue(15000);
    await user.click(screen.getByRole("button", { name: /sozlamalarni saqlash/i }));
    await waitFor(() => expect(settingsWrites).toHaveLength(2));
    expect(settingsWrites[0]).toMatchObject({ expected_version: 1, delivery_fee: "15000" });
    expect(settingsWrites[1]).toMatchObject({ expected_version: 2, delivery_fee: "15000" });
  });

  it("preserves a product draft through conflict refresh and uploads photos as multipart", async () => {
    const user = userEvent.setup();
    let version = 4;
    let firstSave = true;
    let loadedProduct = false;
    const productWrites: Array<Record<string, unknown>> = [];
    const photoRequests: Array<{ method: string; path: string; body: unknown; csrf: string | undefined }> = [];
    adminApi.defaults.adapter = async (config) => {
      if (config.url === "/auth/admin/session") return response(config, { admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" });
      if (config.url === "/admin/categories") return response(config, [{ id: 3, parent_id: null, name_uz: "Daftarlar", name_ru: "Тетради", slug: "daftarlar", description_uz: null, description_ru: null, image_url: null, sort_order: 0, edit_version: 0, is_active: true, products_count: 1 }]);
      if (config.url === "/admin/products" && config.method === "get") return response(config, { items: [{ id: 5, category_id: 3, name_uz: "Oddiy daftar", name_ru: "Тетрадь", description_uz: null, description_ru: null, sku: "NOTE-1", barcode: null, price: "12000", old_price: null, stock_qty: 9, unit: "dona", min_order_qty: 1, is_active: true, is_featured: false, sort_order: 0, lot_url: null, edit_version: version, images: [{ id: 13, url: "/synthetic.jpg", telegram_file_id: null, is_main: true, sort_order: 0 }, { id: 14, url: "/synthetic-2.jpg", telegram_file_id: null, is_main: false, sort_order: 1 }] }], total: 1, page: 1, limit: 20, total_pages: 1 });
      if (config.url === "/admin/products/5" && config.method === "get") {
        loadedProduct = true;
        return response(config, { id: 5, category_id: 3, name_uz: "Server name", name_ru: "Имя сервера", description_uz: null, description_ru: null, sku: "NOTE-1", barcode: null, price: "12000", old_price: null, stock_qty: 8, unit: "dona", min_order_qty: 1, is_active: true, is_featured: false, sort_order: 0, lot_url: null, edit_version: version, images: [{ id: 13, url: "/synthetic.jpg", telegram_file_id: null, is_main: true, sort_order: 0 }, { id: 14, url: "/synthetic-2.jpg", telegram_file_id: null, is_main: false, sort_order: 1 }] });
      }
      if (config.url === "/admin/products/5" && config.method === "patch" && firstSave) {
        productWrites.push(typeof config.data === "string" ? JSON.parse(config.data) as Record<string, unknown> : config.data as Record<string, unknown>);
        firstSave = false;
        version += 1;
        throw conflict(config);
      }
      if (config.url === "/admin/products/5" && config.method === "patch") {
        productWrites.push(typeof config.data === "string" ? JSON.parse(config.data) as Record<string, unknown> : config.data as Record<string, unknown>);
        return response(config, { id: 5, images: [{ id: 13, url: "/synthetic.jpg", telegram_file_id: null, is_main: true, sort_order: 0 }, { id: 14, url: "/synthetic-2.jpg", telegram_file_id: null, is_main: false, sort_order: 1 }] });
      }
      if (/\/admin\/products\/5\/images$/.test(config.url ?? "") && config.method === "post") {
        photoRequests.push({ method: config.method, path: config.url ?? "", body: config.data, csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        return response(config, { id: 5, images: [{ id: 13, url: "/synthetic.jpg", telegram_file_id: null, is_main: true, sort_order: 0 }, { id: 14, url: "/synthetic-2.jpg", telegram_file_id: null, is_main: false, sort_order: 1 }] });
      }
      if (/\/admin\/products\/5\/images\/(13|14)$/.test(config.url ?? "") && config.method === "patch") {
        photoRequests.push({ method: config.method, path: config.url ?? "", body: config.data, csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        return response(config, { id: 5, images: [{ id: 13, url: "/synthetic.jpg", telegram_file_id: null, is_main: true, sort_order: 0 }, { id: 14, url: "/synthetic-2.jpg", telegram_file_id: null, is_main: false, sort_order: 1 }] });
      }
      return response(config, {});
    };

    renderPage(<CatalogPage route={route("catalog")} />);
    await user.click(await screen.findByRole("button", { name: /mahsulotni tahrirlash:.*oddiy daftar/i }));
    const name = screen.getByLabelText(/nomi \(o'zbekcha\)/i);
    await user.clear(name);
    await user.type(name, "Yangi daftar");
    await user.click(screen.getByRole("button", { name: /mahsulotni saqlash/i }));
    await waitFor(() => expect(productWrites).toHaveLength(1));
    expect(productWrites[0]?.expected_edit_version).toBe(4);
    expect(await screen.findByRole("alert")).toHaveTextContent(/yozuv boshqa sessiyada o'zgargan/i);
    expect(name).toHaveValue("Yangi daftar");
    await user.click(screen.getByRole("button", { name: /eng so'nggi versiyani ko'rish/i }));
    await waitFor(() => expect(loadedProduct).toBe(true));
    expect(name).toHaveValue("Yangi daftar");
    await user.click(screen.getByRole("button", { name: /mahsulotni saqlash/i }));
    await waitFor(() => expect(productWrites).toHaveLength(2));
    expect(productWrites[1]?.expected_edit_version).toBe(5);

    await user.click(await screen.findByRole("button", { name: /mahsulotni tahrirlash:.*oddiy daftar/i }));

    const file = new File([new Uint8Array([137, 80, 78, 71])], "photo.png", { type: "image/png" });
    await user.upload(screen.getByLabelText(/mahsulot rasmi/i), file);
    await user.click(screen.getByRole("button", { name: /rasmni yuklash/i }));
    await waitFor(() => expect(photoRequests.some((request) => request.method === "post" && request.path === "/admin/products/5/images" && request.body instanceof FormData)).toBe(true));
    expect(photoRequests[0]?.csrf).toBe("csrf");
    await user.click(screen.getAllByRole("button", { name: /asosiy rasm qilish/i })[1]);
    await waitFor(() => expect(photoRequests.map((request) => `${request.method} ${request.path}`)).toContain("patch /admin/products/5/images/14"));
    expect(JSON.stringify(photoRequests.at(-1)?.body)).toContain("is_main");
    await user.click(screen.getAllByRole("button", { name: "Pastga" })[0]);
    await waitFor(() => expect(photoRequests.map((request) => `${request.method} ${request.path}`)).toContain("patch /admin/products/5/images/13"));
    expect(String(photoRequests.at(-1)?.body)).toContain('"sort_order":1');
  });

  it("retains a stale category draft and sends its cover as multipart with CSRF", async () => {
    const user = userEvent.setup();
    let version = 0;
    let nameUz = "Daftarlar";
    let firstSave = true;
    const writes: Array<Record<string, unknown>> = [];
    const uploads: Array<{ path: string; body: unknown; csrf: string | undefined }> = [];
    const category = (imageUrl: string | null = null) => ({ id: 3, parent_id: null, name_uz: nameUz, name_ru: "Тетради", slug: "daftarlar", description_uz: null, description_ru: null, image_url: imageUrl, sort_order: 0, edit_version: version, is_active: true, products_count: 1 });
    adminApi.defaults.adapter = async (config) => {
      if (config.url === "/auth/admin/session") return response(config, { admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" });
      if (config.url === "/admin/categories" && config.method === "get") return response(config, [category()]);
      if (config.url === "/admin/products" && config.method === "get") return response(config, { items: [], total: 0, page: 1, limit: 100, total_pages: 1 });
      if (config.url === "/admin/categories/3" && config.method === "patch") {
        const body = typeof config.data === "string" ? JSON.parse(config.data) as Record<string, unknown> : config.data as Record<string, unknown>;
        writes.push(body);
        if (firstSave) {
          firstSave = false;
          version = 1;
          throw conflict(config);
        }
        version = 2;
        nameUz = String(body.name_uz);
        return response(config, category());
      }
      if (config.url === "/admin/categories/3/image" && config.method === "put") {
        uploads.push({ path: config.url, body: config.data, csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        return response(config, category("/synthetic-category-cover.jpg"));
      }
      return response(config, {});
    };

    renderPage(<CatalogPage route={route("catalog")} />);
    await user.click(await screen.findByRole("button", { name: /kategoriyani tahrirlash: daftarlar/i }));
    const name = screen.getByLabelText(/nomi \(o'zbekcha\)/i);
    await user.clear(name);
    await user.type(name, "Mening kategoriya");
    await user.click(screen.getByRole("button", { name: /kategoriyani saqlash/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/yozuv boshqa sessiyada o'zgargan/i);
    expect(name).toHaveValue("Mening kategoriya");
    await user.click(screen.getByRole("button", { name: /eng so'nggi versiyani ko'rish/i }));
    await waitFor(() => expect(version).toBe(1));
    expect(name).toHaveValue("Mening kategoriya");
    await user.click(screen.getByRole("button", { name: /kategoriyani saqlash/i }));
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[0]?.expected_edit_version).toBe(0);
    expect(writes[1]?.expected_edit_version).toBe(1);

    await user.click(await screen.findByRole("button", { name: /kategoriyani tahrirlash: mening kategoriya/i }));
    const cover = new File([new Uint8Array([137, 80, 78, 71])], "cover.png", { type: "image/png" });
    await user.upload(screen.getByLabelText(/kategoriya rasmi/i), cover);
    await user.click(screen.getByRole("button", { name: /rasmni yuklash/i }));
    await waitFor(() => expect(uploads.at(-1)?.path).toBe("/admin/categories/3/image"));
    expect(uploads.at(-1)?.body).toBeInstanceOf(FormData);
    expect(uploads.at(-1)?.csrf).toBe("csrf");
  });

  it("uploads a private photo, previews, creates a draft, confirms launch, retries the same UUID, polls checkpoints, and cancels", async () => {
    const user = userEvent.setup();
    const previews: Array<{ body: Record<string, unknown>; csrf: string | undefined }> = [];
    const drafts: Array<{ body: Record<string, unknown>; csrf: string | undefined }> = [];
    const launches: Array<{ path: string; body: Record<string, unknown>; csrf: string | undefined }> = [];
    const mediaUploads: Array<{ body: unknown; csrf: string | undefined }> = [];
    let launchAttempts = 0;
    let progressReads = 0;
    const draft = {
      id: 12, text: "Synthetic announcement", photo_storage_key: "photo-asset-123", photo_file_id: null,
      button_text: "Open shop", button_url: "https://shop.example.test", target: "active", status: "draft",
      sent_count: 0, failed_count: 0, pending_count: 0, sending_count: 0, cancelled_count: 0,
      created_at: "2026-10-10T08:00:00Z", launched_at: null,
    };
    let progressState: Record<string, unknown> = draft;
    adminApi.defaults.adapter = async (config) => {
      const url = config.url ?? "";
      if (url === "/auth/admin/session") return response(config, { admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" });
      if (url === "/admin/broadcasts/media" && config.method === "post") {
        mediaUploads.push({ body: config.data, csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        return response(config, { photo_storage_key: "photo-asset-123" });
      }
      if (url === "/admin/broadcasts/preview" && config.method === "post") {
        previews.push({ body: parseRequestBody(config.data), csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        return response(config, { preview_fingerprint: "a".repeat(64), preview_count: 12 });
      }
      if (url === "/admin/broadcasts" && config.method === "post") {
        drafts.push({ body: parseRequestBody(config.data), csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        return response(config, draft);
      }
      if (url === "/admin/broadcasts/12/launch" && config.method === "post") {
        launches.push({ path: url, body: parseRequestBody(config.data), csrf: config.headers.get("X-CSRF-Token") as string | undefined });
        launchAttempts += 1;
        if (launchAttempts === 1) throw new AxiosError("Network outcome unknown", "ERR_NETWORK", config);
        progressState = { ...draft, status: "sending", pending_count: 12, launched_at: "2026-10-10T08:01:00Z" };
        return response(config, progressState);
      }
      if (url === "/admin/broadcasts/12" && config.method === "get") {
        progressReads += 1;
        progressState = { ...progressState, status: "sending", sent_count: 3, pending_count: 8, sending_count: 1, launched_at: "2026-10-10T08:01:00Z" };
        return response(config, progressState);
      }
      if (url === "/admin/broadcasts/12/cancel" && config.method === "post") {
        expect(config.headers.get("X-CSRF-Token")).toBe("csrf");
        progressState = { ...progressState, status: "cancelled", sent_count: 3, pending_count: 0, sending_count: 0, cancelled_count: 9, launched_at: "2026-10-10T08:01:00Z" };
        return response(config, progressState);
      }
      return response(config, {});
    };

    renderPage(<BroadcastsPage route={route("broadcasts")} />);
    expect(previews).toHaveLength(0);
    expect(drafts).toHaveLength(0);
    expect(launches).toHaveLength(0);
    const target = screen.getByLabelText(/auditoriya/i);
    await user.selectOptions(target, "active");
    await user.type(screen.getByLabelText(/xabar matni/i), "Synthetic announcement");
    await user.type(screen.getByLabelText(/tugma matni/i), "Open shop");
    await user.type(screen.getByLabelText(/tugma HTTPS havolasi/i), "https://shop.example.test");
    await user.upload(screen.getByLabelText(/xabar rasmi/i), new File(["synthetic"], "photo.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: /rasmni shaxsiy yuklash/i }));
    await waitFor(() => expect(mediaUploads).toHaveLength(1));
    expect(mediaUploads[0]?.body).toBeInstanceOf(FormData);
    expect(mediaUploads[0]?.csrf).toBe("csrf");

    await user.click(screen.getByRole("button", { name: /auditoriyani ko'rib chiqish/i }));
    await waitFor(() => expect(previews).toHaveLength(1));
    expect(previews[0]?.body).toMatchObject({ target: "active", text: "Synthetic announcement", photo_storage_key: "photo-asset-123", photo_file_id: null, button_text: "Open shop", button_url: "https://shop.example.test" });
    expect(previews[0]?.csrf).toBe("csrf");
    expect(await screen.findByText(/12 mijoz/i)).toBeInTheDocument();
    expect(launches).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /qoralama yaratish/i }));
    await waitFor(() => expect(drafts).toHaveLength(1));
    expect(drafts[0]?.body).toMatchObject({ preview_fingerprint: "a".repeat(64), preview_count: 12, target: "active", text: "Synthetic announcement", photo_storage_key: "photo-asset-123", photo_file_id: null, button_text: "Open shop", button_url: "https://shop.example.test" });
    expect(drafts[0]?.csrf).toBe("csrf");
    expect(launches).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /yuborishni ko'rib chiqish/i }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(/12 mijoz/i);
    expect(launches).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: /yuborishni tasdiqlash/i }));
    expect(await screen.findByText(/javobi olinmadi/i)).toBeInTheDocument();
    const firstKey = launches[0]?.body.idempotency_key;
    expect(firstKey).toMatch(/^[0-9a-f-]{36}$/i);
    expect(launches[0]?.body).toEqual({ preview_fingerprint: "a".repeat(64), preview_count: 12, idempotency_key: firstKey });
    await user.click(screen.getByRole("button", { name: /yuborishni qayta tekshirish/i }));
    await waitFor(() => expect(launches).toHaveLength(2));
    expect(launches[1]?.body.idempotency_key).toBe(firstKey);
    expect(launches.every((launch) => launch.path === "/admin/broadcasts/12/launch" && launch.csrf === "csrf")).toBe(true);
    expect(await screen.findByText("Yuborildi")).toBeInTheDocument();
    expect(await screen.findByText("8")).toBeInTheDocument();
    expect(progressReads).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /qolgan yuborishni bekor qilish/i }));
    expect(await screen.findAllByText(/bekor qilindi/i)).not.toHaveLength(0);
  });

  it("preserves content and requires a fresh preview after create and audience conflicts", async () => {
    const user = userEvent.setup();
    let previewCount = 0;
    let createAttempts = 0;
    let launchAttempts = 0;
    const previews: Array<Record<string, unknown>> = [];
    const drafts: Array<Record<string, unknown>> = [];
    const launches: Array<Record<string, unknown>> = [];
    const activeDraft = {
      id: 22, text: "Conflict-safe draft", target: "buyers", photo_storage_key: null, photo_file_id: null,
      button_text: null, button_url: null, status: "draft", sent_count: 0, failed_count: 0,
      pending_count: 0, sending_count: 0, cancelled_count: 0, created_at: "2026-10-10T08:00:00Z", launched_at: null,
    };
    adminApi.defaults.adapter = async (config) => {
      const url = config.url ?? "";
      if (url === "/auth/admin/session") return response(config, { admin_id: 9, full_name: "Manager", role: "manager", csrf_token: "csrf" });
      if (url === "/admin/broadcasts/preview" && config.method === "post") {
        previews.push(parseRequestBody(config.data));
        previewCount += 1;
        return response(config, { preview_fingerprint: String(previewCount).padStart(64, "b"), preview_count: previewCount === 1 ? 5 : 7 });
      }
      if (url === "/admin/broadcasts" && config.method === "post") {
        drafts.push(parseRequestBody(config.data));
        createAttempts += 1;
        if (createAttempts === 1) throw broadcastError(config, "BROADCAST_PREVIEW_CHANGED", 409);
        return response(config, activeDraft);
      }
      if (url === "/admin/broadcasts/22/launch" && config.method === "post") {
        launches.push(parseRequestBody(config.data));
        launchAttempts += 1;
        if (launchAttempts === 1) throw broadcastError(config, "BROADCAST_AUDIENCE_CHANGED", 409);
        return response(config, { ...activeDraft, status: "sending", pending_count: 7, launched_at: "2026-10-10T08:02:00Z" });
      }
      if (url === "/admin/broadcasts/22" && config.method === "get") return response(config, activeDraft);
      return response(config, {});
    };

    renderPage(<BroadcastsPage route={route("broadcasts")} />);
    await user.selectOptions(screen.getByLabelText(/auditoriya/i), "buyers");
    await user.type(screen.getByLabelText(/xabar matni/i), "Conflict-safe draft");
    await user.click(screen.getByRole("button", { name: /auditoriyani ko'rib chiqish/i }));
    await waitFor(() => expect(previews).toHaveLength(1));
    await user.click(screen.getByRole("button", { name: /qoralama yaratish/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/mazmuni/i);
    expect(screen.getByLabelText(/xabar matni/i)).toHaveValue("Conflict-safe draft");
    expect(screen.getByRole("button", { name: /qoralama yaratish/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /auditoriyani ko'rib chiqish/i }));
    await waitFor(() => expect(previews).toHaveLength(2));
    await user.click(screen.getByRole("button", { name: /qoralama yaratish/i }));
    await waitFor(() => expect(drafts).toHaveLength(2));

    await user.click(screen.getByRole("button", { name: /yuborishni ko'rib chiqish/i }));
    await user.click(screen.getByRole("button", { name: /yuborishni tasdiqlash/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/auditoriya o'zgardi/i);
    expect(screen.getByLabelText(/xabar matni/i)).toHaveValue("Conflict-safe draft");
    expect(screen.queryByRole("button", { name: /yuborishni ko'rib chiqish/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /auditoriyani ko'rib chiqish/i }));
    await waitFor(() => expect(previews).toHaveLength(3));
    await user.click(screen.getByRole("button", { name: /yuborishni ko'rib chiqish/i }));
    await user.click(screen.getByRole("button", { name: /yuborishni tasdiqlash/i }));
    await waitFor(() => expect(launches).toHaveLength(2));
    expect(launches[0]?.preview_fingerprint).toBe(`${"b".repeat(63)}2`);
    expect(launches[1]?.preview_fingerprint).toBe(`${"b".repeat(63)}3`);
    expect(launches[0]?.idempotency_key).not.toBe(launches[1]?.idempotency_key);
    expect(drafts).toHaveLength(2);
  });

  it("stops retrying a draft after the server reports it was already launched", async () => {
    const user = userEvent.setup();
    let launches = 0;
    let progressReads = 0;
    const broadcast = {
      id: 31, text: "Already launched", target: "all", photo_storage_key: null, photo_file_id: null,
      button_text: null, button_url: null, status: "draft", sent_count: 0, failed_count: 0,
      pending_count: 0, sending_count: 0, cancelled_count: 0, created_at: "2026-10-10T08:00:00Z", launched_at: null,
    };
    adminApi.defaults.adapter = async (config) => {
      const url = config.url ?? "";
      if (url === "/auth/admin/session") return response(config, { admin_id: 9, full_name: "Manager", role: "manager", csrf_token: "csrf" });
      if (url === "/admin/broadcasts/preview" && config.method === "post") return response(config, { preview_fingerprint: "c".repeat(64), preview_count: 3 });
      if (url === "/admin/broadcasts" && config.method === "post") return response(config, broadcast);
      if (url === "/admin/broadcasts/31/launch" && config.method === "post") {
        launches += 1;
        throw broadcastError(config, "BROADCAST_ALREADY_LAUNCHED", 409);
      }
      if (url === "/admin/broadcasts/31" && config.method === "get") {
        progressReads += 1;
        return response(config, { ...broadcast, status: "sending", sent_count: 1, pending_count: 2, launched_at: "2026-10-10T08:01:00Z" });
      }
      return response(config, {});
    };

    renderPage(<BroadcastsPage route={route("broadcasts")} />);
    await user.type(screen.getByLabelText(/xabar matni/i), "Already launched");
    await user.click(screen.getByRole("button", { name: /auditoriyani ko'rib chiqish/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /qoralama yaratish/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /qoralama yaratish/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /yuborishni ko'rib chiqish/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /yuborishni ko'rib chiqish/i }));
    await user.click(screen.getByRole("button", { name: /yuborishni tasdiqlash/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/allaqachon ishga tushirilgan/i);
    expect(screen.queryByRole("button", { name: /yuborishni ko'rib chiqish/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /auditoriyani ko'rib chiqish/i })).toBeDisabled();
    expect(launches).toBe(1);

    await user.click(screen.getByRole("button", { name: /qayta yuklash/i }));
    await waitFor(() => expect(progressReads).toBeGreaterThan(0));
    expect(await screen.findAllByText(/yuborilmoqda/i)).not.toHaveLength(0);
    expect(launches).toBe(1);
  });
});

function parseRequestBody(data: unknown): Record<string, unknown> {
  return typeof data === "string" ? JSON.parse(data) as Record<string, unknown> : data as Record<string, unknown>;
}

function broadcastError(config: Parameters<AxiosAdapter>[0], code: string, status: number) {
  return new AxiosError("Broadcast conflict", "ERR_BAD_REQUEST", config, undefined, {
    config, data: { error: { code, message: "Broadcast preview changed." } },
    status, statusText: "Conflict", headers: new AxiosHeaders(),
  });
}
