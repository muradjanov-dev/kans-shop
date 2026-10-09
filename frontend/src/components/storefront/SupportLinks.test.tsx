import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SupportLinks } from "@/components/storefront/SupportLinks";
import type { PublicSettings } from "@/types/api";

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

describe("public support links", () => {
  it("keeps malformed usernames and phone values out of links", () => {
    renderSupportLinks({ support_username: "not a username", shop_phone: "++", work_hours: "09:00-18:00" });

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("09:00-18:00")).toBeInTheDocument();
  });

  it("renders nothing when every optional support value is empty or invalid", () => {
    const { container } = renderSupportLinks({ support_username: "x", shop_phone: "++", work_hours: " " });

    expect(container.firstChild).toBeNull();
  });

  it("links a valid Telegram username and normalized Uzbekistan phone", () => {
    renderSupportLinks({ support_username: "@kans_shop", shop_phone: "90 123 45 67", work_hours: "09:00-18:00" });

    expect(screen.getByRole("link", { name: "Telegram yordami" })).toHaveAttribute("href", "https://t.me/kans_shop");
    expect(screen.getByRole("link", { name: "+998901234567" })).toHaveAttribute("href", "tel:+998901234567");
    expect(screen.queryByText("09:00-18:00")).not.toBeInTheDocument();
  });
});
