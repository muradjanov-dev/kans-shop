import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AdminAuthProvider } from "@/admin/AdminAuthProvider";
import { adminApi, setAdminCsrfToken } from "@/admin/api";
import { CatalogPage } from "@/admin/pages/CatalogPage";
import { SettingsPage } from "@/admin/pages/SettingsPage";
import { adminRouteRegistry } from "@/admin/adminRoutes";

const originalAdapter = adminApi.defaults.adapter;
const route = (id: "catalog" | "settings") => adminRouteRegistry.find((entry) => entry.id === id)!;

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
});
