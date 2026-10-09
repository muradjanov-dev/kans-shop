import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosResponse,
} from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "@/App";
import { adminApi, setAdminCsrfToken, type AdminSession } from "@/admin/api";
import { useAuthStore } from "@/store/auth";

const adminSession: AdminSession = {
  admin_id: 14,
  full_name: "Aziza Admin",
  role: "manager",
  csrf_token: "server-csrf-token",
};

const originalAdminAdapter = adminApi.defaults.adapter;
const originalAxiosAdapter = axios.defaults.adapter;

function response<T>(
  config: Parameters<AxiosAdapter>[0],
  data: T,
  status = 200,
): AxiosResponse<T> {
  return {
    data,
    status,
    statusText: status === 200 ? "OK" : "Unauthorized",
    headers: new AxiosHeaders(),
    config,
  };
}

function unauthorized(config: Parameters<AxiosAdapter>[0]): Promise<never> {
  const errorResponse = response(config, { error: { code: "ADMIN_SESSION_REQUIRED" } }, 401);
  return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse));
}

function headerValue(config: Parameters<AxiosAdapter>[0], name: string): string | undefined {
  const value = config.headers.get(name);
  return typeof value === "string" ? value : undefined;
}

function renderAdmin(path = "/admin") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  adminApi.defaults.adapter = originalAdminAdapter;
  axios.defaults.adapter = originalAxiosAdapter;
  setAdminCsrfToken(null);
  delete (window as unknown as { Telegram?: unknown }).Telegram;
});

describe("admin session authentication", () => {
  it("does not start Telegram customer authentication on an admin route", async () => {
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: { WebApp: { initData: "telegram-customer-init-data" } },
    });
    adminApi.defaults.adapter = async (config) => unauthorized(config);
    const customerAuthRequest = vi.spyOn(axios, "post").mockResolvedValue({ data: {} } as never);

    renderAdmin("/admin/orders");

    expect(await screen.findByLabelText(/kirish kodi/i)).toBeInTheDocument();
    expect(customerAuthRequest).not.toHaveBeenCalled();
  });

  it("shows the login screen without private content when the session is missing", async () => {
    adminApi.defaults.adapter = async (config) => unauthorized(config);

    renderAdmin("/admin/orders");

    expect(await screen.findByRole("heading", { name: /admin paneliga kirish/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /telegram/i })).toHaveAttribute("href", "https://t.me/kansshopbot");
    expect(screen.getByText("/admin_login")).toBeInTheDocument();
    expect(screen.queryByText(/buyurtmalar moduli/i)).not.toBeInTheDocument();
  });

  it("clears private views after the server rejects an authenticated admin request", async () => {
    useAuthStore.getState().setTokens({ access_token: "buyer-access-token", refresh_token: "buyer-refresh-token", is_admin: false });
    let mutationCalls = 0;
    adminApi.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/auth/admin/session")) return response(config, adminSession);
      if (config.url?.endsWith("/admin/private-mutation")) mutationCalls += 1;
      return unauthorized(config);
    };
    renderAdmin();

    expect(await screen.findByText("Aziza Admin")).toBeInTheDocument();
    await expect(adminApi.post("/admin/private-mutation", { state: "change" })).rejects.toMatchObject({ response: { status: 401 } });

    await waitFor(() => {
      expect(screen.queryByText("Aziza Admin")).not.toBeInTheDocument();
      expect(screen.getByLabelText(/kirish kodi/i)).toBeInTheDocument();
    });
    expect(mutationCalls).toBe(1);
    expect(useAuthStore.getState().accessToken).toBe("buyer-access-token");
  });

  it("exchanges a bot code for the server session and sends CSRF on unsafe JSON and multipart requests", async () => {
    expect(adminApi.defaults.baseURL).toBe("/api/v1");
    expect(adminApi.defaults.withCredentials).toBe(true);
    useAuthStore.getState().setTokens({ access_token: "buyer-access-token", refresh_token: "buyer-refresh-token", is_admin: false });
    const requests: Array<{
      url: string;
      method: string;
      data: unknown;
      csrf: string | undefined;
      authorization: string | undefined;
      withCredentials: boolean;
    }> = [];
    adminApi.defaults.adapter = async (config) => {
      requests.push({
        url: config.url ?? "",
        method: config.method ?? "",
        data: config.data,
        csrf: headerValue(config, "X-CSRF-Token"),
        authorization: headerValue(config, "Authorization"),
        withCredentials: Boolean(config.withCredentials),
      });
      if (config.url?.endsWith("/auth/admin/session")) return unauthorized(config);
      if (config.url?.endsWith("/auth/admin/code/exchange")) return response(config, adminSession);
      if (config.url?.endsWith("/auth/admin/session/refresh")) return response(config, adminSession);
      return response(config, { ok: true });
    };
    const user = userEvent.setup();
    renderAdmin("/admin/login");

    await user.type(await screen.findByLabelText(/kirish kodi/i), "123456");
    await user.click(screen.getByRole("button", { name: /kirish/i }));
    expect(await screen.findByText("Aziza Admin")).toBeInTheDocument();

    await adminApi.post("/admin/probe", { enabled: true });
    const form = new FormData();
    form.append("photo", new Blob(["image"]), "image.png");
    await adminApi.post("/admin/upload-probe", form);
    await adminApi.refreshSession();

    const exchange = requests.find((request) => request.url.endsWith("/auth/admin/code/exchange"));
    expect(exchange).toMatchObject({ method: "post", csrf: undefined, authorization: undefined, withCredentials: true });
    expect(JSON.parse(String(exchange?.data))).toEqual({ code: "123456" });
    for (const request of requests.filter((item) => ["/admin/probe", "/admin/upload-probe", "/auth/admin/session/refresh"].some((path) => item.url.endsWith(path)))) {
      expect(request.csrf).toBe(adminSession.csrf_token);
      expect(request.authorization).toBeUndefined();
    }
    expect(requests.find((request) => request.url.endsWith("/admin/upload-probe"))?.data).toBeInstanceOf(FormData);
  });

  it("uses the logout endpoint and clears the admin session", async () => {
    const requests: Array<{ url: string; method: string; csrf: string | undefined }> = [];
    adminApi.defaults.adapter = async (config) => {
      requests.push({
        url: config.url ?? "",
        method: config.method ?? "",
        csrf: headerValue(config, "X-CSRF-Token"),
      });
      if (config.url?.endsWith("/auth/admin/session")) return response(config, adminSession);
      return response(config, { ok: true });
    };
    const user = userEvent.setup();
    renderAdmin();

    expect(await screen.findByText("Aziza Admin")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Chiqish" }));

    await waitFor(() => expect(screen.getByLabelText(/kirish kodi/i)).toBeInTheDocument());
    expect(requests.find((request) => request.url.endsWith("/auth/admin/logout"))).toMatchObject({
      method: "post",
      csrf: adminSession.csrf_token,
    });
  });

  it("calls logout-all through the admin client", async () => {
    const requests: Array<{ url: string; method: string; csrf: string | undefined }> = [];
    adminApi.defaults.adapter = async (config) => {
      requests.push({
        url: config.url ?? "",
        method: config.method ?? "",
        csrf: headerValue(config, "X-CSRF-Token"),
      });
      return response(config, adminSession);
    };
    // Setting CSRF through the session provider mirrors the browser flow.
    setAdminCsrfToken(adminSession.csrf_token);

    await adminApi.logoutAll();

    expect(requests[0]).toMatchObject({ url: "/auth/admin/logout-all", method: "post", csrf: adminSession.csrf_token });
  });
});
