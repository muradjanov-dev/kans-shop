import WebApp from "@twa-dev/sdk";

export const isTelegramWebApp = Boolean(WebApp.initData);

export function initTelegramWebApp(): void {
  if (!isTelegramWebApp) return;
  WebApp.ready();
  WebApp.expand();
}

export function telegramLanguageCode(): "uz" | "ru" {
  return WebApp.initDataUnsafe?.user?.language_code === "ru" ? "ru" : "uz";
}

export { WebApp };
