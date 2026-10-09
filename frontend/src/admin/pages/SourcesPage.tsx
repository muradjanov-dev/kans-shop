import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { adminQueryKeys, createAdminSource, updateAdminSource, useAdminSource, useAdminSources } from "@/admin/adminQueries";
import { useTranslate } from "@/lib/i18n";
import {
  AdminActionError,
  AdminEmptyState,
  AdminErrorState,
  AdminField,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  formatAdminAmount,
  formatAdminDate,
  primaryButtonClass,
} from "@/admin/pages/AdminPageFrame";

export function SourcesPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const queryClient = useQueryClient();
  const sources = useAdminSources();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [editName, setEditName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const detail = useAdminSource(selectedId);

  const invalidate = async (id?: number) => Promise.all([
    queryClient.invalidateQueries({ queryKey: adminQueryKeys.sources(1) }),
    ...(id ? [queryClient.invalidateQueries({ queryKey: adminQueryKeys.source(id) })] : []),
  ]);
  const create = useMutation({
    mutationFn: () => createAdminSource({ name: name.trim(), code: code.trim() }),
    onSuccess: async (source) => { setName(""); setCode(""); setSelectedId(source.id); setError(null); await invalidate(source.id); },
    onError: setError,
  });
  const update = useMutation({
    mutationFn: ({ id, active, nextName }: { id: number; active?: boolean; nextName?: string }) => updateAdminSource(id, { ...(active === undefined ? {} : { active }), ...(nextName === undefined ? {} : { name: nextName.trim() }) }),
    onSuccess: async (_source, variables) => { setError(null); await invalidate(variables.id); },
    onError: setError,
  });

  return <AdminPageFrame route={route}>
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(18rem,0.7fr)_minmax(0,1.3fr)]">
      <div className="space-y-4">
        <AdminPanel title={t("admin.sources.add")}>
          <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
            <AdminField label={t("admin.sources.name")}>{(className) => <input className={className} maxLength={128} onChange={(event) => setName(event.target.value)} required value={name} />}</AdminField>
            <AdminField label={t("admin.sources.code")}>{(className) => <input className={className} maxLength={32} minLength={2} onChange={(event) => setCode(event.target.value)} pattern="[a-zA-Z0-9_-]+" required value={code} />}</AdminField>
            <button className={primaryButtonClass} disabled={create.isPending || !name.trim() || !code.trim()} type="submit">{t("admin.sources.add")}</button>
          </form>
        </AdminPanel>
        <AdminPanel>
          {sources.isPending ? <AdminLoadingState /> : sources.isError ? <AdminErrorState onRetry={() => void sources.refetch()} /> : sources.data?.items.length ? <ul className="space-y-2">
            {sources.data.items.map((source) => <li key={source.id}><button aria-label={`${t("admin.sources.open_metrics")}: ${source.name}`} aria-pressed={selectedId === source.id} className={`min-h-11 w-full rounded-lg border p-3 text-left ${selectedId === source.id ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-400/10" : "border-slate-200 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"}`} onClick={() => { setSelectedId(source.id); setEditName(source.name); }} type="button"><span className="flex flex-wrap items-center justify-between gap-2"><strong>{source.name}</strong><span className="text-xs">{source.is_active ? t("admin.sources.active") : t("admin.sources.inactive")}</span></span><span className="mt-1 block text-sm text-slate-500">{source.code} · {t("admin.sources.clicks")}: {source.clicks_count}</span></button></li>)}
          </ul> : <AdminEmptyState />}
        </AdminPanel>
      </div>
      <div>{selectedId === null ? <AdminEmptyState>{t("admin.orders.select")}</AdminEmptyState>
        : detail.isPending ? <AdminLoadingState />
          : detail.isError ? <AdminErrorState onRetry={() => void detail.refetch()} />
            : detail.data && <AdminPanel title={detail.data.name}>
              <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <Metric label={t("admin.sources.clicks")} value={String(detail.data.clicks)} />
                <Metric label={t("admin.sources.first_touch_users")} value={String(detail.data.first_touch_users)} />
                <Metric label={t("admin.sources.orders")} value={String(detail.data.orders_count)} />
                <Metric label={t("admin.sources.order_value")} value={formatAdminAmount(detail.data.order_value)} />
              </div>
              <p className="mt-4 rounded-lg bg-indigo-50 p-3 text-sm leading-6 text-indigo-950 dark:bg-indigo-400/10 dark:text-indigo-100">{t("admin.reports.source_attribution_note")}</p>
              <AdminField className="mt-4" label={t("admin.sources.name")}>{(className) => <input className={className} maxLength={128} onChange={(event) => setEditName(event.target.value)} value={editName} />}</AdminField>
              <div className="mt-3 flex min-w-0 flex-wrap gap-2">
                <button className={buttonClass} disabled={update.isPending || !editName.trim() || editName.trim() === detail.data.name} onClick={() => update.mutate({ id: detail.data!.id, nextName: editName })} type="button">{t("admin.common.save")}</button>
                <button className={detail.data.is_active ? buttonClass : primaryButtonClass} disabled={update.isPending} onClick={() => update.mutate({ id: detail.data!.id, active: !detail.data!.is_active })} type="button">{detail.data.is_active ? t("admin.sources.deactivate") : t("admin.sources.activate")}</button>
              </div>
              <a className="mt-4 block break-all text-sm font-medium text-indigo-700 underline dark:text-indigo-300" href={detail.data.bot_link} rel="noreferrer" target="_blank">{detail.data.bot_link}</a>
              <p className="mt-2 text-xs text-slate-500">{formatAdminDate(detail.data.created_at)}</p>
            </AdminPanel>}
      </div>
    </div>
    {(error != null || create.error != null || update.error != null) && <div className="mt-4"><AdminActionError /></div>}
  </AdminPageFrame>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article className="min-w-0 rounded-lg border border-slate-200 p-3 dark:border-white/10"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 break-words font-semibold">{value}</p></article>;
}
