import { useState } from "react";
import { api } from "@/lib/api";
import { useTranslate } from "@/lib/i18n";
import {
  formatCoordinate,
  getDeviceLocation,
  LocationError,
  mapLink,
  openLocationSettings,
} from "@/lib/location";
import { isTelegramWebApp, WebApp } from "@/lib/telegram";
import { useLanguageStore } from "@/store/language";
import type { CheckoutLocation } from "./useCheckoutFlow";

type Status = "idle" | "locating" | "resolving" | "denied" | "failed";

interface ReverseGeocodeResponse {
  address: string | null;
  latitude: string;
  longitude: string;
}

/**
 * "Send my location" for delivery: takes the position from Telegram (or the browser), asks
 * the shop API for the written address and fills it in. The coordinates travel with the
 * order, so admins and the courier also get an exact map link.
 */
export function LocationPicker({
  address,
  disabled,
  location,
  onAddress,
  onLocation,
}: {
  address: string;
  disabled: boolean;
  location: CheckoutLocation | null;
  onAddress: (address: string) => void;
  onLocation: (location: CheckoutLocation | null) => void;
}) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const [status, setStatus] = useState<Status>("idle");
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [addressMissing, setAddressMissing] = useState(false);

  async function share(): Promise<void> {
    setStatus("locating");
    setSuggestion(null);
    setAddressMissing(false);
    let next: CheckoutLocation;
    try {
      const point = await getDeviceLocation();
      next = { latitude: formatCoordinate(point.latitude), longitude: formatCoordinate(point.longitude) };
    } catch (error) {
      setStatus(error instanceof LocationError && error.reason === "denied" ? "denied" : "failed");
      return;
    }
    onLocation(next);
    setStatus("resolving");
    try {
      const { data } = await api.get<ReverseGeocodeResponse>("/geocode/reverse", {
        params: { lat: next.latitude, lon: next.longitude, lang: language },
      });
      if (!data.address) {
        setAddressMissing(true);
      } else if (!address.trim()) {
        onAddress(data.address);
      } else if (data.address !== address.trim()) {
        // Never overwrite what the customer typed: offer the detected address instead.
        setSuggestion(data.address);
      }
    } catch {
      setAddressMissing(true);
    }
    setStatus("idle");
  }

  function openMap(event: React.MouseEvent<HTMLAnchorElement>): void {
    if (!location) return;
    event.preventDefault();
    WebApp.openLink(mapLink(location.latitude, location.longitude));
  }

  return (
    <div className="location-picker mb-5 flex flex-col gap-2 rounded-2xl border border-dashed border-[var(--line)] bg-[var(--paper)] p-3 dark:border-white/15">
      {location ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--soft)] px-3 py-1.5 font-semibold text-brand dark:text-white">
            <PinIcon />
            {t("checkout.location.attached")}
          </span>
          <a
            className="font-medium text-brand underline underline-offset-2 dark:text-white"
            href={mapLink(location.latitude, location.longitude)}
            onClick={openMap}
            rel="noreferrer"
            target="_blank"
          >
            {t("checkout.location.view_map")}
          </a>
          <button
            className="min-h-11 px-1 font-medium text-[var(--muted)] underline underline-offset-2 disabled:opacity-50"
            disabled={disabled}
            onClick={() => {
              onLocation(null);
              setSuggestion(null);
              setAddressMissing(false);
            }}
            type="button"
          >
            {t("checkout.location.remove")}
          </button>
        </div>
      ) : (
        <button
          className="secondary-button min-h-12 w-full gap-2 disabled:opacity-60"
          disabled={disabled || status === "locating"}
          onClick={() => void share()}
          type="button"
        >
          <PinIcon />
          {status === "locating" ? t("checkout.location.locating") : t("checkout.location.share")}
        </button>
      )}
      <div aria-live="polite" className="text-xs leading-5">
        {status === "resolving" && <p className="text-[var(--muted)]">{t("checkout.location.resolving")}</p>}
        {suggestion && (
          <p className="text-[var(--ink)] dark:text-slate-100">
            {t("checkout.location.suggestion", { address: suggestion })}{" "}
            <button
              className="min-h-11 font-semibold text-brand underline underline-offset-2 dark:text-white"
              onClick={() => {
                onAddress(suggestion);
                setSuggestion(null);
              }}
              type="button"
            >
              {t("checkout.location.use_suggestion")}
            </button>
          </p>
        )}
        {addressMissing && location && <p className="text-amber-700 dark:text-amber-300">{t("checkout.location.no_address")}</p>}
        {status === "denied" && (
          <p className="text-red-600 dark:text-red-300" role="alert">
            {t("checkout.location.denied")}{" "}
            {isTelegramWebApp() && (
              <button
                className="min-h-11 font-semibold underline underline-offset-2"
                onClick={() => openLocationSettings()}
                type="button"
              >
                {t("checkout.location.open_settings")}
              </button>
            )}
          </p>
        )}
        {status === "failed" && <p className="text-red-600 dark:text-red-300" role="alert">{t("checkout.location.failed")}</p>}
        {!location && status === "idle" && <p className="text-[var(--muted)]">{t("checkout.location.hint")}</p>}
      </div>
    </div>
  );
}

function PinIcon() {
  return (
    <svg aria-hidden="true" className="size-4 shrink-0" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2" viewBox="0 0 24 24">
      <path d="M12 21s-6.5-5.8-6.5-11A6.5 6.5 0 0 1 18.5 10c0 5.2-6.5 11-6.5 11Z" />
      <circle cx="12" cy="10" r="2.4" />
    </svg>
  );
}
