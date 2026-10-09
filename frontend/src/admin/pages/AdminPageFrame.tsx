import type { ReactNode } from "react";
import type { AdminPageProps } from "@/admin/adminRoutes";
import type { DecimalValue } from "@/admin/adminTypes";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";

export function AdminPageFrame({ route, children, description }: AdminPageProps & { children: ReactNode; description?: string }) {
  return (
    <section className="min-w-0 p-4 sm:p-6 lg:p-8" aria-labelledby="admin-page-title">
      <header className="mb-5 max-w-4xl">
        <h1 id="admin-page-title" className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{useTranslate()(route.titleKey)}</h1>
        {description && <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{description}</p>}
      </header>
      {children}
    </section>
  );
}

export function AdminPanel({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950 sm:p-5 ${className}`}>
      {title && <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-white">{title}</h2>}
      {children}
    </section>
  );
}

export function AdminLoadingState() {
  const t = useTranslate();
  return <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600 dark:bg-white/5 dark:text-slate-300" role="status">{t("admin.common.loading")}</p>;
}

export function AdminErrorState({ onRetry }: { onRetry?: () => void }) {
  const t = useTranslate();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-50 p-4 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">
      <span>{t("admin.common.load_error")}</span>
      {onRetry && <button className={buttonClass} onClick={onRetry} type="button">{t("common.retry")}</button>}
    </div>
  );
}

export function AdminActionError({ code }: { code?: string | null }) {
  const t = useTranslate();
  const message = code === "ENTITY_CONFLICT" ? t("admin.common.conflict")
    : code === "LAST_SUPERADMIN_REQUIRED" ? t("admin.team.last_superadmin")
      : t("admin.common.action_error");
  return <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{message}</p>;
}

export function AdminEmptyState({ children }: { children?: ReactNode }) {
  const t = useTranslate();
  return <p className="rounded-lg border border-dashed border-slate-300 p-5 text-sm text-slate-600 dark:border-white/15 dark:text-slate-300">{children ?? t("admin.common.no_results")}</p>;
}

export function AdminField({
  label,
  children,
  className = "",
}: {
  label: string;
  children: (className: string) => ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200 ${className}`}>
      <span>{label}</span>
      {children(inputClass)}
    </label>
  );
}

export const inputClass = "min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-60 dark:border-white/15 dark:bg-slate-900 dark:text-white";
export const buttonClass = "inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/15 dark:text-slate-100 dark:hover:bg-white/5";
export const primaryButtonClass = "inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50";

export function formatAdminAmount(value: DecimalValue | null | undefined): string {
  const language = useLanguageStore.getState().language;
  if (value === null || value === undefined) return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return `${new Intl.NumberFormat(language === "uz" ? "uz-UZ" : "ru-RU", { maximumFractionDigits: 2 }).format(amount)} ${language === "uz" ? "so'm" : "сум"}`;
}

export function formatAdminDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  const language = useLanguageStore.getState().language;
  return new Intl.DateTimeFormat(language === "uz" ? "uz-UZ" : "ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function adminQueryErrorCode(error: unknown): string | null {
  const candidate = error as { response?: { data?: { error?: { code?: string } } } };
  return candidate?.response?.data?.error?.code ?? null;
}
