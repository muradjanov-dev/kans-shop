import { usePublicSettings } from "@/hooks/queries";
import { useTranslate } from "@/lib/i18n";

export function SupportLinks() {
  const t = useTranslate();
  const { data: settings } = usePublicSettings();
  const username = settings?.support_username?.trim().replace(/^@/, "");
  const phone = settings?.shop_phone?.trim();
  const workHours = settings?.work_hours?.trim();
  const phoneNumber = phone?.replace(/[^+\d]/g, "");
  const supportUrl = username ? `https://t.me/${encodeURIComponent(username)}` : null;

  if (!supportUrl && !phoneNumber && !workHours) return null;

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
      {phoneNumber && (
        <a
          className="min-h-11 inline-flex items-center font-medium hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          href={`tel:${phoneNumber}`}
        >
          {phone}
        </a>
      )}
      {workHours && <span>{workHours}</span>}
    </div>
  );
}
