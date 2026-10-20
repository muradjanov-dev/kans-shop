import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from "axios";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { renderWithProviders } from "@/test/renderWithProviders";
import { LocationPicker } from "./LocationPicker";
import type { CheckoutLocation } from "./useCheckoutFlow";

const originalAdapter = api.defaults.adapter;
const originalGeolocation = Object.getOwnPropertyDescriptor(navigator, "geolocation");

type TelegramWindow = Window & { Telegram?: unknown };

function response<T>(config: Parameters<AxiosAdapter>[0], data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: new AxiosHeaders(), config };
}

function mockGeocoder(address: string | null) {
  const calls: Array<Record<string, unknown>> = [];
  api.defaults.adapter = async (config) => {
    calls.push({ url: config.url, ...(config.params as Record<string, unknown>) });
    return response(config, { address, latitude: "41.285600", longitude: "69.203400" });
  };
  return calls;
}

function mockBrowserPosition(result: { latitude: number; longitude: number } | { deniedCode: number }) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: (
        success: (position: { coords: { latitude: number; longitude: number; accuracy: number } }) => void,
        failure: (error: { code: number; PERMISSION_DENIED: number; TIMEOUT: number }) => void,
      ) => {
        if ("deniedCode" in result) failure({ code: result.deniedCode, PERMISSION_DENIED: 1, TIMEOUT: 3 });
        else success({ coords: { ...result, accuracy: 12 } });
      },
    },
  });
}

function Harness({ initialAddress = "" }: { initialAddress?: string }) {
  const [address, setAddress] = useState(initialAddress);
  const [location, setLocation] = useState<CheckoutLocation | null>(null);
  return (
    <>
      <LocationPicker address={address} disabled={false} location={location} onAddress={setAddress} onLocation={setLocation} />
      <output data-testid="address">{address}</output>
      <output data-testid="location">{location ? `${location.latitude},${location.longitude}` : "none"}</output>
    </>
  );
}

afterEach(() => {
  api.defaults.adapter = originalAdapter;
  if (originalGeolocation) Object.defineProperty(navigator, "geolocation", originalGeolocation);
  else delete (navigator as { geolocation?: unknown }).geolocation;
  delete (window as TelegramWindow).Telegram;
  vi.restoreAllMocks();
});

describe("delivery location picker", () => {
  it("attaches the phone's position and fills in the detected address", async () => {
    mockBrowserPosition({ latitude: 41.2856, longitude: 69.2034 });
    const calls = mockGeocoder("Yuqori Darxon ko'chasi 12, Chilonzor tumani, Toshkent");
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(screen.getByRole("button", { name: "Lokatsiyamni yuborish" }));

    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("Yuqori Darxon ko'chasi 12, Chilonzor tumani, Toshkent"));
    expect(screen.getByTestId("location")).toHaveTextContent("41.285600,69.203400");
    expect(screen.getByText("Lokatsiya biriktirildi")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xaritada ko'rish" })).toHaveAttribute("href", "https://maps.google.com/?q=41.285600,69.203400");
    expect(calls).toEqual([{ url: "/geocode/reverse", lat: "41.285600", lon: "69.203400", lang: "uz" }]);
  });

  it("offers the detected address instead of overwriting what the customer typed", async () => {
    mockBrowserPosition({ latitude: 41.2856, longitude: 69.2034 });
    mockGeocoder("Yuqori Darxon ko'chasi 12");
    const user = userEvent.setup();
    renderWithProviders(<Harness initialAddress="Chilonzor 9, 15-uy" />);

    await user.click(screen.getByRole("button", { name: "Lokatsiyamni yuborish" }));

    expect(await screen.findByText(/Aniqlangan manzil: Yuqori Darxon ko'chasi 12/)).toBeInTheDocument();
    expect(screen.getByTestId("address")).toHaveTextContent("Chilonzor 9, 15-uy");
    await user.click(screen.getByRole("button", { name: "Shu manzilni qo'yish" }));
    expect(screen.getByTestId("address")).toHaveTextContent("Yuqori Darxon ko'chasi 12");
  });

  it("uses Telegram's location access inside the Mini App", async () => {
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition } });
    (window as TelegramWindow).Telegram = {
      WebApp: {
        initData: "query_id=test",
        isVersionAtLeast: () => true,
        LocationManager: {
          isInited: true,
          isLocationAvailable: true,
          getLocation: (callback: (data: { latitude: number; longitude: number }) => void) => callback({ latitude: 41.31, longitude: 69.28 }),
        },
      },
    };
    mockGeocoder(null);
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(screen.getByRole("button", { name: "Lokatsiyamni yuborish" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("41.310000,69.280000"));
    expect(getCurrentPosition).not.toHaveBeenCalled();
    expect(await screen.findByText(/Manzilni avtomatik aniqlab bo'lmadi/)).toBeInTheDocument();
  });

  it("explains a refused permission", async () => {
    mockBrowserPosition({ deniedCode: 1 });
    const user = userEvent.setup();
    renderWithProviders(<Harness />);

    await user.click(screen.getByRole("button", { name: "Lokatsiyamni yuborish" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Lokatsiyaga ruxsat berilmagan.");
    expect(screen.getByTestId("location")).toHaveTextContent("none");
  });
});
