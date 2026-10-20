import { useEffect, useState } from "react";
import {
  initTelegramWebApp,
  isTelegramWebApp,
  telegramLanguageCode,
} from "@/lib/telegram";
import { signInWithTelegram } from "@/lib/telegramSession";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";

type AuthStatus = "pending" | "ready" | "unavailable";

export function useTelegramAuth(): AuthStatus {
  const [status, setStatus] = useState<AuthStatus>("pending");
  const accessToken = useAuthStore((state) => state.accessToken);
  const setTelegramLanguage = useLanguageStore((state) => state.setTelegramLanguage);

  useEffect(() => {
    let cancelled = false;

    function authenticate() {
      setTelegramLanguage(telegramLanguageCode());

      if (accessToken) {
        // Show the shop at once and renew the stored session from Telegram behind it. A
        // session saved weeks ago would otherwise run out mid-visit and leave the customer a
        // guest who gets asked for a login code inside Telegram.
        setStatus("ready");
        void signInWithTelegram({ force: true });
        return;
      }

      void signInWithTelegram({ force: true }).then((signedIn) => {
        if (!cancelled) setStatus(signedIn ? "ready" : "unavailable");
      });
    }

    // Some Telegram clients (notably Desktop) populate initData a beat after our bundle
    // evaluates, so a single early check can read "not available" for a session that is in
    // fact inside Telegram. Poll briefly before giving up.
    //
    // Every iteration is wrapped: an exception escaping here used to leave `status` pinned to
    // "pending" forever, which renders nothing but a spinner and never recovers. Falling
    // through to "unavailable" keeps the storefront browsable instead.
    let attempts = 0;
    const maxAttempts = 20; // ~2s at 100ms
    function poll() {
      if (cancelled) return;
      try {
        initTelegramWebApp();
        if (isTelegramWebApp()) {
          authenticate();
          return;
        }
        if (!(window as unknown as { Telegram?: { WebApp?: unknown } }).Telegram?.WebApp) {
          setStatus("unavailable");
          return;
        }
      } catch (error) {
        console.error("Telegram init check failed", error);
        setStatus("unavailable");
        return;
      }
      attempts += 1;
      if (attempts >= maxAttempts) {
        setStatus("unavailable");
        return;
      }
      setTimeout(poll, 100);
    }
    poll();

    return () => {
      cancelled = true;
    };
    // Intentionally runs once on mount only — re-running on every accessToken change would
    // re-authenticate in a loop right after setTokens() sets it.
  }, []);

  return status;
}
