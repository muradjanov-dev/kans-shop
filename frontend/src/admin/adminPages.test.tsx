import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "@/App";
import { exportAdminStats } from "@/admin/adminQueries";
import { adminApi, type AdminSession } from "@/admin/api";
import { useLanguageStore } from "@/store/language";

const originalAdapter = adminApi.defaults.adapter;

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

function renderAdmin(session: AdminSession, path = "/admin") {
  const requests: string[] = [];
  adminApi.defaults.adapter = async (config) => {
    const url = config.url ?? "";
    requests.push(`${config.method?.toUpperCase()} ${url}`);
    if (url.endsWith("/auth/admin/session")) return response(config, session);
    if (url === "/admin/stats/overview") {
      return response(config, {
        period: "today",
        orders_count: 4,
        order_value: "125000",
        paid_amount: "45000",
        revenue: "125000",
        avg_check: "31250",
        new_users: 2,
        top_products: [{ name: "Daftar", sold: 3 }],
      });
    }
    if (url === "/admin/orders") {
      return response(config, { items: [], total: 0, page: 1, limit: 20, total_pages: 1 });
    }
    if (url === "/admin/users") {
      return response(config, {
        items: [{
          id: 71, telegram_id: 701, username: null, first_name: "Dilnoza", last_name: null,
          phone: "+998 ** *** **42", language: "uz", is_blocked: false, source: "webapp",
          created_at: "2026-10-09T00:00:00Z", last_active_at: null,
        }], total: 1, page: 1, limit: 20, total_pages: 1,
      });
    }
    if (url === "/admin/sources") {
      return response(config, {
        items: [{ id: 9, name: "Yarmarka", code: "fair", is_active: true, clicks_count: 11, created_at: "2026-10-09T00:00:00Z" }],
        total: 1, page: 1, limit: 20, total_pages: 1,
      });
    }
    if (url === "/admin/sources/9") {
      return response(config, {
        id: 9, name: "Yarmarka", code: "fair", is_active: true,
        bot_link: "https://t.me/kansshopbot?start=src_fair", clicks: 11,
        first_touch_users: 4, orders_count: 3, order_value: "85000", created_at: "2026-10-09T00:00:00Z",
      });
    }
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

describe("admin domain pages", () => {
  it("lets an operator use orders and read-only reports while hiding management pages", async () => {
    renderAdmin({ admin_id: 7, full_name: "Operator", role: "operator", csrf_token: "csrf" }, "/admin/reports");

    const nav = await screen.findByRole("navigation", { name: /asosiy menyu/i });
    expect(within(nav).getByRole("link", { name: "Buyurtmalar" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Hisobotlar" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Katalog" })).not.toBeInTheDocument();
    expect(await screen.findByText(/125\s?000/)).toBeInTheDocument();
  });

  it("shows the masked phone returned for customer lists", async () => {
    renderAdmin({ admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" }, "/admin/customers");

    expect(await screen.findByText(/\+998 \*\* \*\*\* \*\*42/)).toBeInTheDocument();
    expect(screen.queryByText("+998 90 123 4542")).not.toBeInTheDocument();
  });

  it("labels order value and paid amount separately and exposes first-touch source metrics", async () => {
    const reports = renderAdmin({ admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" }, "/admin/reports");
    expect(await screen.findByText(/bekor qilinmagan buyurtmalar summasi/i)).toBeInTheDocument();
    expect(screen.getByText(/to'lovi tasdiqlangan buyurtmalar summasi/i)).toBeInTheDocument();
    reports.unmount();

    renderAdmin({ admin_id: 8, full_name: "Manager", role: "manager", csrf_token: "csrf" }, "/admin/sources");
    await userClick(await screen.findByRole("button", { name: /ko'rish/i }));
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText(/birinchi tashrif manbasi/i)).toBeInTheDocument();
  });

  it("keeps broadcasts in progress and makes no broadcast mutation when the page opens", async () => {
    const { requests } = renderAdmin({ admin_id: 1, full_name: "Manager", role: "manager", csrf_token: "csrf" }, "/admin/broadcasts");
    expect(await screen.findByText(/task 10.*api/i)).toBeInTheDocument();
    await waitFor(() => expect(requests.some((request) => /POST .*broadcasts/i.test(request))).toBe(false));
  });

  it("sends the selected UI language to the XLSX export contract", async () => {
    let acceptLanguage: string | undefined;
    adminApi.defaults.adapter = async (config) => {
      acceptLanguage = config.headers.get("Accept-Language") as string | undefined;
      return response(config, new Blob(["synthetic xlsx"]));
    };

    await exportAdminStats("month", "ru");

    expect(acceptLanguage).toBe("ru");
  });

  it("queues a one-off order message only on the explicit action with the order message DTO", async () => {
    const user = userEvent.setup();
    const queued: Array<Record<string, unknown>> = [];
    let messageRequests = 0;
    const detail = {
      id: 5, order_number: "A-5", status: "new", order_type: "delivery", customer_name: "Synthetic buyer",
      customer_phone: "+998900000005", address: "Synthetic address", address_comment: null, comment: null,
      subtotal: "12000", delivery_fee: "0", discount: "0", total: "12000", payment_method: "cash",
      payment_status: "pending", receipt_url: null, payment_instructions: null, receipt_version: 0,
      payment_reviewed_by_admin_id: null, payment_reviewed_at: null, cancel_reason: null,
      created_at: "2026-10-09T09:00:00Z", confirmed_at: null, completed_at: null, cancelled_at: null,
      has_receipt: false, items: [{ id: 1, product_id: null, product_name_snapshot: "Synthetic notebook", product_sku_snapshot: "SYN-1", price: "12000", quantity: 1, total: "12000" }],
      status_history: [], payment_history: [], payment_review_history: [],
    };
    adminApi.defaults.adapter = async (config) => {
      const url = config.url ?? "";
      if (url === "/auth/admin/session") return response(config, { admin_id: 7, full_name: "Operator", role: "operator", csrf_token: "csrf" });
      if (url === "/admin/orders" && config.method === "get") return response(config, { items: [detail], total: 1, page: 1, limit: 20, total_pages: 1 });
      if (url === "/admin/orders/5" && config.method === "get") return response(config, detail);
      if (url === "/admin/orders/5/message" && config.method === "post") {
        messageRequests += 1;
        queued.push(typeof config.data === "string" ? JSON.parse(config.data) as Record<string, unknown> : config.data as Record<string, unknown>);
        return response(config, { message_id: 901, state: "queued" });
      }
      return response(config, { items: [], total: 0, page: 1, limit: 20, total_pages: 1 });
    };

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/admin/orders"]}><App /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(messageRequests).toBe(0);
    await user.click(await screen.findByRole("button", { name: /A-5/i }));
    await user.type(screen.getByLabelText(/mijozga xabar/i), "Synthetic follow-up");
    await user.click(screen.getByRole("button", { name: /xabarni navbatga qo'yish/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/xabar navbatga qo'yildi/i);
    expect(messageRequests).toBe(1);
    expect(queued.at(-1)).toMatchObject({ text: "Synthetic follow-up" });
    expect(queued.at(-1)?.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i);
    expect(queued.at(-1)).not.toHaveProperty("telegram_id");
  });
});

async function userClick(element: HTMLElement) {
  const { default: userEvent } = await import("@testing-library/user-event");
  await userEvent.setup().click(element);
}

afterEach(() => {
  adminApi.defaults.adapter = originalAdapter;
  useLanguageStore.getState().setLanguage("uz");
});
