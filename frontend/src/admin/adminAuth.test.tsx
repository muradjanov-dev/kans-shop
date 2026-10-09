import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
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
import { AdminAuthProvider, useAdminAuth } from "@/admin/AdminAuthProvider";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function AdminAuthHarness() {
  const auth = useAdminAuth();
  return (
    <div>
      <output data-testid="admin-auth-status">{auth.status}</output>
      <output data-testid="admin-auth-name">{auth.session?.full_name ?? "anonymous"}</output>
      <button onClick={() => void auth.login("123456").catch(() => undefined)} type="button">Complete admin login</button>
      <button onClick={() => void auth.logout().catch(() => undefined)} type="button">Log out admin</button>
    </div>
  );
}

function renderAuthHarness(strict = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const harness = <AdminAuthProvider><AdminAuthHarness /></AdminAuthProvider>;
  const view = render(
    <QueryClientProvider client={queryClient}>
      {strict ? <StrictMode>{harness}</StrictMode> : harness}
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
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

  it("ignores an older bootstrap 401 after code exchange and keeps admin CSRF and buyer state", async () => {
    useAuthStore.getState().setTokens({ access_token: "buyer-access-token", refresh_token: "buyer-refresh-token", is_admin: false });
    const oldSession = deferred<AxiosResponse<AdminSession>>();
    const sessionRequestStarted = deferred<void>();
    let oldSessionConfig: Parameters<AxiosAdapter>[0] | undefined;
    const csrfHeaders: Array<string | undefined> = [];
    adminApi.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/auth/admin/session")) {
        oldSessionConfig = config;
        sessionRequestStarted.resolve();
        return oldSession.promise;
      }
      if (config.url?.endsWith("/auth/admin/code/exchange")) return response(config, adminSession);
      csrfHeaders.push(headerValue(config, "X-CSRF-Token"));
      return response(config, { ok: true });
    };
    const user = userEvent.setup();
    renderAuthHarness(true);
    await sessionRequestStarted.promise;

    await user.click(screen.getByRole("button", { name: "Complete admin login" }));
    await waitFor(() => {
      expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("authenticated");
      expect(screen.getByTestId("admin-auth-name")).toHaveTextContent(adminSession.full_name);
    });
    await adminApi.post("/admin/probe", { operation: "write" });

    const requestConfig = oldSessionConfig!;
    oldSession.reject(new AxiosError(
      "Request failed",
      "ERR_BAD_REQUEST",
      requestConfig,
      undefined,
      response(requestConfig, { error: { code: "ADMIN_SESSION_REQUIRED" } }, 401),
    ));

    await waitFor(() => expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("authenticated"));
    await adminApi.post("/admin/probe", { operation: "write-again" });
    expect(csrfHeaders).toEqual([adminSession.csrf_token, adminSession.csrf_token]);
    expect(useAuthStore.getState().accessToken).toBe("buyer-access-token");
  });

  it("does not restore a session from an old bootstrap 200 after logout", async () => {
    const oldSession = deferred<AxiosResponse<AdminSession>>();
    const sessionRequestStarted = deferred<void>();
    const probeHeaders: Array<string | undefined> = [];
    let oldSessionConfig: Parameters<AxiosAdapter>[0] | undefined;
    adminApi.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/auth/admin/session")) {
        oldSessionConfig = config;
        sessionRequestStarted.resolve();
        return oldSession.promise;
      }
      if (config.url?.endsWith("/auth/admin/code/exchange")) return response(config, adminSession);
      if (config.url?.endsWith("/admin/probe")) probeHeaders.push(headerValue(config, "X-CSRF-Token"));
      return response(config, { ok: true });
    };
    const user = userEvent.setup();
    renderAuthHarness();
    await sessionRequestStarted.promise;

    await user.click(screen.getByRole("button", { name: "Complete admin login" }));
    await waitFor(() => expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("authenticated"));
    await user.click(screen.getByRole("button", { name: "Log out admin" }));
    await waitFor(() => expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("anonymous"));

    const requestConfig = oldSessionConfig!;
    oldSession.resolve(response(requestConfig, adminSession));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await adminApi.post("/admin/probe", { operation: "after-logout" });

    expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("anonymous");
    expect(screen.getByTestId("admin-auth-name")).toHaveTextContent("anonymous");
    expect(probeHeaders).toEqual([undefined]);
  });

  it("discards an old domain response before it can populate the new admin cache", async () => {
    const oldDomain = deferred<AxiosResponse<{ owner: string }>>();
    const domainRequestStarted = deferred<void>();
    let domainRequestConfig: Parameters<AxiosAdapter>[0] | undefined;
    const secondSession = { ...adminSession, csrf_token: "new-admin-csrf-token", full_name: "New Admin" };
    adminApi.defaults.adapter = async (config) => {
      if (config.url?.endsWith("/auth/admin/session")) return response(config, adminSession);
      if (config.url?.endsWith("/auth/admin/code/exchange")) return response(config, secondSession);
      if (config.url?.endsWith("/admin/private-data")) {
        domainRequestConfig = config;
        domainRequestStarted.resolve();
        return oldDomain.promise;
      }
      return response(config, { ok: true });
    };
    const user = userEvent.setup();
    const { queryClient } = renderAuthHarness();
    await waitFor(() => expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("authenticated"));

    const oldPrivateRequest = adminApi.get<{ owner: string }>("/admin/private-data").then(({ data }) => {
      queryClient.setQueryData(["admin", "private-data"], data);
      return data;
    });
    await domainRequestStarted.promise;
    await user.click(screen.getByRole("button", { name: "Log out admin" }));
    await waitFor(() => expect(screen.getByTestId("admin-auth-status")).toHaveTextContent("anonymous"));
    await user.click(screen.getByRole("button", { name: "Complete admin login" }));
    await waitFor(() => expect(screen.getByTestId("admin-auth-name")).toHaveTextContent("New Admin"));

    const requestConfig = domainRequestConfig!;
    oldDomain.resolve(response(requestConfig, { owner: adminSession.full_name }));

    await expect(oldPrivateRequest).rejects.toMatchObject({ name: "StaleAdminResponseError" });
    expect(queryClient.getQueryData(["admin", "private-data"])).toBeUndefined();
  });
});
