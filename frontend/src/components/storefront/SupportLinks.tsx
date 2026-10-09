import { usePublicSettings } from "@/hooks/queries";
import { useTranslate } from "@/lib/i18n";
import { isValidUzPhone, normalizeUzPhone } from "@/lib/phone";
import { useLanguageStore } from "@/store/language";

export function SupportLinks({ showWelcome = true }: { showWelcome?: boolean }) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const { data: settings } = usePublicSettings();
  const configuredUsername = settings?.support_username?.trim().replace(/^@/, "") ?? "";
  const username = /^[A-Za-z0-9_]{5,32}$/.test(configuredUsername) ? configuredUsername : null;
  const configuredPhone = settings?.shop_phone?.trim() ?? "";
  const phone = isValidUzPhone(configuredPhone) ? normalizeUzPhone(configuredPhone) : null;
  const workHours = settings?.work_hours?.trim();
  const welcomeText = language === "ru"
    ? settings?.welcome_text_ru?.trim()
    : settings?.welcome_text_uz?.trim();
  const supportUrl = username ? `https://t.me/${encodeURIComponent(username)}` : null;

  if (!supportUrl && !phone && !workHours && !(showWelcome && welcomeText)) return null;

  return (
    <section aria-label={t("storefront.support")} className="mb-24 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white/80 px-3 py-3 text-xs text-slate-600 dark:border-white/10 dark:bg-slate-900/70 dark:text-slate-300 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 lg:mb-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {supportUrl && (
          <a
            className="inline-flex min-h-11 items-center font-medium hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            href={supportUrl}
            rel="noreferrer"
            target="_blank"
          >
            {t("storefront.telegram_support")}
          </a>
        )}
        {phone && (
          <a
            className="inline-flex min-h-11 items-center font-medium hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            href={`tel:${phone}`}
          >
            {phone}
          </a>
        )}
        {workHours && (
          <p className="min-h-11 inline-flex items-center gap-1">
            <span className="font-medium">{t("storefront.work_hours")}:</span>
            <span>{workHours}</span>
          </p>
        )}
      </div>
      {showWelcome && welcomeText && (
        <p className="min-w-0 flex-1 text-sm text-slate-700 dark:text-slate-200">{welcomeText}</p>
      )}
    </section>
  );
}
