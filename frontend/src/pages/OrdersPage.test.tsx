import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { OrdersPage } from "@/pages/OrdersPage";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

let originalAdapter: typeof api.defaults.adapter;
afterEach(() => {
  if (originalAdapter !== undefined) api.defaults.adapter = originalAdapter;
  originalAdapter = undefined;
});

describe("orders access recovery", () => {
  it("offers account sign-in recovery before fetching private orders", async () => {
    originalAdapter = api.defaults.adapter;
    let orderRequests = 0;
    api.defaults.adapter = async (config) => {
      if (config.url === "/orders") {
        orderRequests += 1;
        return response(config, []);
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`);
    };
    const user = userEvent.setup();

    renderWithProviders(<OrdersPage />, "/orders", true);
    await user.click(screen.getByRole("button", { name: "Kirish" }));

    expect(await screen.findByRole("dialog", { name: "Kans Shop hisobingizga kiring" })).toBeInTheDocument();
    expect(orderRequests).toBe(0);
  });
});
