import { create } from "zustand";
import { persist } from "zustand/middleware";

export function userIdFromAccessToken(token: string | null): string | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="))) as {
      sub?: string | number;
    };
    if (typeof decoded.sub === "string" && decoded.sub.trim()) return decoded.sub;
    if (typeof decoded.sub === "number" && Number.isFinite(decoded.sub)) return String(decoded.sub);
  } catch {
    // An unreadable subject cannot be used as a private-cache identity.
  }
  return null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  isAdmin: boolean;
  userId: string | null;
  authEpoch: number;
  setTokens: (tokens: { access_token: string; refresh_token: string; is_admin: boolean }) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      isAdmin: false,
      userId: null,
      authEpoch: 0,
      setTokens: ({ access_token, refresh_token, is_admin }) => {
        const previous = get();
        const userId = userIdFromAccessToken(access_token);
        const startsSession = !previous.accessToken && Boolean(access_token);
        set({
          accessToken: access_token,
          refreshToken: refresh_token,
          isAdmin: is_admin,
          userId,
          authEpoch:
            previous.authEpoch + (startsSession || previous.userId !== userId ? 1 : 0),
        });
      },
      clear: () => {
        const previous = get();
        set({
          accessToken: null,
          refreshToken: null,
          isAdmin: false,
          userId: null,
          authEpoch: previous.authEpoch + (previous.accessToken || previous.refreshToken ? 1 : 0),
        });
      },
    }),
    {
      name: "kans-shop-auth",
      partialize: ({ accessToken, refreshToken, isAdmin }) => ({
        accessToken,
        refreshToken,
        isAdmin,
      }) as AuthState,
      merge: (persisted, current) => {
        const saved = persisted as Partial<AuthState>;
        return {
          ...current,
          ...saved,
          userId: userIdFromAccessToken(saved.accessToken ?? current.accessToken),
          authEpoch: current.authEpoch,
        };
      },
    },
  ),
);
