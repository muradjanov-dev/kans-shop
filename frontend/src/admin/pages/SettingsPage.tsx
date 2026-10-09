import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import type { AdminStoreSettings, AdminStoreSettingsDraft } from "@/admin/adminTypes";
import { adminQueryKeys, getAdminSettings, updateAdminSettings, useAdminSettings } from "@/admin/adminQueries";
import { getAdminApiErrorCode } from "@/admin/api";
import { useTranslate } from "@/lib/i18n";
import {
  AdminActionError,
  AdminErrorState,
  AdminField,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  primaryButtonClass,
} from "@/admin/pages/AdminPageFrame";

const settingFields: Array<keyof AdminStoreSettingsDraft> = [
  "delivery_fee", "free_delivery_from", "min_order_amount", "work_hours", "card_number", "card_holder",
  "support_username", "shop_phone", "is_shop_open", "welcome_text_uz", "welcome_text_ru",
];

export function SettingsPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const { session } = useAdminAuth();
  const queryClient = useQueryClient();
  const settings = useAdminSettings();
  const [draft, setDraft] = useState<AdminStoreSettingsDraft | null>(null);
  const [writeVersion, setWriteVersion] = useState<number | null>(null);
  const [conflictRefreshed, setConflictRefreshed] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);

  useEffect(() => {
    if (settings.data && draft === null) {
      setDraft(toSettingsDraft(settings.data));
      setWriteVersion(settings.data.version);
    }
  }, [draft, settings.data]);

  const save = useMutation({
    mutationFn: () => {
      if (!draft || writeVersion === null) throw new Error("Settings are not loaded");
      return updateAdminSettings(settingsBody(draft, writeVersion));
    },
    onSuccess: async (updated) => {
      setDraft(toSettingsDraft(updated));
      setWriteVersion(updated.version);
      setConflictRefreshed(false);
      setActionError(null);
      setNotice(t("admin.common.save"));
      queryClient.setQueryData([...adminQueryKeys.settings(), session?.admin_id ?? "anonymous"], updated);
    },
    onError: (error) => {
      setActionError(error);
      setNotice("");
      if (getAdminApiErrorCode(error) === "ENTITY_CONFLICT") setConflictRefreshed(false);
    },
  });

  async function refreshLatest() {
    setActionError(null);
    try {
      const latest = await getAdminSettings();
      setWriteVersion(latest.version);
      setConflictRefreshed(true);
      setNotice(t("admin.common.conflict_refreshed"));
      queryClient.setQueryData([...adminQueryKeys.settings(), session?.admin_id ?? "anonymous"], latest);
    } catch (error) { setActionError(error); }
  }

  const conflict = getAdminApiErrorCode(save.error) === "ENTITY_CONFLICT";
  const updateDraft = <K extends keyof AdminStoreSettingsDraft>(field: K, value: AdminStoreSettingsDraft[K]) => {
    setDraft((current) => current ? { ...current, [field]: value } : current);
    setNotice("");
  };

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!draft || writeVersion === null || (conflict && !conflictRefreshed)) return;
    save.mutate();
  }

  return <AdminPageFrame route={route}>
    {settings.isPending || !draft ? settings.isError ? <AdminErrorState onRetry={() => void settings.refetch()} /> : <AdminLoadingState /> : <>
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(17rem,0.6fr)]">
        <AdminPanel title={t("admin.settings.title")}>
          <form className="grid min-w-0 gap-3 sm:grid-cols-2" onSubmit={submit}>
            <AdminField label={t("admin.settings.delivery_fee")}>{(className) => <input className={className} min="0" onChange={(event) => updateDraft("delivery_fee", event.target.value === "" ? null : event.target.value)} step="0.01" type="number" value={draft.delivery_fee ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.free_delivery_from")}>{(className) => <input className={className} min="0" onChange={(event) => updateDraft("free_delivery_from", event.target.value === "" ? null : event.target.value)} step="0.01" type="number" value={draft.free_delivery_from ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.min_order_amount")}>{(className) => <input className={className} min="0" onChange={(event) => updateDraft("min_order_amount", event.target.value === "" ? null : event.target.value)} step="0.01" type="number" value={draft.min_order_amount ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.work_hours")}>{(className) => <input className={className} maxLength={128} onChange={(event) => updateDraft("work_hours", event.target.value || null)} value={draft.work_hours ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.card_number")}>{(className) => <input autoComplete="off" className={className} maxLength={64} onChange={(event) => updateDraft("card_number", event.target.value || null)} value={draft.card_number ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.card_holder")}>{(className) => <input className={className} maxLength={128} onChange={(event) => updateDraft("card_holder", event.target.value || null)} value={draft.card_holder ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.support_username")}>{(className) => <input autoComplete="off" className={className} maxLength={32} onChange={(event) => updateDraft("support_username", event.target.value || null)} value={draft.support_username ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.shop_phone")}>{(className) => <input className={className} maxLength={20} onChange={(event) => updateDraft("shop_phone", event.target.value || null)} type="tel" value={draft.shop_phone ?? ""} />}</AdminField>
            <AdminField label={t("admin.settings.is_shop_open")}>{(className) => <select className={className} onChange={(event) => updateDraft("is_shop_open", event.target.value === "" ? null : event.target.value === "true")} value={draft.is_shop_open === null ? "" : String(draft.is_shop_open)}><option value="">{t("admin.common.unconfigured")}</option><option value="true">{t("common.yes")}</option><option value="false">{t("common.no")}</option></select>}</AdminField>
            <AdminField className="sm:col-span-2" label={t("admin.settings.welcome_text_uz")}>{(className) => <textarea className={`${className} min-h-24`} maxLength={4000} onChange={(event) => updateDraft("welcome_text_uz", event.target.value || null)} value={draft.welcome_text_uz ?? ""} />}</AdminField>
            <AdminField className="sm:col-span-2" label={t("admin.settings.welcome_text_ru")}>{(className) => <textarea className={`${className} min-h-24`} maxLength={4000} onChange={(event) => updateDraft("welcome_text_ru", event.target.value || null)} value={draft.welcome_text_ru ?? ""} />}</AdminField>
            <div className="sm:col-span-2">
              {conflict && <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-300/30 dark:bg-amber-300/10"><p className="text-sm text-amber-900 dark:text-amber-100">{conflictRefreshed ? t("admin.common.conflict_refreshed") : t("admin.common.conflict")}</p>{!conflictRefreshed && <button className={`${buttonClass} mt-2`} onClick={() => void refreshLatest()} type="button">{t("admin.common.refresh_latest")}</button>}</div>}
              {actionError != null && <AdminActionError code={getAdminApiErrorCode(actionError)} />}
              {notice && !conflict && <p className="mb-3 text-sm text-emerald-700 dark:text-emerald-300" role="status">{notice}</p>}
              <button className={primaryButtonClass} disabled={save.isPending || (conflict && !conflictRefreshed)} type="submit">{save.isPending ? t("admin.common.loading") : t("admin.settings.save")}</button>
            </div>
          </form>
        </AdminPanel>
        <AdminPanel title={t("admin.settings.readiness")}>
          <ul className="space-y-2">{settingFields.map((field) => <li className="flex min-w-0 items-center justify-between gap-2 border-b border-slate-100 py-2 text-sm last:border-0 dark:border-white/10" key={field}><span className="min-w-0 break-words">{t(settingLabelKey(field))}</span><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${settings.data?.readiness[field] ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-300/10 dark:text-emerald-200" : "bg-amber-50 text-amber-800 dark:bg-amber-300/10 dark:text-amber-100"}`}>{settings.data?.readiness[field] ? t("common.yes") : t("admin.common.unconfigured")}</span></li>)}</ul>
        </AdminPanel>
      </div>
      <p className="mt-4 text-xs text-slate-500">v{writeVersion ?? settings.data?.version}</p>
    </>}
  </AdminPageFrame>;
}

function toSettingsDraft(settings: AdminStoreSettings): AdminStoreSettingsDraft {
  return {
    delivery_fee: settings.delivery_fee,
    free_delivery_from: settings.free_delivery_from,
    min_order_amount: settings.min_order_amount,
    work_hours: settings.work_hours,
    card_number: settings.card_number,
    card_holder: settings.card_holder,
    support_username: settings.support_username,
    shop_phone: settings.shop_phone,
    is_shop_open: settings.is_shop_open,
    welcome_text_uz: settings.welcome_text_uz,
    welcome_text_ru: settings.welcome_text_ru,
  };
}

function settingsBody(draft: AdminStoreSettingsDraft, expectedVersion: number) {
  return { expected_version: expectedVersion, ...draft };
}

function settingLabelKey(field: keyof AdminStoreSettingsDraft) {
  return `admin.settings.${field}` as const;
}
