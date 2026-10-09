import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Language = "uz" | "ru";

interface LanguageState {
  language: Language;
  hasUserPreference: boolean;
  setLanguage: (language: Language) => void;
  setTelegramLanguage: (language: Language) => void;
}

export const useLanguageStore = create<LanguageState>()(
  persist(
    (set) => ({
      language: "uz",
      hasUserPreference: false,
      setLanguage: (language) => set({ language, hasUserPreference: true }),
      setTelegramLanguage: (language) => set((state) => (
        state.hasUserPreference ? state : { language }
      )),
    }),
    {
      name: "kans-shop-language",
      partialize: ({ language, hasUserPreference }) => ({ language, hasUserPreference }),
      merge: (persisted, current) => {
        const saved = persisted as Partial<LanguageState>;
        const savedLanguage = saved.language;
        return {
          ...current,
          language: savedLanguage === "ru" ? "ru" : "uz",
          hasUserPreference: saved.hasUserPreference ?? typeof savedLanguage === "string",
        };
      },
    },
  ),
);
