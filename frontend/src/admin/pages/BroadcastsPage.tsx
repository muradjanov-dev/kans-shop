import type { AdminPageProps } from "@/admin/adminRoutes";
import { useTranslate } from "@/lib/i18n";
import { AdminPageFrame, AdminPanel } from "@/admin/pages/AdminPageFrame";

/** Task 10 owns the durable broadcast DTOs and state machine; this route stays inert until that contract lands. */
export function BroadcastsPage({ route }: AdminPageProps) {
  const t = useTranslate();
  return <AdminPageFrame route={route}>
    <AdminPanel>
      <p className="max-w-2xl text-sm leading-6 text-slate-700 dark:text-slate-200" role="status">{t("admin.broadcasts.in_progress")}</p>
    </AdminPanel>
  </AdminPageFrame>;
}
