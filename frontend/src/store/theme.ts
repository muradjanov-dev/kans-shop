import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  hasUserPreference: boolean;
  setTheme: (theme: Theme) => void;
  setSystemTheme: (theme: Theme) => void;
}

function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "light",
      hasUserPreference: false,
      setTheme: (theme) => {
        set({ theme, hasUserPreference: true });
        applyTheme(theme);
      },
      setSystemTheme: (theme) => {
        const state = get();
        if (state.hasUserPreference) {
          applyTheme(state.theme);
          return;
        }
        set({ theme });
        applyTheme(theme);
      },
    }),
    {
      name: "kans-shop-theme",
      partialize: ({ theme, hasUserPreference }) => ({ theme, hasUserPreference }),
      onRehydrateStorage: () => (state) => {
        if (state?.hasUserPreference) applyTheme(state.theme);
      },
    },
  ),
);

export function useTheme(): Pick<ThemeState, "theme" | "setTheme"> {
  const theme = useThemeStore((state) => state.theme);
  const setTheme = useThemeStore((state) => state.setTheme);
  return { theme, setTheme };
}

export function setSystemTheme(theme: Theme): void {
  useThemeStore.getState().setSystemTheme(theme);
}
