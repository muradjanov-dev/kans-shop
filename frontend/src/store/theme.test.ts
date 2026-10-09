import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("persisted theme preference", () => {
  it("restores dark mode and persists later light and dark selections", async () => {
    window.localStorage.setItem(
      "kans-shop-theme",
      JSON.stringify({ state: { theme: "dark", hasUserPreference: true }, version: 0 }),
    );
    const themeModules = import.meta.glob<{ useTheme: () => { theme: string; setTheme: (theme: "light" | "dark") => void } }>("./theme.ts");
    const loadTheme = Object.values(themeModules)[0];
    const themeModule = await loadTheme?.();
    expect(themeModule?.useTheme).toBeDefined();
    if (!themeModule) return;

    const { result } = renderHook(() => themeModule.useTheme());
    expect(result.current.theme).toBe("dark");

    act(() => result.current.setTheme("light"));
    expect(JSON.parse(window.localStorage.getItem("kans-shop-theme") ?? "{}").state.theme).toBe("light");

    act(() => result.current.setTheme("dark"));
    expect(JSON.parse(window.localStorage.getItem("kans-shop-theme") ?? "{}").state.theme).toBe("dark");
  });
});
