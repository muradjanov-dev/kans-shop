import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "@/App";
import { adminApi, setAdminCsrfToken } from "@/admin/api";

const originalAdapter = adminApi.defaults.adapter;

function response<T>(config: Parameters<AxiosAdapter>[0], data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: new AxiosHeaders(), config };
}

function unauthorized(config: Parameters<AxiosAdapter>[0]): Promise<never> {
  const errorResponse = response(config, { error: { code: "ADMIN_SESSION_REQUIRED" } }, 401);
  return Promise.reject(new AxiosError("Request failed", "ERR_BAD_REQUEST", config, undefined, errorResponse));
}

function mockCodeRequests() {
  const identifiers: string[] = [];
  adminApi.defaults.adapter = async (config) => {
    if (config.url?.endsWith("/auth/admin/code/request")) {
      identifiers.push((JSON.parse(String(config.data)) as { identifier: string }).identifier);
      return response(config, { expires_in: 300, resend_after: 60 });
    }
    return unauthorized(config);
  };
  return identifiers;
}

function renderLogin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/admin/login"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.removeItem("kans-admin-login-identifier");
});

afterEach(() => {
  vi.useRealTimers();
  adminApi.defaults.adapter = originalAdapter;
  setAdminCsrfToken(null);
  localStorage.removeItem("kans-admin-login-identifier");
});

describe("admin login code delivery", () => {
  it("sends a five-minute code to Telegram and offers a resend once it expires", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const identifiers = mockCodeRequests();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderLogin();

    await user.type(await screen.findByLabelText("Telegram ID yoki @username"), "@kans_admin");
    await user.click(screen.getByRole("button", { name: "Kodni Telegram'ga yuborish" }));

    expect(await screen.findByText("Agar bu hisob admin bo'lsa, kod Telegram'ga yuborildi.")).toBeInTheDocument();
    expect(screen.getByText("5:00 qoldi")).toBeInTheDocument();
    expect(identifiers).toEqual(["@kans_admin"]);
    expect(localStorage.getItem("kans-admin-login-identifier")).toBe("@kans_admin");
    expect(screen.queryByRole("button", { name: "Kodni qayta yuborish" })).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(300_000);
    });

    expect(await screen.findByText("Kod muddati tugadi.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kodni qayta yuborish" }));
    await waitFor(() => expect(identifiers).toEqual(["@kans_admin", "@kans_admin"]));
    expect(await screen.findByText("5:00 qoldi")).toBeInTheDocument();
  });

  it("sends a code automatically for a remembered admin", async () => {
    localStorage.setItem("kans-admin-login-identifier", "917456291");
    const identifiers = mockCodeRequests();

    renderLogin();

    await waitFor(() => expect(identifiers).toEqual(["917456291"]));
    expect(await screen.findByText("Agar bu hisob admin bo'lsa, kod Telegram'ga yuborildi.")).toBeInTheDocument();
    expect(screen.getByLabelText("Telegram ID yoki @username")).toHaveValue("917456291");
  });
});
