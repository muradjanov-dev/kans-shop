import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "@/App";
import { adminApi, type AdminSession } from "@/admin/api";
import { useLanguageStore } from "@/store/language";

const originalAdapter = adminApi.defaults.adapter;

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

const sales = {
  orders: 6, revenue: "480000", paid_amount: "300000", avg_check: "80000", items_sold: 15,
  cancelled: 1, customers: 4, new_customers: 3, returning_customers: 1,
};

const fixtures: Record<string, unknown> = {
  "/admin/analytics/summary": {
    period: "week", since: "2026-10-14T00:00:00Z", until: "2026-10-21T00:00:00Z",
    visitors: 12, new_visitors: 9, returning_visitors: 3, signed_in_visitors: 4, sessions: 15,
    page_views: 60, engaged_seconds: 3725, avg_session_seconds: 248, bounce_rate: 0.2,
    product_views: 20, cart_adds: 5, conversion_rate: 0.0667,
    platforms: [{ key: "telegram", count: 10 }, { key: "web", count: 5 }],
    devices: [{ key: "mobile", count: 13 }, { key: "desktop", count: 2 }],
    sources: [{ key: "direct", count: 9 }, { key: "t.me", count: 6 }],
    timeline: [
      { day: "2026-10-20", visitors: 5, sessions: 6, orders: 2, revenue: "160000" },
      { day: "2026-10-21", visitors: 7, sessions: 9, orders: 4, revenue: "320000" },
    ],
    sales,
  },
  "/admin/analytics/behavior": {
    period: "week", sessions: 15,
    sections: [
      { path: "/", section: "hero", position: 0, sessions: 15, reach_rate: 1, total_seconds: 300, avg_seconds: 20 },
      { path: "/", section: "products", position: 3, sessions: 9, reach_rate: 0.6, total_seconds: 600, avg_seconds: 66.7 },
    ],
    pages: [{ path: "/", views: 30, sessions: 15, total_seconds: 900, avg_seconds: 30 }],
    scroll: [{ path: "/", page_views: 20, reached_25: 0.9, reached_50: 0.7, reached_75: 0.5, reached_90: 0.2 }],
    clicks: [{ section: "products", target: "card_add", label: "Savatga qo'shish", clicks: 7, sessions: 5 }],
    funnel: [
      { key: "sessions", sessions: 15 }, { key: "product_view", sessions: 10 },
      { key: "add_to_cart", sessions: 4 }, { key: "checkout_start", sessions: 3 }, { key: "order_placed", sessions: 1 },
    ],
    hours: Array.from({ length: 24 }, (_, hour) => (hour === 10 ? 6 : hour === 20 ? 4 : 0)),
    searches: [
      { term: "ruchka", searches: 4, sessions: 3, zero_results: 0 },
      { term: "globus", searches: 2, sessions: 2, zero_results: 2 },
    ],
    filters: [{ key: "sort", count: 3 }],
    carousel: [{ key: "next", count: 5 }],
  },
  "/admin/analytics/products": {
    period: "week",
    products: [{
      product_id: 3, name: "Ruchka Luxor", price: "5000", image_url: null, impressions: 40, views: 10,
      viewers: 8, view_seconds: 95, cart_adds: 4, favorites: 1, ordered_qty: 6, revenue: "30000",
    }],
    interested_not_bought: [{
      product_id: 4, name: "Globus 32 sm", price: "150000", image_url: null, impressions: 12, views: 5,
      viewers: 4, view_seconds: 120, cart_adds: 0, favorites: 0, ordered_qty: 0, revenue: "0",
    }],
  },
  "/admin/analytics/customers": {
    period: "week", total: 1, page: 1, limit: 20, guest_visitors: 8, guest_sessions: 10,
    items: [{
      user_id: 5, name: "Dilnoza", username: "dilnoza_k", phone: null, sessions: 3, engaged_seconds: 600,
      page_views: 14, first_seen: "2026-10-15T08:00:00Z", last_seen: "2026-10-21T09:00:00Z", platform: "telegram",
      products_viewed: 4, cart_adds: 2, orders: 1, revenue: "45000", interests: ["Ruchka Luxor"],
    }],
  },
  "/admin/analytics/customers/5": {
    period: "week",
    customer: {
      user_id: 5, name: "Dilnoza", username: "dilnoza_k", phone: null, sessions: 3, engaged_seconds: 600,
      page_views: 14, first_seen: "2026-10-15T08:00:00Z", last_seen: "2026-10-21T09:00:00Z", platform: "telegram",
      products_viewed: 4, cart_adds: 2, orders: 1, revenue: "45000", interests: ["Ruchka Luxor"],
    },
    sessions: [{
      started_at: "2026-10-21T08:50:00Z", last_seen_at: "2026-10-21T09:00:00Z", engaged_seconds: 240,
      page_views: 5, platform: "telegram", device: "mobile", entry_path: "/",
    }],
    products: [{ product_id: 3, name: "Ruchka Luxor", views: 3, view_seconds: 80, cart_adds: 2, favorites: 1, ordered_qty: 1 }],
    searches: ["ruchka"],
    events: [{
      occurred_at: "2026-10-21T08:58:00Z", type: "add_to_cart", path: "/product/:id", section: null,
      target: null, label: null, product_name: "Ruchka Luxor", value: 2,
    }],
  },
  "/admin/analytics/sales": {
    period: "week", summary: sales,
    statuses: [{ key: "new", count: 2, amount: "160000" }, { key: "cancelled", count: 1, amount: "20000" }],
    payment_methods: [{ key: "cash", count: 4, amount: "320000" }],
    order_types: [{ key: "pickup", count: 2, amount: "160000" }],
    categories: [{ key: "Yozuv qurollari", count: 9, amount: "90000" }],
    top_products: [{ name: "Ruchka Luxor", quantity: 6, revenue: "30000" }],
    top_customers: [{ user_id: 5, name: "Dilnoza", orders: 1, revenue: "45000" }],
    heatmap: [{ weekday: 1, hour: 10, orders: 3 }],
    avg_items_per_order: 2.5,
  },
};

