import WebApp from "@twa-dev/sdk";

// Telegram's bridge script can populate window.Telegram.WebApp.initData a moment after
// our bundle evaluates, so this must be read fresh at call time rather than cached as a
// module-level const - otherwise a slow-to-initialize WebView permanently reads as "false".
export function isTelegramWebApp(): boolean {
  return Boolean(WebApp.initData);
}

export function initTelegramWebApp(): void {
  if (!isTelegramWebApp()) return;
  WebApp.ready();
  WebApp.expand();
}

export function telegramLanguageCode(): "uz" | "ru" {
  return WebApp.initDataUnsafe?.user?.language_code === "ru" ? "ru" : "uz";
}

export { WebApp };
