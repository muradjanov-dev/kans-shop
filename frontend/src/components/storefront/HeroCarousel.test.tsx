import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { ShowcaseProduct } from "@/types/api";
import { CAROUSEL_AUTOPLAY_MS, HeroCarousel } from "./HeroCarousel";

const showcase = (id: number, overrides: Partial<ShowcaseProduct> = {}): ShowcaseProduct => ({
  id,
  name_uz: `Daftar ${id}`,
  name_ru: `Тетрадь ${id}`,
  price: "12000.00",
  old_price: null,
  image_url: null,
  is_featured: false,
  min_order_qty: 1,
  available: true,
  ...overrides,
});

function mockShowcase(items: ShowcaseProduct[]) {
  vi.spyOn(api, "get").mockImplementation(async (url: string, _config?: AxiosRequestConfig) => {
    if (url === "/catalog/showcase") return { data: items, status: 200, statusText: "OK", headers: {}, config: {} } as never;
    if (url === "/cart") return { data: { items: [], subtotal: "0", items_count: 0 }, status: 200, statusText: "OK", headers: {}, config: {} } as never;
    throw new Error(`Unexpected GET ${url}`);
  });
}

beforeEach(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("HeroCarousel", () => {
  it("opens on the brand slide and steps through every product", async () => {
    mockShowcase([showcase(1, { is_featured: true, old_price: "15000.00" }), showcase(2)]);
    const user = userEvent.setup();
    renderWithProviders(<HeroCarousel />, "/", true);

    expect(screen.getByText("Katta g‘oyalar kichik narsalardan boshlanadi.")).toBeInTheDocument();
    expect(await screen.findByText("1 / 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Keyingi slayd" }));
    expect(screen.getByRole("link", { name: "Daftar 1" })).toHaveAttribute("href", "/product/1");
    expect(screen.getByText("Tavsiya etilgan")).toBeInTheDocument();
    expect(screen.getByText("15 000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Savatga qo‘shish" })).toBeInTheDocument();
    expect(screen.getByText("2 / 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Keyingi slayd" }));
    expect(screen.getByRole("link", { name: "Daftar 2" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Keyingi slayd" }));
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Oldingi slayd" }));
    expect(screen.getByRole("link", { name: "Daftar 2" })).toBeInTheDocument();
  });

  it("jumps to an upcoming product from its thumbnail", async () => {
    mockShowcase([showcase(1), showcase(2), showcase(3)]);
    const user = userEvent.setup();
    renderWithProviders(<HeroCarousel />, "/", true);

    await user.click(await screen.findByRole("button", { name: "Daftar 3 mahsulotiga o‘tish" }));

    expect(screen.getByRole("link", { name: "Daftar 3" })).toBeInTheDocument();
    expect(screen.getByText("4 / 4")).toBeInTheDocument();
  });

  it("plays on its own and stops when the customer pauses it", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockShowcase([showcase(1), showcase(2)]);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<HeroCarousel />, "/", true);
    expect(await screen.findByText("1 / 3")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_AUTOPLAY_MS + 10);
    });
    await waitFor(() => expect(screen.getByText("2 / 3")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Aylanishni to‘xtatish" }));
    expect(screen.getByRole("button", { name: "Aylanishni davom ettirish" })).toHaveAttribute("aria-pressed", "true");
    await user.unhover(screen.getByRole("region", { name: "Barcha mahsulotlar karuseli" }));
    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_AUTOPLAY_MS * 3);
    });
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("keeps the brand slide alone when no products load", async () => {
    vi.spyOn(api, "get").mockRejectedValue(new Error("offline"));
    renderWithProviders(<HeroCarousel />, "/", true);

    expect(screen.getByText("Katta g‘oyalar kichik narsalardan boshlanadi.")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keyingi slayd" })).toBeDisabled();
  });
});