function renderAdmin(session: AdminSession, path: string) {
  const requests: Array<{ url: string; params: Record<string, unknown> }> = [];
  adminApi.defaults.adapter = async (config) => {
    const url = config.url ?? "";
    requests.push({ url, params: (config.params ?? {}) as Record<string, unknown> });
    if (url.endsWith("/auth/admin/session")) return response(config, session);
    if (url in fixtures) return response(config, fixtures[url]);
    return response(config, { items: [], total: 0, page: 1, limit: 20, total_pages: 1 });
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, requests };
}

describe("admin analytics dashboard", () => {
  afterEach(() => {
    adminApi.defaults.adapter = originalAdapter;
    useLanguageStore.setState({ language: "uz" });
    localStorage.clear();
  });

  it("shows behaviour, interest, customers and sales to a manager", async () => {
    const user = userEvent.setup();
    const { requests } = renderAdmin({ admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" }, "/admin/analytics");

    const nav = await screen.findByRole("navigation", { name: /asosiy menyu/i });
    expect(within(nav).getByRole("link", { name: "Statistika" })).toBeInTheDocument();
    expect(await screen.findByText("Tashrif buyuruvchilar")).toBeInTheDocument();
    expect(screen.getByText("1 soat 2 daq")).toBeInTheDocument();
    expect(screen.getByText("9 yangi, 3 qaytib kelgan")).toBeInTheDocument();
    expect(screen.getByText("Telegram ilova")).toBeInTheDocument();
    expect(screen.getByText("To'g'ridan-to'g'ri")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Jadval" })[0]!);
    expect(await screen.findByRole("columnheader", { name: "Kun" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "30 kun" }));
    expect(requests.some(({ url, params }) => url === "/admin/analytics/summary" && params.period === "month")).toBe(true);

    await user.click(screen.getByRole("tab", { name: "Xulq-atvor" }));
    expect(await screen.findByText("Karusel (eng tepada)")).toBeInTheDocument();
    expect(screen.getAllByText("Barcha mahsulotlar").length).toBeGreaterThan(0);
    expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
    expect(screen.getByText("Kartochkadagi «+» (savatga)")).toBeInTheDocument();
    expect(screen.getByText("Mahsulotni ochdi")).toBeInTheDocument();
    const globus = screen.getByText("globus").closest("tr")!;
    expect(within(globus).getByText("⚠")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Mahsulotlar" }));
    expect(await screen.findByText("Globus 32 sm")).toBeInTheDocument();
    expect(screen.getByText("Qiziqishdi, lekin sotib olishmadi")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Mijozlar" }));
    expect(await screen.findByText("Dilnoza")).toBeInTheDocument();
    expect(screen.getByText("Tizimga kirmagan mehmonlar: 8 kishi, 10 tashrif")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Batafsil" }));
    expect(await screen.findByText("Dilnoza: batafsil")).toBeInTheDocument();
    expect(screen.getByText("Savatga qo'shdi")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Savdo" }));
    expect(await screen.findByText("Naqd")).toBeInTheDocument();
    expect(screen.getByText("Olib ketish")).toBeInTheDocument();
    expect(screen.getByText("Buyurtmalar: hafta kuni va soat")).toBeInTheDocument();
    expect(screen.queryByText("Jamoa a'zolarining tashriflarini ham hisoblash")).not.toBeInTheDocument();
  });

  it("is not offered to operators", async () => {
    const { requests } = renderAdmin({ admin_id: 7, full_name: "Operator", role: "operator", csrf_token: "csrf" }, "/admin");

    const nav = await screen.findByRole("navigation", { name: /asosiy menyu/i });
    expect(within(nav).queryByRole("link", { name: "Statistika" })).not.toBeInTheDocument();
    expect(requests.some(({ url }) => url.startsWith("/admin/analytics"))).toBe(false);
  });
});
