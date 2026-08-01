import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Language = "uz" | "ru";

interface LanguageState {
  language: Language;
  setLanguage: (language: Language) => void;
}

export const useLanguageStore = create<LanguageState>()(
  persist(
    (set) => ({
      language: "uz",
      setLanguage: (language) => set({ language }),
    }),
    { name: "kans-shop-language" },
  ),
);
