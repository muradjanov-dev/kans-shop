import { usePublicSettings } from "@/hooks/queries";
import { useTranslate } from "@/lib/i18n";
import { isValidUzPhone, normalizeUzPhone } from "@/lib/phone";

export function SupportLinks() {
  const t = useTranslate();
  const { data: settings } = usePublicSettings();
  const configuredUsername = settings?.support_username?.trim().replace(/^@/, "") ?? "";
  const username = /^[A-Za-z0-9_]{5,32}$/.test(configuredUsername) ? configuredUsername : null;
  const configuredPhone = settings?.shop_phone?.trim() ?? "";
  const phone = isValidUzPhone(configuredPhone) ? normalizeUzPhone(configuredPhone) : null;
  const workHours = settings?.work_hours?.trim();
  const supportUrl = username ? `https://t.me/${encodeURIComponent(username)}` : null;

  if (!supportUrl && !phone && !workHours) return null;

  return (
    <div className="hidden items-center gap-3 border-l border-slate-200 pl-3 text-xs text-slate-600 dark:border-white/15 dark:text-slate-300 xl:flex">
      {supportUrl && (
        <a
          className="min-h-11 inline-flex items-center font-medium hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          href={supportUrl}
          rel="noreferrer"
          target="_blank"
        >
          {t("storefront.telegram_support")}
        </a>
      )}
      {phone && (
        <a
          className="min-h-11 inline-flex items-center font-medium hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          href={`tel:${phone}`}
        >
          {phone}
        </a>
      )}
      {workHours && !supportUrl && !phone && <span>{workHours}</span>}
    </div>
  );
}
