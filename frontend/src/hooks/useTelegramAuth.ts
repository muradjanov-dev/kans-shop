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
    initTelegramWebApp();
    if (!isTelegramWebApp()) {
      setStatus("unavailable");
      return;
    }

    setLanguage(telegramLanguageCode());

    if (accessToken) {
      setStatus("ready");
      return;
    }

    let cancelled = false;
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

    return () => {
      cancelled = true;
    };
    // Intentionally runs once on mount only — re-running on every accessToken change would
    // re-authenticate in a loop right after setTokens() sets it.
  }, []);

  return status;
}
