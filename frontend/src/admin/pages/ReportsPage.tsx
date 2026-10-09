import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { exportAdminStats, useAdminStats, type AdminPeriod } from "@/admin/adminQueries";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import {
  AdminEmptyState,
  AdminErrorState,
  AdminField,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  formatAdminAmount,
} from "@/admin/pages/AdminPageFrame";

export function ReportsPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const [period, setPeriod] = useState<AdminPeriod>("today");
  const stats = useAdminStats(period);
  const exportMutation = useMutation({
    mutationFn: () => exportAdminStats(period, language),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `stats_${period}.xlsx`;
      anchor.click();
      URL.revokeObjectURL(url);
    },
  });

  return <AdminPageFrame route={route}>
    <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
      <AdminField className="min-w-[12rem] flex-1 sm:max-w-xs" label={t("admin.reports.period")}>
        {(className) => <select className={className} onChange={(event) => setPeriod(event.target.value as AdminPeriod)} value={period}>
          <option value="today">{t("admin.reports.today")}</option><option value="week">{t("admin.reports.week")}</option><option value="month">{t("admin.reports.month")}</option>
        </select>}
      </AdminField>
      <button className={buttonClass} disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()} type="button">{exportMutation.isPending ? t("admin.common.loading") : t("admin.reports.export")}</button>
    </div>
    {exportMutation.error && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800" role="alert">{t("admin.common.action_error")}</p>}

    <div className="mt-4">
      {stats.isPending ? <AdminLoadingState /> : stats.isError ? <AdminErrorState onRetry={() => void stats.refetch()} /> : stats.data && <>
        <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label={t("admin.reports.orders_count")} value={String(stats.data.orders_count)} />
          <Metric label={t("admin.reports.order_value")} value={formatAdminAmount(stats.data.order_value)} />
          <Metric label={t("admin.reports.paid_amount")} value={formatAdminAmount(stats.data.paid_amount)} />
          <Metric label={t("admin.reports.avg_check")} value={formatAdminAmount(stats.data.avg_check)} />
          <Metric label={t("admin.reports.new_users")} value={String(stats.data.new_users)} />
        </div>
        <AdminPanel className="mt-4" title={t("admin.reports.top_products")}>
          {stats.data.top_products.length ? <ol className="divide-y divide-slate-100 dark:divide-white/10">{stats.data.top_products.map((product, index) => <li className="flex justify-between gap-3 py-3 text-sm" key={`${product.name}-${index}`}><span className="break-words">{product.name}</span><span className="shrink-0 font-semibold">{product.sold}</span></li>)}</ol> : <AdminEmptyState />}
        </AdminPanel>
      </>}
    </div>
  </AdminPageFrame>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article className="min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950 sm:p-5"><p className="text-sm text-slate-600 dark:text-slate-300">{label}</p><p className="mt-3 break-words text-xl font-semibold">{value}</p></article>;
}
