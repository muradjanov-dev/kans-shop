import { useTranslate } from "@/lib/i18n";
import { useTheme } from "@/store/theme";

export function ThemeToggle() {
  const t = useTranslate();
  const { theme, setTheme } = useTheme();
  const nextTheme = theme === "light" ? "dark" : "light";

  return (
    <button
      aria-label={theme === "light" ? t("theme.enable_dark") : t("theme.enable_light")}
      aria-pressed={theme === "dark"}
      className="flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-slate-200 bg-white text-lg text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
      onClick={() => setTheme(nextTheme)}
      type="button"
    >
      <span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>
    </button>
  );
}
