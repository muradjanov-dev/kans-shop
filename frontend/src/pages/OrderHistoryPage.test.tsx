import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import { SupportLinks } from "@/components/storefront/SupportLinks";
import { CustomerAuthProvider } from "@/features/customer-auth/CustomerAuthProvider";
import { OrderDetailPage } from "@/pages/OrderDetailPage";
import { OrdersPage } from "@/pages/OrdersPage";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";
import type { Order, PublicSettings } from "@/types/api";

interface HistoryItem {
  id: number;
  order_number: string;
  created_at: string;
  status: string;
  payment_status: string;
  order_type: string;
  total: string;
}

interface HistoryPage {
  items: HistoryItem[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

interface TimelineItem {
  status: string;
  occurred_at: string | null;
  changed_by_admin_id?: number;
  changed_by_admin_name?: string;
  comment?: string;
}

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

const createdAt = "2026-10-09T08:30:00Z";

const order: Order = {
  id: 42,
  order_number: "KS-42",
  status: "confirmed",
  order_type: "delivery",
  customer_name: "Snapshot Customer",
  customer_phone: "+998901234567",
  address: "Snapshot Street 12, Apartment 3",
  address_comment: "Snapshot gate note",
  comment: "Customer checkout note",
  subtotal: "2500.50",
  delivery_fee: "0.00",
  discount: "0.00",
  total: "2500.50",
  payment_method: "cash",
  payment_status: "pending",
  payment_instructions: null,
  receipt_version: 0,
  has_receipt: false,
  receipt_url: null,
  cancel_reason: null,
  created_at: createdAt,
  confirmed_at: null,
  completed_at: null,
  cancelled_at: null,
  items: [{
    id: 1,
    product_id: 7,
    product_name_snapshot: "Snapshot Notebook",
    product_sku_snapshot: "NB-7",
    price: "1250.25",
    quantity: 2,
    total: "2500.50",
  }],
};

function RoutedOrderDetail() {
  return (
    <Routes>
      <Route path="/orders/:id" element={<OrderDetailPage />} />
    </Routes>
  );
}

const baseSettings: PublicSettings = {
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
};

function renderSupportLinks(settings: Partial<PublicSettings>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(["public-settings"], { ...baseSettings, ...settings });
  return render(
    <QueryClientProvider client={queryClient}>
      <SupportLinks />
    </QueryClientProvider>,
  );
}

function CustomerSessionSwitch() {
  return (
    <button type="button" onClick={() => useAuthStore.getState().setTokens({
      access_token: jwt(99),
      refresh_token: "refresh-99",
      is_admin: false,
    })}>
      Switch to another account
    </button>
  );
}

function PrivateOrderQueryProbe() {
  const userId = useAuthStore((state) => state.userId);
  const history = useQuery({
    queryKey: ["order-history", userId, 1],
    enabled: Boolean(userId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<HistoryPage>("/orders/history", {
        params: { page: 1, limit: 24 },
        signal,
      });
      return data;
    },
  });
  const timeline = useQuery({
    queryKey: ["order-timeline", userId, 42],
    enabled: Boolean(userId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<TimelineItem[]>("/orders/42/timeline", { signal });
      return data;
    },
  });

  return (
    <div>
      <p>{history.data?.items[0]?.order_number}</p>
      <p>{timeline.data?.[0]?.status}</p>
    </div>
  );
}

let originalAdapter: typeof api.defaults.adapter;

afterEach(() => {
  cleanup();
  if (originalAdapter !== undefined) api.defaults.adapter = originalAdapter;
  originalAdapter = undefined;
  useAuthStore.getState().clear();
  useLanguageStore.getState().setLanguage("uz");
});

describe("customer order history and timeline", () => {
  it("history_is_paginated_and_localized", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    useLanguageStore.getState().setLanguage("uz");
    originalAdapter = api.defaults.adapter;
    const requestedPages: number[] = [];
    const firstPage: HistoryPage = {
      items: [{
        id: 42,
        order_number: "KS-42",
        created_at: createdAt,
        status: "preparing",
        payment_status: "paid",
        order_type: "pickup",
        total: "1234.56",
      }],
      total: 25,
      page: 1,
      limit: 24,
      total_pages: 2,
    };
    const secondPage: HistoryPage = {
      ...firstPage,
      items: [{
        ...firstPage.items[0]!,
        id: 43,
        order_number: "KS-43",
        status: "completed",
        order_type: "delivery",
      }],
      page: 2,
    };
    api.defaults.adapter = async (config) => {
      if (config.url !== "/orders/history") throw new Error(`Unexpected request: ${config.method} ${config.url}`);
      const page = Number((config.params as { page?: number } | undefined)?.page ?? 1);
      requestedPages.push(page);
      return response(config, page === 1 ? firstPage : secondPage);
    };

    const user = userEvent.setup();
    renderWithProviders(<OrdersPage />, "/orders", true);

    expect(await screen.findByRole("link", { name: /KS-42/ })).toBeInTheDocument();
    expect(screen.getByText("Tayyorlanmoqda")).toBeInTheDocument();
    expect(screen.getByText("Olib ketish")).toBeInTheDocument();
    expect(screen.getByText(/To'lov qabul qilindi/)).toBeInTheDocument();
    expect(screen.getByText(/1 234\.56/)).toBeInTheDocument();
    expect(document.querySelector(`time[datetime="${createdAt}"]`)).not.toBeNull();

    await user.click(screen.getByRole("button", { name: "Keyingi" }));
    expect(await screen.findByRole("link", { name: /KS-43/ })).toBeInTheDocument();
    expect(requestedPages).toEqual([1, 2]);

    act(() => useLanguageStore.getState().setLanguage("ru"));
    expect(screen.getByText("Выполнен")).toBeInTheDocument();
    expect(screen.getByText("Доставка")).toBeInTheDocument();
  });

  it("timeline_does_not_invent_future_events", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    originalAdapter = api.defaults.adapter;
    const adminInternalComment = "internal note for operators";
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, order);
      if (config.url === "/orders/42/timeline") {
        return response(config, [{
          status: "new",
          occurred_at: createdAt,
          changed_by_admin_id: 901,
          changed_by_admin_name: "Hidden Operator",
          comment: adminInternalComment,
        } satisfies TimelineItem]);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    const rendered = renderWithProviders(<RoutedOrderDetail />, "/orders/42", true);
    const { container } = rendered;

    const timeline = await screen.findByRole("list", { name: "Buyurtma vaqt jadvali" });
    await within(timeline).findByText("Yangi");
    const currentStep = within(timeline).getByText("Tasdiqlandi");
    expect(currentStep.closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Yangi").closest("li")).toHaveAttribute("data-state", "completed");
    const pendingStep = screen.getByText("Tayyorlanmoqda").closest("li");
    expect(pendingStep).toHaveAttribute("data-state", "pending");
    expect(pendingStep?.querySelector("time")).toBeNull();
    expect(currentStep.closest("li")?.querySelector("time")).toBeNull();
    expect(container.querySelectorAll("time")).toHaveLength(1);
    expect(container.querySelector(`time[datetime="${createdAt}"]`)).not.toBeNull();
    expect(container.textContent).not.toContain(adminInternalComment);
    expect(timeline.textContent).not.toContain("Hidden Operator");
    expect(timeline.textContent).not.toContain("901");
    expect(rendered.queryClient.getQueryData(["order-timeline", "42", 42])).toEqual([
      { status: "new", occurred_at: createdAt },
    ]);
  });

  it("cancelled_timeline_is_terminal", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    const cancelledOrder = { ...order, status: "cancelled" as const };
    originalAdapter = api.defaults.adapter;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, cancelledOrder);
      if (config.url === "/orders/42/timeline") {
        return response(config, [
          { status: "new", occurred_at: createdAt },
          { status: "cancelled", occurred_at: "2026-10-09T09:00:00Z" },
        ] satisfies TimelineItem[]);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    renderWithProviders(<RoutedOrderDetail />, "/orders/42", true);

    const timeline = await screen.findByRole("list", { name: "Buyurtma vaqt jadvali" });
    await within(timeline).findByText("Yangi");
    const cancelledStep = within(timeline).getByText("Bekor qilindi");
    expect(cancelledStep.closest("li")).toHaveAttribute("aria-current", "step");
    expect(cancelledStep.closest("li")).toHaveAttribute("data-state", "current");
    expect(within(timeline).queryByText("Bajarildi")).not.toBeInTheDocument();
    expect(within(timeline).queryByText("Yetkazilmoqda")).not.toBeInTheDocument();
    expect(within(timeline).getByText("Yangi").closest("li")).toHaveAttribute("data-state", "completed");
  });

  it("empty_or_corrupt_timeline_shows_only_current_status", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    originalAdapter = api.defaults.adapter;
    const timelines: unknown[] = [
      [],
      [{ status: "completed", occurred_at: "2030-01-01T00:00:00Z" }],
      [{ status: "operator_only_debug", occurred_at: createdAt }],
    ];
    let timelineRequest = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, order);
      if (config.url === "/orders/42/timeline") {
        return response(config, timelines[timelineRequest++]);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    for (const _responseBody of timelines) {
      const rendered = renderWithProviders(<RoutedOrderDetail />, "/orders/42", true);
      const timeline = await screen.findByRole("list", { name: "Buyurtma vaqt jadvali" });
      await waitFor(() => {
        expect(rendered.queryClient.getQueryState(["order-timeline", "42", 42])?.status).toBe("success");
      });
      expect(within(timeline).getByText("Tasdiqlandi")).toBeInTheDocument();
      expect(timeline.querySelectorAll("li")).toHaveLength(1);
      expect(timeline.querySelector("time")).toBeNull();
      rendered.unmount();
    }
  });

  it("support_links_hide_invalid_or_empty_values", () => {
    const nullSettings = renderSupportLinks({
      support_username: null,
      shop_phone: null,
      work_hours: null,
      welcome_text_uz: null,
      welcome_text_ru: null,
    });
    expect(nullSettings.container.firstChild).toBeNull();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    nullSettings.unmount();

    const invalidContacts = renderSupportLinks({
      support_username: "not a username",
      shop_phone: "++",
      work_hours: "09:00–18:00",
      welcome_text_uz: "Do‘konning sozlangan xush kelibsiz matni",
    });

    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByText("09:00–18:00")).toBeInTheDocument();
    expect(screen.getByText("Do‘konning sozlangan xush kelibsiz matni")).toBeInTheDocument();

    invalidContacts.unmount();
    const emptySettings = renderSupportLinks({
      support_username: "x",
      shop_phone: "++",
      work_hours: "  ",
      welcome_text_uz: "\n ",
      welcome_text_ru: "",
    });
    expect(emptySettings.container.firstChild).toBeNull();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("order_detail_keeps_snapshot_address", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    originalAdapter = api.defaults.adapter;
    const personalDataRequests: string[] = [];
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, order);
      if (config.url === "/orders/42/timeline") return response(config, []);
      if (config.url === "/profile" || config.url === "/addresses") {
        personalDataRequests.push(String(config.url));
        return response(config, { display_name: "Edited Name", address_text: "Edited Address" });
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    renderWithProviders(<RoutedOrderDetail />, "/orders/42", true);

    expect(await screen.findByText("Snapshot Customer")).toBeInTheDocument();
    expect(screen.getByText("Snapshot Street 12, Apartment 3")).toBeInTheDocument();
    expect(screen.getByText("Snapshot Notebook × 2")).toBeInTheDocument();
    expect(screen.getAllByText(/2 500\.5/)).toHaveLength(2);
    expect(screen.queryByText("Edited Name")).not.toBeInTheDocument();
    expect(screen.queryByText("Edited Address")).not.toBeInTheDocument();
    expect(personalDataRequests).toEqual([]);
  });

  it("order_ownership_errors_stay_recoverable", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    originalAdapter = api.defaults.adapter;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") {
        return Promise.reject(Object.assign(new Error("Not your order"), {
          config,
          response: { status: 403, data: { error: { code: "FORBIDDEN" } } },
        }));
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    renderWithProviders(<RoutedOrderDetail />, "/orders/42", true);

    expect(await screen.findByRole("button", { name: "Qayta urinish" })).toBeInTheDocument();
    expect(screen.queryByText("Snapshot Customer")).not.toBeInTheDocument();
    expect(screen.queryByText("KS-42")).not.toBeInTheDocument();
  });

  it("customer_order_history_and_timeline_caches_are_removed_on_account_switch", async () => {
    useAuthStore.getState().setTokens({
      access_token: jwt(42),
      refresh_token: "refresh-42",
      is_admin: false,
    });
    originalAdapter = api.defaults.adapter;
    let releaseOldHistory!: () => void;
    let releaseOldTimeline!: () => void;
    let oldHistoryStarted!: () => void;
    let oldTimelineStarted!: () => void;
    const oldHistoryGate = new Promise<void>((resolve) => { releaseOldHistory = resolve; });
    const oldTimelineGate = new Promise<void>((resolve) => { releaseOldTimeline = resolve; });
    const historyStarted = new Promise<void>((resolve) => { oldHistoryStarted = resolve; });
    const timelineStarted = new Promise<void>((resolve) => { oldTimelineStarted = resolve; });
    const oldHistory: HistoryPage = {
      items: [{ id: 42, order_number: "OLD-USER-ORDER", created_at: createdAt, status: "new", payment_status: "pending", order_type: "pickup", total: "100" }],
      total: 1,
      page: 1,
      limit: 24,
      total_pages: 1,
    };
    const newHistory: HistoryPage = {
      ...oldHistory,
      items: [{ ...oldHistory.items[0]!, id: 99, order_number: "NEW-USER-ORDER" }],
    };
    api.defaults.adapter = async (config) => {
      const accessToken = String(config.headers.get("Authorization"));
      const isOldUser = accessToken.includes(jwt(42));
      if (config.url === "/orders/history") {
        if (isOldUser) {
          oldHistoryStarted();
          await oldHistoryGate;
          return response(config, oldHistory);
        }
        return response(config, newHistory);
      }
      if (config.url === "/orders/42/timeline") {
        if (isOldUser) {
          oldTimelineStarted();
          await oldTimelineGate;
          return response(config, [{ status: "new", occurred_at: createdAt }]);
        }
        return response(config, [{ status: "confirmed", occurred_at: createdAt }]);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    const rendered = renderWithProviders(
      <CustomerAuthProvider>
        <PrivateOrderQueryProbe />
        <CustomerSessionSwitch />
      </CustomerAuthProvider>,
      "/orders",
      false,
    );
    await Promise.all([historyStarted, timelineStarted]);
    try {
      await userEvent.setup().click(screen.getByRole("button", { name: "Switch to another account" }));

      expect(await screen.findByText("NEW-USER-ORDER")).toBeInTheDocument();
      await waitFor(() => {
        expect(rendered.queryClient.getQueryCache().find({ queryKey: ["order-history", "42", 1], exact: true })).toBeUndefined();
        expect(rendered.queryClient.getQueryCache().find({ queryKey: ["order-timeline", "42", 42], exact: true })).toBeUndefined();
      });

      releaseOldHistory();
      releaseOldTimeline();
      await waitFor(() => {
        expect(rendered.queryClient.getQueryCache().find({ queryKey: ["order-history", "42", 1], exact: true })).toBeUndefined();
        expect(rendered.queryClient.getQueryCache().find({ queryKey: ["order-timeline", "42", 42], exact: true })).toBeUndefined();
      });
      expect(screen.queryByText("OLD-USER-ORDER")).not.toBeInTheDocument();
      expect(screen.getByText("NEW-USER-ORDER")).toBeInTheDocument();
    } finally {
      releaseOldHistory();
      releaseOldTimeline();
    }
  });
});
