import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  isAdmin: boolean;
  setTokens: (tokens: { access_token: string; refresh_token: string; is_admin: boolean }) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      isAdmin: false,
      setTokens: ({ access_token, refresh_token, is_admin }) =>
        set({ accessToken: access_token, refreshToken: refresh_token, isAdmin: is_admin }),
      clear: () => set({ accessToken: null, refreshToken: null, isAdmin: false }),
    }),
    { name: "kans-shop-auth" },
  ),
);
