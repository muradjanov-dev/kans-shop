import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "@/App";
import { adminApi, setAdminCsrfToken, type AdminSession } from "@/admin/api";
import { useLanguageStore } from "@/store/language";

const originalAdminAdapter = adminApi.defaults.adapter;

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

function renderAdmin(session: AdminSession, path = "/admin") {
  adminApi.defaults.adapter = async (config) => {
    if (config.url?.endsWith("/auth/admin/session")) return response(config, session);
    return response(config, { ok: true });
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("admin responsive shell", () => {
  it("shows only the operator navigation allowed by the server role", async () => {
    renderAdmin({ admin_id: 5, full_name: "Operator", role: "operator", csrf_token: "csrf" });
    const navigation = await screen.findByRole("navigation", { name: /asosiy menyu/i });

    expect(within(navigation).getByRole("link", { name: "Bosh sahifa" })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "Buyurtmalar" })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "Hisobotlar" })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "Audit" })).toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "Katalog" })).not.toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "Jamoa" })).not.toBeInTheDocument();
  });

  it("shows management navigation in Russian without exposing Team to managers", async () => {
    useLanguageStore.getState().setLanguage("ru");
    renderAdmin({ admin_id: 8, full_name: "Менеджер", role: "manager", csrf_token: "csrf" });
    const navigation = await screen.findByRole("navigation", { name: /основная навигация/i });

    expect(within(navigation).getByRole("link", { name: "Каталог" })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "Клиенты" })).toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "Источники" })).toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "Команда" })).not.toBeInTheDocument();
  });

  it("keeps the full navigation and shell scroll regions bounded at 360px", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 360 });
    renderAdmin({ admin_id: 1, full_name: "Root Admin", role: "superadmin", csrf_token: "csrf" });

    const navigation = await screen.findByRole("navigation", { name: /asosiy menyu/i });
    expect(within(navigation).getByRole("link", { name: "Jamoa" })).toBeInTheDocument();
    expect(navigation).toHaveStyle({ overflowX: "auto", maxWidth: "100%" });
    expect(screen.getByTestId("admin-content-scroll")).toHaveStyle({ overflowX: "auto", maxWidth: "100%" });
  });

  it("registers all admin paths while keeping task 12 modules as explicit placeholders", async () => {
    renderAdmin({ admin_id: 1, full_name: "Root Admin", role: "superadmin", csrf_token: "csrf" }, "/admin/sources");

    expect(await screen.findByRole("heading", { name: "Manbalar" })).toBeInTheDocument();
    expect(screen.getByText(/modul keyingi bosqichda ulanadi/i)).toBeInTheDocument();
  });
});

afterEach(() => {
  adminApi.defaults.adapter = originalAdminAdapter;
  setAdminCsrfToken(null);
  useLanguageStore.getState().setLanguage("uz");
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
});
