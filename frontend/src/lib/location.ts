import {
  telegramLocationManager,
  type TelegramLocationData,
  type TelegramLocationManager,
} from "@/lib/telegram";

export interface DeviceLocation {
  latitude: number;
  longitude: number;
  accuracy: number | null;
}

export type LocationFailure = "denied" | "unavailable" | "timeout";

export class LocationError extends Error {
  constructor(readonly reason: LocationFailure) {
    super(`Location ${reason}`);
    this.name = "LocationError";
  }
}

const LOCATION_TIMEOUT_MS = 15_000;

function withTimeout<T>(promise: Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new LocationError("timeout")), LOCATION_TIMEOUT_MS);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

async function fromTelegram(manager: TelegramLocationManager): Promise<DeviceLocation> {
  if (!manager.isInited && manager.init) {
    await withTimeout(new Promise<void>((resolve) => {
      manager.init?.(() => resolve());
    }));
  }
  if (manager.isLocationAvailable === false) throw new LocationError("unavailable");
  const data = await withTimeout(new Promise<TelegramLocationData | null>((resolve) => {
    manager.getLocation?.(resolve);
  }));
  // Telegram answers null when the customer declines or has location off for this bot.
  if (!data) throw new LocationError("denied");
  return { latitude: data.latitude, longitude: data.longitude, accuracy: data.horizontal_accuracy ?? null };
}

function fromBrowser(): Promise<DeviceLocation> {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return Promise.reject(new LocationError("unavailable"));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
      }),
      (error) => reject(new LocationError(
        error.code === error.PERMISSION_DENIED ? "denied" : error.code === error.TIMEOUT ? "timeout" : "unavailable",
      )),
      { enableHighAccuracy: true, timeout: LOCATION_TIMEOUT_MS, maximumAge: 60_000 },
    );
  });
}

/**
 * The customer's current position: Telegram's location access first (inside the Mini App),
 * then the browser's geolocation. A refusal in Telegram is final; other Telegram failures
 * (old client, no GPS bridge) fall back to the browser.
 */
export async function getDeviceLocation(): Promise<DeviceLocation> {
  const manager = telegramLocationManager();
  if (manager) {
    try {
      return await fromTelegram(manager);
    } catch (error) {
      if (error instanceof LocationError && error.reason === "denied") throw error;
    }
  }
  return fromBrowser();
}

/** Opens Telegram's per-bot location permission screen, when available. */
export function openLocationSettings(): boolean {
  const manager = telegramLocationManager();
  if (!manager?.openSettings) return false;
  try {
    manager.openSettings();
    return true;
  } catch {
    return false;
  }
}

export function formatCoordinate(value: number): string {
  return value.toFixed(6);
}

export function mapLink(latitude: string, longitude: string): string {
  return `https://maps.google.com/?q=${latitude},${longitude}`;
}
