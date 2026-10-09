import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { Order } from "@/types/api";
import { OrdersPage } from "@/pages/OrdersPage";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";
import { useAuthStore } from "@/store/auth";

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

function jwt(sub: number): string {
  const payload = btoa(JSON.stringify({ sub: String(sub) }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `e30.${payload}.signature`;
}

const order: Order = {
  id: 42,
  order_number: "KS-42",
  status: "new",
  order_type: "delivery",
  customer_name: "Test Customer",
  customer_phone: "+998901234567",
  address: "Tashkent",
  address_comment: null,
  comment: null,
  subtotal: "1250",
  delivery_fee: "0",
  discount: "0",
  total: "1250",
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

let originalAdapter: typeof api.defaults.adapter;
afterEach(() => {
  if (originalAdapter !== undefined) api.defaults.adapter = originalAdapter;
  originalAdapter = undefined;
});

describe("orders access recovery", () => {
  it("keeps order history text and cards readable in dark mode", async () => {
    useAuthStore.getState().setTokens({ access_token: jwt(42), refresh_token: "refresh-42", is_admin: false });
    originalAdapter = api.defaults.adapter;
    api.defaults.adapter = async (config) => response(config, {
      items: [{
        id: order.id,
        order_number: order.order_number,
        created_at: order.created_at,
        status: order.status,
        payment_status: order.payment_status,
        order_type: order.order_type,
        total: order.total,
      }],
      total: 1,
      page: 1,
      limit: 24,
      total_pages: 1,
    });

    renderWithProviders(<OrdersPage />, "/orders", true);

    const heading = await screen.findByRole("heading", { name: "Mening buyurtmalarim" });
    const orderLink = screen.getByRole("link", { name: /KS-42/ });
    expect(heading).toHaveClass("dark:text-white");
    expect(orderLink).toHaveClass("dark:border-white/10", "dark:bg-slate-900");
    expect(screen.getByText("Buyurtma KS-42")).toHaveClass("dark:text-white");
    expect(screen.getByText(/1 250/)).toHaveClass("dark:text-white");
  });

  it("offers account sign-in recovery before fetching private orders", async () => {
    originalAdapter = api.defaults.adapter;
    let historyRequests = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/history") {
        historyRequests += 1;
        return response(config, { items: [], total: 0, page: 1, limit: 24, total_pages: 1 });
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<OrdersPage />, "/orders", true);
    await user.click(screen.getByRole("button", { name: "Kirish" }));

    expect(await screen.findByRole("dialog", { name: "Kans Shop hisobingizga kiring" })).toBeInTheDocument();
    expect(historyRequests).toBe(0);
  });
});
