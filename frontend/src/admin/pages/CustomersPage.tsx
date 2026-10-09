import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { adminQueryKeys, setAdminUserBlocked, useAdminUser, useAdminUsers } from "@/admin/adminQueries";
import { useTranslate } from "@/lib/i18n";
import {
  AdminEmptyState,
  AdminErrorState,
  AdminField,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  formatAdminDate,
  primaryButtonClass,
} from "@/admin/pages/AdminPageFrame";

export function CustomersPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const users = useAdminUsers(query, page);
  const customer = useAdminUser(selectedId);
  const block = useMutation({
    mutationFn: ({ id, blocked }: { id: number; blocked: boolean }) => setAdminUserBlocked(id, blocked),
    onSuccess: async (_result, variables) => Promise.all([
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.users(query, page) }),
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.user(variables.id) }),
    ]),
  });

  return <AdminPageFrame route={route}>
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <AdminPanel>
        <AdminField label={t("admin.customers.search")}>
          {(className) => <input className={className} onChange={(event) => { setQuery(event.target.value); setPage(1); }} value={query} />}
        </AdminField>
        <div className="mt-4 space-y-2">
          {users.isPending ? <AdminLoadingState /> : users.isError ? <AdminErrorState onRetry={() => void users.refetch()} /> : users.data?.items.length ? users.data.items.map((user) => (
            <button aria-pressed={selectedId === user.id} className={`block min-h-11 w-full rounded-lg border p-3 text-left ${selectedId === user.id ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-400/10" : "border-slate-200 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"}`} key={user.id} onClick={() => setSelectedId(user.id)} type="button">
              <span className="block truncate font-semibold">{user.first_name} {user.last_name ?? ""}</span>
              <span className="mt-1 block break-all text-sm text-slate-600 dark:text-slate-300">{t("admin.customers.phone")}: {user.phone ?? "—"}</span>
              <span className="mt-1 block text-xs text-slate-500">Telegram ID {user.telegram_id}{user.is_blocked ? ` · ${t("admin.customers.blocked")}` : ""}</span>
            </button>
          )) : <AdminEmptyState />}
        </div>
        {users.data && <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-slate-600 dark:text-slate-300">{t("admin.common.page", { page: users.data.page, total: users.data.total_pages })}</p>
          <div className="flex gap-2"><button className={buttonClass} disabled={page <= 1} onClick={() => setPage((current) => current - 1)} type="button">{t("admin.common.previous")}</button><button className={buttonClass} disabled={page >= users.data.total_pages} onClick={() => setPage((current) => current + 1)} type="button">{t("admin.common.next")}</button></div>
        </div>}
      </AdminPanel>

      <div>{selectedId === null ? <AdminEmptyState>{t("admin.orders.select")}</AdminEmptyState>
        : customer.isPending ? <AdminLoadingState />
          : customer.isError ? <AdminErrorState onRetry={() => void customer.refetch()} />
            : customer.data && <AdminPanel title={`${customer.data.first_name} ${customer.data.last_name ?? ""}`}>
              <dl className="grid min-w-0 gap-4 sm:grid-cols-2">
                <Detail label={t("admin.customers.phone")} value={customer.data.phone ?? "—"} />
                <Detail label={t("admin.customers.telegram_id")} value={String(customer.data.telegram_id)} />
                <Detail label={t("admin.customers.orders_count")} value={String(customer.data.orders_count)} />
                <Detail label={t("admin.customers.first_touch")} value={customer.data.first_touch_source?.name ?? "—"} />
                <Detail label={t("admin.customers.blocked")} value={customer.data.is_blocked ? t("common.yes") : t("common.no")} />
                <Detail label={t("admin.customers.telegram_username")} value={customer.data.username ? `@${customer.data.username}` : "—"} />
                <Detail label={t("admin.customers.created")} value={formatAdminDate(customer.data.created_at)} />
              </dl>
              {block.error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800" role="alert">{t("admin.common.action_error")}</p>}
              <button className={`${customer.data.is_blocked ? buttonClass : primaryButtonClass} mt-5 w-full sm:w-auto`} disabled={block.isPending} onClick={() => block.mutate({ id: customer.data!.id, blocked: !customer.data!.is_blocked })} type="button">
                {customer.data.is_blocked ? t("admin.customers.unblock") : t("admin.customers.block")}
              </button>
            </AdminPanel>}
      </div>
    </div>
  </AdminPageFrame>;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-900 dark:text-white">{value}</dd></div>;
}
