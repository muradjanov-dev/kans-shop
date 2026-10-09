import { useState } from "react";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { useAdminAudit } from "@/admin/adminQueries";
import type { AdminAuditFilters } from "@/admin/adminQueries";
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

export function AuditPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const [draft, setDraft] = useState({ action: "", resource_type: "", actor_admin_id: "", request_id: "" });
  const [filters, setFilters] = useState<AdminAuditFilters>({ page: 1, limit: 20 });
  const audit = useAdminAudit(filters);

  return <AdminPageFrame route={route}>
    <AdminPanel>
      <form className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => { event.preventDefault(); setFilters({ page: 1, limit: 20, ...(draft.action.trim() ? { action: draft.action.trim() } : {}), ...(draft.resource_type.trim() ? { resource_type: draft.resource_type.trim() } : {}), ...(draft.actor_admin_id ? { actor_admin_id: Number(draft.actor_admin_id) } : {}), ...(draft.request_id.trim() ? { request_id: draft.request_id.trim() } : {}) }); }}>
        <AdminField label={t("admin.audit.action")}>{(className) => <input className={className} maxLength={64} onChange={(event) => setDraft((current) => ({ ...current, action: event.target.value }))} value={draft.action} />}</AdminField>
        <AdminField label={t("admin.audit.resource_type")}>{(className) => <input className={className} maxLength={64} onChange={(event) => setDraft((current) => ({ ...current, resource_type: event.target.value }))} value={draft.resource_type} />}</AdminField>
        <AdminField label={t("admin.audit.actor_admin_id")}>{(className) => <input className={className} min="1" onChange={(event) => setDraft((current) => ({ ...current, actor_admin_id: event.target.value }))} type="number" value={draft.actor_admin_id} />}</AdminField>
        <AdminField label={t("admin.audit.request_id")}>{(className) => <input className={className} maxLength={64} onChange={(event) => setDraft((current) => ({ ...current, request_id: event.target.value }))} value={draft.request_id} />}</AdminField>
        <button className={`${primaryButtonClass} sm:col-span-2 xl:col-span-4`} type="submit">{t("admin.audit.filter")}</button>
      </form>
    </AdminPanel>

    <div className="mt-4">{audit.isPending ? <AdminLoadingState /> : audit.isError ? <AdminErrorState onRetry={() => void audit.refetch()} /> : audit.data?.items.length ? <AdminPanel>
      <div className="overflow-x-auto"><table className="w-full min-w-[48rem] text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-white/5"><tr><th className="p-3">{t("admin.audit.timestamp")}</th><th className="p-3">{t("admin.audit.actor")}</th><th className="p-3">{t("admin.audit.action")}</th><th className="p-3">{t("admin.audit.resource")}</th><th className="p-3">{t("admin.audit.request_id")}</th><th className="p-3">{t("admin.audit.filter")}</th></tr></thead>
        <tbody>{audit.data.items.map((event) => <tr className="border-t border-slate-100 align-top dark:border-white/10" key={event.id}>
          <td className="whitespace-nowrap p-3">{formatAdminDate(event.created_at)}</td><td className="p-3">{event.actor_name_snapshot ?? event.actor_admin_id ?? "—"}</td><td className="p-3 font-medium">{event.action}</td><td className="p-3">{event.resource_type}{event.resource_id ? ` #${event.resource_id}` : ""}</td><td className="max-w-36 break-all p-3 text-xs">{event.request_id}</td><td className="p-3"><AuditDetails eventId={event.id} before={event.before_json} after={event.after_json} /></td>
        </tr>)}</tbody>
      </table></div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2"><span className="text-sm text-slate-600 dark:text-slate-300">{t("admin.common.page", { page: audit.data.page, total: audit.data.total_pages })}</span><div className="flex gap-2"><button className={buttonClass} disabled={filters.page === 1} onClick={() => setFilters((current) => ({ ...current, page: Math.max(1, (current.page ?? 1) - 1) }))} type="button">{t("admin.common.previous")}</button><button className={buttonClass} disabled={filters.page === audit.data.total_pages} onClick={() => setFilters((current) => ({ ...current, page: (current.page ?? 1) + 1 }))} type="button">{t("admin.common.next")}</button></div></div>
    </AdminPanel> : <AdminEmptyState />}</div>
  </AdminPageFrame>;
}

function AuditDetails({ eventId, before, after }: { eventId: number; before: Record<string, unknown> | null; after: Record<string, unknown> | null }) {
  const [open, setOpen] = useState(false);
  const t = useTranslate();
  return <>
    <button aria-expanded={open} className="min-h-11 rounded-md px-2 text-indigo-700 underline dark:text-indigo-300" onClick={() => setOpen((value) => !value)} type="button">{open ? t("admin.audit.hide_details") : t("admin.audit.show_details")}</button>
    {open && <pre className="mt-2 max-w-64 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-2 text-xs dark:bg-white/5" id={`audit-${eventId}`}>{JSON.stringify({ before, after }, null, 2)}</pre>}
  </>;
}
