import axios from "axios";
import { API_BASE_URL } from "@/lib/api";
import { isTelegramWebApp, telegramInitData } from "@/lib/telegram";
import { telegramSessionState as state } from "@/lib/telegramSessionState";
import { useAuthStore } from "@/store/auth";
import type { TokenPair } from "@/types/api";

/** After a refused sign-in, wait this long before trying again on our own. */
export const TELEGRAM_RETRY_AFTER_MS = 30_000;

/**
 * Inside the Telegram Mini App the customer is identified by Telegram itself and is never
 * asked for a login code. This signs in, or renews the session, with the app's signed
 * initData: on every app open, and again whenever the stored session runs out.
 *
 * Resolves true once fresh tokens are stored. Concurrent callers share one request; after
 * a refusal, background retries pause briefly (`force` skips the pause for a tap).
 */
export function signInWithTelegram({ force = false }: { force?: boolean } = {}): Promise<boolean> {
  if (!isTelegramWebApp()) return Promise.resolve(false);
  if (state.inFlight) return state.inFlight;
  if (!force && Date.now() - state.lastFailureAt < TELEGRAM_RETRY_AFTER_MS) return Promise.resolve(false);
  state.inFlight = axios
    .post<TokenPair>(`${API_BASE_URL}/auth/telegram`, { init_data: telegramInitData() })
    .then(({ data }) => {
      // Telegram's identity wins inside Telegram: the app offers no other way to sign in.
      useAuthStore.getState().setTokens(data);
      state.lastFailureAt = 0;
      return true;
    })
    .catch(() => {
      state.lastFailureAt = Date.now();
      return false;
    })
    .finally(() => {
      state.inFlight = null;
    });
  return state.inFlight;
}
