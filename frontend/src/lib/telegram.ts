// The Telegram bridge script in index.html owns `window.Telegram.WebApp`, and that global is
// the source of truth here.
//
// We deliberately do NOT use @twa-dev/sdk's default export: in this build its object carries
// no `ready`/`expand`/`onEvent`, so calling them threw `TypeError: ready is not a function`.
// Those calls sit behind the isTelegramWebApp() guard, so a plain browser never reached them
// and only real Telegram clients crashed - the throw escaped the auth effect, took down the
// whole React tree, and left users staring at a blank page. Reading the live global also
// avoids shipping the SDK's bundled second copy of the bridge, which fought with the script
// tag over the same global.

interface TelegramWebApp {
  initData?: string;
  initDataUnsafe?: {
    user?: { id?: number; first_name?: string; last_name?: string; language_code?: string };
  };
  colorScheme?: "light" | "dark";
  ready?: () => void;
  expand?: () => void;
  onEvent?: (event: string, handler: () => void) => void;
  openLink?: (url: string) => void;
}

function webApp(): TelegramWebApp | undefined {
  return (window as unknown as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp;
}

// Telegram's bridge can populate initData a moment after our bundle evaluates, so this must be
// read fresh at call time - a value cached at module scope permanently reads as "false" on a
// slow-to-initialize WebView.
export function isTelegramWebApp(): boolean {
  return Boolean(webApp()?.initData);
}

function applyColorScheme(): void {
  const isDark = isTelegramWebApp()
    ? webApp()?.colorScheme === "dark"
    : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", isDark);
}

let themeListenerBound = false;

export function initTelegramWebApp(): void {
  // Called from a retry loop, so it must stay safe to invoke repeatedly, and no failure here
  // is worth taking the app down for - the storefront is fully usable without these.
  try {
    applyColorScheme();
    const app = webApp();
    if (!app || !isTelegramWebApp()) return;

    app.ready?.();
    app.expand?.();
    if (!themeListenerBound && app.onEvent) {
      app.onEvent("themeChanged", applyColorScheme);
      themeListenerBound = true;
    }
  } catch (error) {
    console.error("Telegram WebApp init failed (continuing without it)", error);
  }
}

export function telegramLanguageCode(): "uz" | "ru" {
  return webApp()?.initDataUnsafe?.user?.language_code === "ru" ? "ru" : "uz";
}

export function telegramInitData(): string {
  return webApp()?.initData ?? "";
}

// Kept as a `WebApp`-shaped object so call sites read naturally. The getters resolve against
// the live global on every access rather than a snapshot taken at import time.
export const WebApp = {
  get initData(): string {
    return webApp()?.initData ?? "";
  },
  get initDataUnsafe(): NonNullable<TelegramWebApp["initDataUnsafe"]> {
    return webApp()?.initDataUnsafe ?? {};
  },
  openLink(url: string): void {
    const app = webApp();
    try {
      if (app?.openLink) {
        app.openLink(url);
        return;
      }
    } catch {
      // fall through to a normal navigation
    }
    window.open(url, "_blank", "noopener,noreferrer");
  },
};
