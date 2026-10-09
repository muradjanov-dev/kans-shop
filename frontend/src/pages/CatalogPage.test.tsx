import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import type { AxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { useLanguageStore } from "@/store/language";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { Category, Page, Product, PublicSettings } from "@/types/api";
import { CatalogPage } from "@/pages/CatalogPage";
import { ProductPage } from "@/pages/ProductPage";

const product = (id: number, name = `Product ${id}`): Product => ({
  id,
  category_id: 1,
  name_uz: name,
  name_ru: name,
  description_uz: null,
  description_ru: null,
  sku: `SKU-${id}`,
  price: "12000.50",
  old_price: null,
  stock_qty: 30,
  unit: "dona",
  min_order_qty: 1,
  is_active: true,
  is_featured: false,
  lot_url: null,
  views_count: 0,
  sold_count: 0,
  edit_version: 1,
  images: [],
});

const category = (id: number, parentId: number | null, name: string): Category => ({
  id,
  parent_id: parentId,
  name_uz: name,
  name_ru: name,
  slug: `category-${id}`,
  description_uz: null,
  description_ru: null,
  image_url: null,
  sort_order: id,
  edit_version: 1,
  is_active: true,
  products_count: 0,
});

function categoryChildren(parentId: unknown): Category[] {
  if (parentId === undefined) return [category(1, null, "Root")];
  if (parentId === 1) return [category(2, 1, "Child")];
  if (parentId === 2) return [category(3, 2, "Grandchild")];
  return [];
}

function publicSettings(overrides: Partial<PublicSettings> = {}): PublicSettings {
  return {
    delivery_fee: null,
    free_delivery_from: null,
    min_order_amount: null,
    work_hours: null,
    card_number: null,
    card_holder: null,
    support_username: null,
    shop_phone: null,
    is_shop_open: null,
    welcome_text_uz: null,
    welcome_text_ru: null,
    enabled_payment_providers: [],
    ...overrides,
  };
}

function productPage(items: Product[], page = 1, totalPages = 1): Page<Product> {
  return { items, total: totalPages > 1 ? 25 : items.length, page, limit: 24, total_pages: totalPages };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function response<T>(data: T) {
  return { data, status: 200, statusText: "OK", headers: {}, config: {} } as never;
}

function renderCatalog(initialEntry = "/") {
  return renderWithProviders(
    <>
      <Routes>
        <Route path="/" element={<CatalogPage />} />
        <Route path="/product/:id" element={<ProductPage />} />
      </Routes>
      <LocationProbe />
    </>,
    initialEntry,
    true,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="route-location">{`${location.pathname}${location.search}`}</output>;
}

describe("CatalogPage", () => {
  let get: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    get = vi.spyOn(api, "get");
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") {
        return response(categoryChildren(config?.params?.parent_id));
      }
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings());
      if (url === "/catalog/products") return response(productPage([]));
      if (url === "/catalog/products/7") return response(product(7, "Product 7"));
      throw new Error(`Unexpected GET ${String(url)}`);
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
  });

  it("test_catalog_debounce_abort_and_back_navigation", async () => {
    vi.useFakeTimers();
    const oldRequest = deferred<never>();
    const newRequest = deferred<never>();
    const productRequests: Array<{ query: unknown; signal: AbortSignal | undefined }> = [];
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") return response(categoryChildren(config?.params?.parent_id));
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings());
      if (url === "/catalog/products") {
        const query = config?.params?.q;
        productRequests.push({ query, signal: config?.signal as AbortSignal | undefined });
        if (query === "old") return oldRequest.promise;
        if (query === "new") return newRequest.promise;
        return response(productPage([]));
      }
      if (url === "/catalog/products/7") return response(product(7, "Product 7"));
      throw new Error(`Unexpected GET ${String(url)}`);
    });

    renderCatalog("/?q=old&category=3&min_price=4.50&in_stock=true&sort=newest&page=1");
    await vi.waitFor(() => expect(productRequests.map(({ query }) => query)).toContain("old"));
    const oldSignal = productRequests.find(({ query }) => query === "old")?.signal;
    expect(oldSignal).toBeDefined();

    fireEvent.change(screen.getByRole("searchbox", { name: "Mahsulotlarni qidirish" }), {
      target: { value: "new" },
    });
    expect(productRequests.filter(({ query }) => query === "new")).toHaveLength(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(299); });
    expect(productRequests.filter(({ query }) => query === "new")).toHaveLength(0);

    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    await vi.waitFor(() => expect(productRequests.filter(({ query }) => query === "new")).toHaveLength(1));
    expect(oldSignal?.aborted).toBe(true);
    vi.useRealTimers();

    await act(async () => {
      newRequest.resolve(response(productPage([product(7, "Newest result")])));
      await Promise.resolve();
    });
    expect(await screen.findByText("Newest result")).toBeInTheDocument();
    await act(async () => {
      oldRequest.resolve(response(productPage([product(8, "Stale result")])));
      await Promise.resolve();
    });
    expect(screen.queryByText("Stale result")).not.toBeInTheDocument();

    Object.defineProperty(window, "scrollY", { configurable: true, value: 321 });
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    fireEvent.click(screen.getAllByRole("link", { name: /Newest result/ })[0]!);
    expect(await screen.findByRole("heading", { name: "Product 7" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: /Orqaga/ }));
    expect(await screen.findByRole("searchbox", { name: "Mahsulotlarni qidirish" })).toHaveValue("new");
    expect(screen.getByTestId("route-location")).toHaveTextContent("q=new");
    expect(screen.getByTestId("route-location")).toHaveTextContent("category=3");
    expect(screen.getByTestId("route-location")).toHaveTextContent("page=1");
    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith({ top: 321 }));
  });

  it("test_catalog_filters_reset_page_and_append_unique_ids", async () => {
    const requests: Array<{ params: Record<string, unknown> | undefined; signal: AbortSignal | undefined }> = [];
    const pageOne = productPage(Array.from({ length: 24 }, (_, index) => product(index + 1)), 1, 2);
    const pageTwo = productPage([product(24), product(25)], 2, 2);
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") return response(categoryChildren(config?.params?.parent_id));
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings());
      if (url === "/catalog/products") {
        const params = config?.params as Record<string, unknown> | undefined;
        requests.push({ params, signal: config?.signal as AbortSignal | undefined });
        if (params?.page === 2) return response(pageTwo);
        return response(pageOne);
      }
      throw new Error(`Unexpected GET ${String(url)}`);
    });

    renderCatalog("/?q=pen&category=2&min_price=5.00&max_price=90.50&in_stock=true&sort=price_asc&page=1");
    await waitFor(() => expect(requests.length).toBeGreaterThan(0));
    expect(requests[0]?.params).toMatchObject({
      q: "pen",
      category_id: 2,
      min_price: "5",
      max_price: "90.5",
      in_stock: true,
      sort: "price_asc",
      page: 1,
      limit: 24,
    });

    fireEvent.click(await screen.findByRole("button", { name: "Yana ko‘rsatish" }));
    await waitFor(() => expect(requests.some(({ params }) => params?.page === 2)).toBe(true));
    await waitFor(() => expect(screen.getByText("Product 25")).toBeInTheDocument());
    const productIds = screen.getAllByRole("article").map((article) =>
      within(article).getAllByRole("link")[0]?.getAttribute("href"),
    );
    expect(productIds).toHaveLength(25);
    expect(new Set(productIds).size).toBe(productIds.length);
    expect(requests.some(({ params }) => params?.page === 2)).toBe(true);

    fireEvent.change(screen.getByRole("textbox", { name: "Minimal narx" }), {
      target: { value: "12.75" },
    });
    await waitFor(() => expect(requests.some(({ params }) => params?.min_price === "12.75")).toBe(true));
    expect(requests.at(-1)?.params?.page).toBe(1);
  });

  it("test_category_tree_and_breadcrumb_navigation", async () => {
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") return response(categoryChildren(config?.params?.parent_id));
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings({ welcome_text_uz: "Configured welcome" }));
      if (url === "/catalog/products") return response(productPage([]));
      throw new Error(`Unexpected GET ${String(url)}`);
    });

    renderCatalog();
    fireEvent.click(await screen.findByRole("button", { name: /Root/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Child/ }));
    expect(await screen.findByRole("button", { name: /Grandchild/ })).toBeInTheDocument();
    expect(screen.getByText("Configured welcome")).toBeInTheDocument();
    const breadcrumbs = screen.getByRole("navigation", { name: "Kategoriyalar" });
    expect(within(breadcrumbs).getByRole("button", { name: "Barcha kategoriyalar" })).toBeInTheDocument();
    expect(within(breadcrumbs).getByText("Root")).toBeInTheDocument();
    expect(within(breadcrumbs).getByText("Child")).toBeInTheDocument();
    fireEvent.click(within(breadcrumbs).getByRole("button", { name: "Barcha kategoriyalar" }));
    expect(await screen.findByRole("button", { name: /Root/ })).toBeInTheDocument();
  });

  it("clears a category URL value missing from the public category tree", async () => {
    renderCatalog("/?category=999&page=3");
    await waitFor(() => expect(screen.getByTestId("route-location")).not.toHaveTextContent("category=999"));
    expect(screen.getByTestId("route-location")).toHaveTextContent("page=1");
  });

  it.each([
    ["fractional page", { page: 1.5 }],
    ["zero page", { page: 0 }],
    ["negative total pages", { total_pages: -1 }],
    ["fractional total pages", { total_pages: 1.5 }],
    ["zero total pages for nonempty data", { total_pages: 0 }],
  ])("shows a recoverable error for %s metadata", async (_label, metadata) => {
    const malformed = { ...productPage([product(1)], 1, 1), ...metadata };
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") return response(categoryChildren(config?.params?.parent_id));
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings());
      if (url === "/catalog/products") return response(malformed);
      throw new Error(`Unexpected GET ${url}`);
    });

    renderCatalog();
    expect(await screen.findByRole("alert")).toHaveTextContent("Xatolik yuz berdi");
    expect(screen.queryByText("Product 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Qayta urinish" })).toBeInTheDocument();
  });

  it("accepts zero total pages for an empty catalog response", async () => {
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") return response(categoryChildren(config?.params?.parent_id));
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings());
      if (url === "/catalog/products") {
        return response({ items: [], total: 0, page: 1, limit: 24, total_pages: 0 });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    renderCatalog("/?page=3");
    expect(await screen.findByText("Bu kategoriyada mahsulot yo'q")).toBeInTheDocument();
    expect(screen.getByTestId("route-location")).toHaveTextContent("page=1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("test_featured_hidden_when_empty", async () => {
    const { queryClient } = renderCatalog();
    await screen.findByRole("searchbox", { name: "Mahsulotlarni qidirish" });
    expect(screen.queryByRole("heading", { name: "Tavsiya etilgan" })).not.toBeInTheDocument();

    queryClient.setQueryData(["featured-products", 10], [{ ...product(90, "Real featured item"), is_featured: true }]);
    expect(await screen.findByRole("heading", { name: "Tavsiya etilgan" })).toBeInTheDocument();
    expect(screen.getByText("Real featured item")).toBeInTheDocument();
  });

  it("shows rate-limit retry, then clears filters from an empty result", async () => {
    let productCalls = 0;
    const requests: Array<Record<string, unknown> | undefined> = [];
    const rateLimitedError = Object.assign(new Error("Rate limited"), {
      isAxiosError: true,
      response: { status: 429 },
    });
    get.mockImplementation(async (url: string, config?: AxiosRequestConfig) => {
      if (url === "/catalog/categories") return response([]);
      if (url === "/catalog/featured") return response([]);
      if (url === "/settings/public") return response(publicSettings());
      if (url === "/catalog/products") {
        requests.push(config?.params as Record<string, unknown> | undefined);
        productCalls += 1;
        if (productCalls === 1) throw rateLimitedError;
        return response(productPage([]));
      }
      throw new Error(`Unexpected GET ${String(url)}`);
    });

    renderCatalog("/?q=missing&min_price=5&page=2");
    expect(await screen.findByText("So‘rovlar soni cheklangan. Biroz kutib, qayta urinib ko‘ring.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Qayta urinish" }));
    expect(await screen.findByText("Bu so‘rov bo‘yicha mahsulot topilmadi.")).toBeInTheDocument();
    expect(requests.at(-1)).toMatchObject({ q: "missing", min_price: "5", page: 1, limit: 24 });
    fireEvent.click(screen.getAllByRole("button", { name: "Filtrlarni tozalash" }).at(-1)!);
    await waitFor(() => expect(screen.getByTestId("route-location")).toHaveTextContent("/"));
    expect(screen.getByRole("searchbox", { name: "Mahsulotlarni qidirish" })).toHaveValue("");
  });

  it("shows localized product details, exact prices and bounded quantities", async () => {
    const detail = {
      ...product(7, "Daftar"),
      name_ru: "Тетрадь",
      description_uz: "Daftar tavsifi",
      description_ru: "Описание тетради",
      price: "12000.125",
      old_price: "13000.125",
      stock_qty: 4,
      unit: "quti" as const,
      min_order_qty: 2,
      is_featured: true,
    };
    get.mockImplementation(async (url: string) => {
      if (url === "/catalog/products/7") return response(detail);
      throw new Error(`Unexpected GET ${url}`);
    });
    useLanguageStore.setState({ language: "ru", hasUserPreference: true });

    const { queryClient } = renderCatalog("/product/7");
    expect(await screen.findByRole("heading", { name: "Тетрадь" })).toBeInTheDocument();
    expect(screen.getByText("Описание тетради")).toBeInTheDocument();
    expect(screen.getByText("12 000.125")).toBeInTheDocument();
    expect(screen.getByText("13 000.125")).toHaveClass("line-through");
    expect(screen.getByText("Остаток: 4 коробка")).toBeInTheDocument();
    expect(screen.getByText("Артикул: SKU-7")).toBeInTheDocument();
    expect(screen.getByText("Мин. заказ: 2")).toBeInTheDocument();
    expect(screen.getByText("Рекомендуем")).toBeInTheDocument();

    const decrease = screen.getByRole("button", { name: "Уменьшить количество" });
    const increase = screen.getByRole("button", { name: "Увеличить количество" });
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(decrease).toBeDisabled();
    fireEvent.click(increase);
    fireEvent.click(increase);
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(increase).toBeDisabled();

    queryClient.setQueryData(["product", 7], { ...detail, old_price: "11999.99" });
    await waitFor(() => expect(document.querySelector(".line-through")).not.toBeInTheDocument());
  });
});
