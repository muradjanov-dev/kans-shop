import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";

export function LanguageSwitcher() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const setLanguage = useLanguageStore((state) => state.setLanguage);

  return (
    <>
      <label className="sr-only" htmlFor="storefront-language">{t("storefront.language")}</label>
      <select
        id="storefront-language"
        aria-label={t("storefront.language")}
        className="min-h-11 rounded-lg border border-slate-200 bg-white px-2 text-sm font-medium text-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-slate-100"
        onChange={(event) => setLanguage(event.target.value as "uz" | "ru")}
        value={language}
      >
        <option value="uz">O‘zbekcha</option>
        <option value="ru">Русский</option>
      </select>
    </>
  );
}
