import { Link } from "react-router-dom";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { useAdminOrders, useAdminStats } from "@/admin/adminQueries";
import { useTranslate } from "@/lib/i18n";
import {
  AdminEmptyState,
  AdminErrorState,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  formatAdminAmount,
  formatAdminDate,
} from "@/admin/pages/AdminPageFrame";

export function DashboardPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const stats = useAdminStats("today");
  const orders = useAdminOrders({ page: 1, limit: 5 });
  const recentOrders = orders.data?.items ?? [];
  const topProducts = stats.data?.top_products ?? [];

  return <AdminPageFrame route={route}>
    {stats.isPending ? <AdminLoadingState /> : stats.isError ? <AdminErrorState onRetry={() => void stats.refetch()} /> : stats.data && <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label={t("admin.dashboard.today_orders")} value={String(stats.data.orders_count)} />
      <MetricCard label={t("admin.dashboard.order_value")} value={formatAdminAmount(stats.data.order_value)} />
      <MetricCard label={t("admin.dashboard.paid_amount")} value={formatAdminAmount(stats.data.paid_amount)} />
      <MetricCard label={t("admin.dashboard.new_users")} value={String(stats.data.new_users)} />
    </div>}

    <div className="mt-5 grid min-w-0 gap-4 xl:grid-cols-2">
      <AdminPanel title={t("admin.dashboard.recent_orders")}>
        {orders.isPending ? <AdminLoadingState /> : orders.isError ? <AdminErrorState onRetry={() => void orders.refetch()} /> : recentOrders.length ? <ul className="divide-y divide-slate-100 dark:divide-white/10">
          {recentOrders.map((order) => <li className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-3" key={order.id}>
            <span className="min-w-0"><span className="block font-semibold">#{order.order_number} · {order.customer_name}</span><span className="text-sm text-slate-500">{formatAdminDate(order.created_at)}</span></span>
            <span className="shrink-0 text-sm font-semibold">{formatAdminAmount(order.total)}</span>
          </li>)}
        </ul> : <AdminEmptyState />}
        <Link className={`${buttonClass} mt-4 w-full sm:w-auto`} to="/admin/orders">{t("admin.dashboard.view_orders")}</Link>
      </AdminPanel>

      <AdminPanel title={t("admin.dashboard.top_products")}>
        {stats.isPending ? <AdminLoadingState /> : stats.isError ? <AdminErrorState onRetry={() => void stats.refetch()} /> : topProducts.length ? <ul className="divide-y divide-slate-100 dark:divide-white/10">
          {topProducts.map((product, index) => <li className="flex justify-between gap-3 py-3 text-sm" key={`${product.name}-${index}`}><span className="break-words">{product.name}</span><span className="shrink-0 font-semibold">{product.sold}</span></li>)}
        </ul> : <AdminEmptyState />}
      </AdminPanel>
    </div>
  </AdminPageFrame>;
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return <article className="min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950 sm:p-5">
    <p className="text-sm leading-5 text-slate-600 dark:text-slate-300">{label}</p>
    <p className="mt-3 break-words text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{value}</p>
  </article>;
}
