import { useEffect, useState } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/lib/api";
import {
  initTelegramWebApp,
  isTelegramWebApp,
  telegramInitData,
  telegramLanguageCode,
} from "@/lib/telegram";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";
import type { TokenPair } from "@/types/api";

type AuthStatus = "pending" | "ready" | "unavailable";

export function useTelegramAuth(): AuthStatus {
  const [status, setStatus] = useState<AuthStatus>("pending");
  const setTokens = useAuthStore((state) => state.setTokens);
  const accessToken = useAuthStore((state) => state.accessToken);
  const setLanguage = useLanguageStore((state) => state.setLanguage);

  useEffect(() => {
    let cancelled = false;

    function authenticate() {
      setLanguage(telegramLanguageCode());

      if (accessToken) {
        setStatus("ready");
        return;
      }

      axios
        .post<TokenPair>(`${API_BASE_URL}/auth/telegram`, { init_data: telegramInitData() })
        .then(({ data }) => {
          if (cancelled) return;
          setTokens(data);
          setStatus("ready");
        })
        .catch(() => {
          if (!cancelled) setStatus("unavailable");
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
