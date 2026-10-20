import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/renderWithProviders";
import { StorefrontHeader } from "./StorefrontHeader";

type TelegramWindow = Window & { Telegram?: { WebApp?: { initData?: string } } };

afterEach(() => {
  delete (window as TelegramWindow).Telegram;
});

describe("StorefrontHeader account controls", () => {
  it("offers account switching in a normal browser", () => {
    renderWithProviders(<StorefrontHeader isAuthenticated />, "/", true);

    expect(screen.getByRole("button", { name: "Hisobni almashtirish" })).toBeInTheDocument();
  });

  it("hides code login controls inside Telegram, where the Mini App signs in by itself", () => {
    (window as TelegramWindow).Telegram = { WebApp: { initData: "query_id=test&user=%7B%7D" } };

    renderWithProviders(<StorefrontHeader isAuthenticated />, "/", true);

    expect(screen.queryByRole("button", { name: "Hisobni almashtirish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Kirish" })).toBeNull();
  });
});
