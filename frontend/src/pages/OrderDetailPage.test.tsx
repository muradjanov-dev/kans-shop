import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { OrderDetailPage } from "@/pages/OrderDetailPage";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";
import { useAuthStore } from "@/store/auth";
import type { Order } from "@/types/api";

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
  items: [{
    id: 1,
    product_id: 7,
    product_name_snapshot: "Notebook",
    product_sku_snapshot: "NB-7",
    price: "1250",
    quantity: 1,
    total: "1250",
  }],
};

function RoutedOrderDetail() {
  return (
    <Routes>
      <Route path="/orders/:id" element={<OrderDetailPage />} />
    </Routes>
  );
}

let originalAdapter: typeof api.defaults.adapter;
afterEach(() => {
  if (originalAdapter !== undefined) api.defaults.adapter = originalAdapter;
  originalAdapter = undefined;
});

describe("order detail access", () => {
  it("keeps order details and surfaces readable in dark mode", async () => {
    useAuthStore.getState().setTokens({ access_token: jwt(42), refresh_token: "refresh-42", is_admin: false });
    originalAdapter = api.defaults.adapter;
    api.defaults.adapter = async (config) => response(config, order);

    renderWithProviders(<RoutedOrderDetail />, "/orders/42", true);

    const heading = await screen.findByRole("heading", { name: "Buyurtma KS-42" });
    expect(heading).toHaveClass("dark:text-white");
    expect(screen.getByText("To'lov usuli").parentElement).toHaveClass("dark:border-white/10", "dark:bg-slate-900");
    expect(screen.getByText("To'lov usuli")).toHaveClass("dark:text-white");
    expect(screen.getByText("Notebook × 1")).toHaveClass("dark:text-gray-200");
    expect(screen.getByText("Jami").parentElement).toHaveClass("dark:border-white/10", "dark:text-white");
  });

  it("offers account sign-in recovery before fetching another customer's private order", async () => {
    originalAdapter = api.defaults.adapter;
    let orderRequests = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") {
        orderRequests += 1;
        return response(config, {});
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<OrderDetailPage />, "/orders/42", true);
    await user.click(screen.getByRole("button", { name: "Kirish" }));

    expect(await screen.findByRole("dialog", { name: "Kans Shop hisobingizga kiring" })).toBeInTheDocument();
    expect(orderRequests).toBe(0);
  });
});
