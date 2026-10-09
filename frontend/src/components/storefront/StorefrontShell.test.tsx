import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "@/App";
import { useLanguageStore } from "@/store/language";
import storefrontStyles from "@/index.css?inline";

vi.mock("@/hooks/useTelegramAuth", () => ({ useTelegramAuth: () => "ready" }));

function renderStorefront(
  initialEntry = "/",
  seedQueries?: (queryClient: QueryClient) => void,
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 60_000 },
      mutations: { retry: false },
    },
  });
  queryClient.setQueryData(["public-settings"], {
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
  });
  seedQueries?.(queryClient);

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("responsive storefront shell", () => {
  it("shows desktop shopping links and four mobile destinations", () => {
    renderStorefront("/orders");

    const desktopNavigation = screen.getByRole("navigation", { name: "Asosiy menyu" });
    const mobileNavigation = screen.getByRole("navigation", { name: "Mobil menyu" });

    expect(within(desktopNavigation).getByRole("link", { name: "Katalog" })).toHaveAttribute("href", "/");
    expect(within(desktopNavigation).getByRole("link", { name: "Buyurtmalar" })).toHaveAttribute("href", "/orders");
    expect(within(desktopNavigation).getByRole("link", { name: "Savat" })).toHaveAttribute("href", "/cart");
    expect(within(desktopNavigation).getByRole("link", { name: "Profil" })).toHaveAttribute("href", "/profile");
    expect(within(mobileNavigation).getAllByRole("link")).toHaveLength(4);
    expect(within(mobileNavigation).getByRole("link", { name: "Buyurtmalar" })).toHaveAttribute("aria-current", "page");
    expect(desktopNavigation).toHaveClass("hidden", "lg:flex");
    expect(mobileNavigation).toHaveClass("lg:hidden");
    expect(screen.getByLabelText("Mahsulotlarni qidirish")).toBeInTheDocument();
  });

  it("uses two product columns at narrow widths and four at the wide breakpoint", async () => {
    const product = {
      id: 12,
      category_id: 1,
      name_uz: "Daftar",
      name_ru: "Тетрадь",
      description_uz: null,
      description_ru: null,
      sku: "NB-12",
      price: "450",
      old_price: null,
      stock_qty: 4,
      unit: "dona" as const,
      min_order_qty: 1,
      is_active: true,
      is_featured: false,
      lot_url: null,
      views_count: 0,
      sold_count: 0,
      images: [],
    };
    const category = {
      id: 1,
      parent_id: null,
      name_uz: "Daftarlar",
      name_ru: "Тетради",
      slug: "notebooks",
      description_uz: null,
      description_ru: null,
      image_url: null,
      sort_order: 1,
      products_count: 1,
    };
    renderStorefront("/", (queryClient) => {
      queryClient.setQueryData(["categories", null], [category]);
      queryClient.setQueryData(["category-products", 1, 1], {
        items: [product],
        total: 1,
        page: 1,
        limit: 12,
        total_pages: 1,
      });
    });

    const productLink = await screen.findByRole("link", { name: /Daftar/ });
    expect(productLink.parentElement).toHaveClass("grid-cols-2", "xl:grid-cols-4");
  });

  it("keeps favorites and addresses reachable from the active profile section", () => {
    renderStorefront("/profile");

    const mobileNavigation = screen.getByRole("navigation", { name: "Mobil menyu" });
    expect(within(mobileNavigation).getByRole("link", { name: "Profil" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Hisobingiz" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sevimlilar" })).toHaveAttribute("href", "/favorites");
    expect(screen.getByRole("link", { name: "Manzillar" })).toHaveAttribute("href", "/profile/addresses");
    expect(within(screen.getByRole("region", { name: "Hisobingiz" })).getByRole("button", { name: "Kirish" })).toBeInTheDocument();
  });

  it("switches the language with an explicit accessible label", async () => {
    const user = userEvent.setup();
    renderStorefront();

    await user.selectOptions(screen.getByRole("combobox", { name: "Til" }), "ru");

    const desktopNavigation = screen.getByRole("navigation", { name: "Главное меню" });
    expect(within(desktopNavigation).getByRole("link", { name: "Каталог" })).toBeInTheDocument();
    expect(within(desktopNavigation).getByRole("link", { name: "Профиль" })).toBeInTheDocument();
    expect(useLanguageStore.getState().language).toBe("ru");
    expect(JSON.parse(window.localStorage.getItem("kans-shop-language") ?? "{}").state.language).toBe("ru");
  });

  it("keeps sign-in dialog controls at least 44px tall", async () => {
    const user = userEvent.setup();
    renderStorefront();
    await user.click(screen.getByRole("button", { name: "Kirish" }));

    const dialog = screen.getByRole("dialog", { name: "Kans Shop hisobingizga kiring" });
    expect(within(dialog).getByLabelText("Kirish kodi")).toHaveClass("min-h-11");
    expect(within(dialog).getByRole("link", { name: "Telegram botni ochish" })).toHaveClass("min-h-11");
    expect(within(dialog).getByRole("button", { name: "Kirish" })).toHaveClass("min-h-11");
    expect(within(dialog).getByRole("button", { name: "Bekor qilish" })).toHaveClass("min-h-11");
  });

  it("provides 44px keyboard controls, a visible focus affordance, and reduced-motion CSS", async () => {
    const user = userEvent.setup();
    renderStorefront();

    const catalogLink = within(screen.getByRole("navigation", { name: "Asosiy menyu" })).getByRole("link", { name: "Katalog" });
    const languagePicker = screen.getByRole("combobox", { name: "Til" });
    const themeButton = screen.getByRole("button", { name: "Qorong‘i mavzuni yoqish" });
    expect(catalogLink).toHaveClass("min-h-11", "min-w-11", "focus-visible:outline-2");
    expect(languagePicker).toHaveClass("min-h-11", "focus-visible:outline-2");
    expect(languagePicker.parentElement).not.toHaveClass("sr-only");
    expect(themeButton).toHaveClass("min-h-11", "min-w-11", "focus-visible:outline-2");

    await user.tab();
    expect(document.activeElement).toHaveFocus();
    expect(document.activeElement).toHaveClass("focus-visible:outline-2");

    const styleElement = document.createElement("style");
    styleElement.textContent = storefrontStyles;
    document.head.append(styleElement);
    const rules = Array.from(styleElement.sheet?.cssRules ?? []).flatMap((rule) => {
      if (rule instanceof CSSMediaRule) return Array.from(rule.cssRules).concat(rule);
      return [rule];
    });
    styleElement.remove();
    expect(rules.some((rule) => rule instanceof CSSStyleRule && rule.selectorText.includes(":focus-visible"))).toBe(true);
    expect(rules.some((rule) => rule instanceof CSSMediaRule && rule.conditionText.includes("prefers-reduced-motion"))).toBe(true);
  });
});
