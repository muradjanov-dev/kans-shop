import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { OrderDetailPage } from "@/pages/OrderDetailPage";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";
import { useAuthStore } from "@/store/auth";
import type { Order } from "@/types/api";

const order: Order = {
  id: 42,
  order_number: "KANS-000042",
  status: "new",
  order_type: "pickup",
  customer_name: "Ali",
  customer_phone: "+998901234567",
  address: null,
  address_comment: null,
  comment: null,
  subtotal: "250000.00",
  delivery_fee: "0.00",
  discount: "0.00",
  total: "250000.00",
  payment_method: "card_transfer",
  payment_status: "receipt_uploaded",
  payment_instructions: { card_number: "8600 1234 5678 9012", card_holder: "Kans Shop" },
  receipt_version: 1,
  has_receipt: true,
  receipt_url: "/media/receipts/42.png",
  cancel_reason: null,
  created_at: "2026-10-09T00:00:00Z",
  confirmed_at: null,
  completed_at: null,
  cancelled_at: null,
  items: [],
};

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

function signedIn(): void {
  useAuthStore.getState().setTokens({
    access_token: jwt(42),
    refresh_token: "refresh-42",
    is_admin: false,
  });
}

function renderOrderDetail() {
  return renderWithProviders(
    <Routes><Route path="/orders/:id" element={<OrderDetailPage />} /></Routes>,
    "/orders/42",
    true,
  );
}

let originalAdapter: typeof api.defaults.adapter;
afterEach(() => {
  if (originalAdapter !== undefined) api.defaults.adapter = originalAdapter;
  originalAdapter = undefined;
  vi.restoreAllMocks();
});

describe("private receipt recovery", () => {
  it("shows the saved transfer instructions and loads the receipt through the authenticated order route", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const receipt = new Blob(["private receipt"], { type: "image/png" });
    const requests: Array<{ url: string | undefined; authorization: unknown }> = [];
    const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:private-receipt");
    const revokeUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    api.defaults.adapter = async (config) => {
      requests.push({ url: config.url, authorization: config.headers.get("Authorization") });
      if (config.url === "/orders/42") return response(config, order);
      if (config.url === "/orders/42/receipt") return response(config, receipt);
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    const rendered = renderOrderDetail();
    expect(await screen.findByText("8600 1234 5678 9012")).toBeInTheDocument();
    expect(screen.getByText("Kans Shop")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "To'lov cheki" })).toHaveAttribute("src", "blob:private-receipt");
    expect(requests.some((request) => request.url === "/orders/42/receipt" && request.authorization === "Bearer e30.eyJzdWIiOiI0MiJ9.signature")).toBe(true);
    expect(requests.every((request) => !request.url?.includes("token="))).toBe(true);

    rendered.unmount();
    await waitFor(() => expect(revokeUrl).toHaveBeenCalledWith("blob:private-receipt"));
    expect(createUrl).toHaveBeenCalledWith(receipt);
  });

  it("uploads the selected file under the server's file field and displays the refreshed order", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const initial = { ...order, has_receipt: false, receipt_version: 0, receipt_url: null, payment_status: "pending" as const };
    const uploadedForms: FormData[] = [];
    let receiptCalls = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, initial);
      if (config.url === "/orders/42/receipt" && config.method === "post") {
        receiptCalls += 1;
        uploadedForms.push(config.data as FormData);
        return response(config, { ...order, payment_status: "receipt_uploaded" }, 200);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderOrderDetail();
    const upload = await screen.findByLabelText("Rasm yoki PDF chekni tanlang");
    const file = new File(["fake image"], "receipt.png", { type: "image/png" });
    await user.upload(upload, file);
    await user.click(screen.getByRole("button", { name: "Chekni yuborish" }));

    await waitFor(() => expect(receiptCalls).toBe(1));
    expect(uploadedForms[0]?.get("file")).toBeInstanceOf(File);
    expect((uploadedForms[0]?.get("file") as File).name).toBe("receipt.png");
    expect(await screen.findByText("Chek yuborildi — to'lov tekshirilmoqda")).toBeInTheDocument();
  });

  it("keeps the current user's order cache accessible when navigation happens during upload", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const initial = { ...order, has_receipt: false, receipt_version: 0, receipt_url: null, payment_status: "pending" as const };
    let releaseUpload!: () => void;
    let uploadStarted!: () => void;
    const uploadStartedPromise = new Promise<void>((resolve) => { uploadStarted = resolve; });
    const uploadResponse = new Promise<void>((resolve) => { releaseUpload = resolve; });
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, initial);
      if (config.url === "/orders/42/receipt" && config.method === "post") {
        uploadStarted();
        await uploadResponse;
        return response(config, { ...order, payment_status: "receipt_uploaded" }, 200);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    const rendered = renderOrderDetail();
    await user.upload(await screen.findByLabelText("Rasm yoki PDF chekni tanlang"), new File(["receipt"], "receipt.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Chekni yuborish" }));
    await uploadStartedPromise;
    rendered.unmount();
    releaseUpload();

    await waitFor(() => expect(rendered.queryClient.getQueryData<Order>(["order", "42", 42])?.payment_status).toBe("receipt_uploaded"));
  });

  it("keeps the existing order visible after the receipt upload is rejected", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const initial = { ...order, has_receipt: false, receipt_version: 0, receipt_url: null, payment_status: "pending" as const };
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, initial);
      if (config.url === "/orders/42/receipt" && config.method === "post") {
        const rejected = response(config, { error: { code: "RECEIPT_REJECTED", message: "invalid receipt", details: {} } }, 422);
        return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, rejected));
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderOrderDetail();
    await user.upload(await screen.findByLabelText("Rasm yoki PDF chekni tanlang"), new File(["receipt"], "receipt.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Chekni yuborish" }));

    expect(await screen.findByText("Chekni yuborib bo'lmadi. Qayta urinib ko'ring.")).toBeInTheDocument();
    expect(screen.getByText(/KANS-000042/)).toBeInTheDocument();
    expect(screen.getByText(/250 000/)).toBeInTheDocument();
  });

  it("shows support-needed for a legacy card order without a saved instruction snapshot", async () => {
    signedIn();
    originalAdapter = api.defaults.adapter;
    const legacy = {
      ...order,
      payment_instructions: null,
      has_receipt: false,
      receipt_version: 0,
      payment_status: "pending" as const,
    };
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders/42") return response(config, legacy);
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };

    renderOrderDetail();

    expect(await screen.findByText("Karta ma'lumotlari saqlanmagan. Yordam xizmatiga murojaat qiling.")).toBeInTheDocument();
    expect(screen.queryByText("8600 1234 5678 9012")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Rasm yoki PDF chekni tanlang")).not.toBeInTheDocument();
  });
});
