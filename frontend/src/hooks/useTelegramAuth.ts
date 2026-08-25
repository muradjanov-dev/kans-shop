import { useEffect, useState } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/lib/api";
import { initTelegramWebApp, isTelegramWebApp, telegramLanguageCode, WebApp } from "@/lib/telegram";
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
        .post<TokenPair>(`${API_BASE_URL}/auth/telegram`, { init_data: WebApp.initData })
        .then(({ data }) => {
          if (cancelled) return;
          setTokens(data);
          setStatus("ready");
        })
        .catch(() => {
          if (!cancelled) setStatus("unavailable");
        });
    }

    // Some Telegram clients (notably Desktop) populate WebApp.initData a beat after our
    // bundle evaluates - @twa-dev/sdk snapshots window.Telegram.WebApp once at import time,
    // so a single early check can permanently read "not available". Poll briefly before
    // giving up.
    let attempts = 0;
    const maxAttempts = 20; // ~2s at 100ms
    function poll() {
      if (cancelled) return;
      initTelegramWebApp();
      if (isTelegramWebApp()) {
        authenticate();
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
