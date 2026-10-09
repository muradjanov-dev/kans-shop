import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";

beforeEach(() => {
  window.localStorage.clear();
  useAuthStore.getState().clear();
  useLanguageStore.setState({ language: "uz", hasUserPreference: false });
  if (!window.matchMedia) {
    window.matchMedia = (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    });
  }
});

afterEach(() => {
  cleanup();
});
