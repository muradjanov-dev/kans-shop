import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import { adminApi } from "@/admin/api";
import type { AdminRole } from "@/admin/api";
import { createAdminTeamMember, deleteAdminTeamMember, revokeAdminTeamSessions, updateAdminTeamMember, useAdminTeam } from "@/admin/adminQueries";
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
  formatAdminDate,
  inputClass,
  primaryButtonClass,
} from "@/admin/pages/AdminPageFrame";

const roles: AdminRole[] = ["superadmin", "manager", "operator"];

export function TeamPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const { session } = useAdminAuth();
  const queryClient = useQueryClient();
  const team = useAdminTeam();
  const [telegramId, setTelegramId] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<AdminRole>("operator");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");

  async function refreshTeam() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "team"] });
  }

  async function recoverIfCurrentSessionChanged(adminId: number) {
    if (adminId !== session?.admin_id) return;
    try { await adminApi.loadSession(); } catch { setNotice(t("admin.team.self_session_revoked")); }
  }

  const addMember = useMutation({
    mutationFn: () => createAdminTeamMember({ telegram_id: Number(telegramId), full_name: fullName.trim(), role }),
    onSuccess: async () => { setTelegramId(""); setFullName(""); setRole("operator"); setError(null); await refreshTeam(); },
    onError: setError,
  });
  const updateMember = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: Record<string, unknown> }) => updateAdminTeamMember(id, changes),
    onSuccess: async (_updated, variables) => { setError(null); setNotice(""); await refreshTeam(); await recoverIfCurrentSessionChanged(variables.id); },
    onError: setError,
  });
  const removeMember = useMutation({
    mutationFn: (id: number) => deleteAdminTeamMember(id),
    onSuccess: refreshTeam,
    onError: setError,
  });
  const revokeSessions = useMutation({
    mutationFn: (id: number) => revokeAdminTeamSessions(id),
    onSuccess: async (_result, id) => { setError(null); await refreshTeam(); await recoverIfCurrentSessionChanged(id); },
    onError: setError,
  });

  return <AdminPageFrame route={route}>
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(18rem,0.7fr)_minmax(0,1.3fr)]">
      <AdminPanel title={t("admin.team.add")}>
        <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); addMember.mutate(); }}>
          <AdminField label={t("admin.team.telegram_id")}>{(className) => <input className={className} min="1" onChange={(event) => setTelegramId(event.target.value)} required step="1" type="number" value={telegramId} />}</AdminField>
          <AdminField label={t("admin.team.full_name")}>{(className) => <input className={className} maxLength={128} onChange={(event) => setFullName(event.target.value)} required value={fullName} />}</AdminField>
          <AdminField label={t("admin.team.role")}>{(className) => <RoleSelect className={className} role={role} onChange={setRole} />}</AdminField>
          {addMember.error != null && <AdminActionError code={(addMember.error as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code} />}
          <button className={primaryButtonClass} disabled={addMember.isPending || !telegramId || !fullName.trim()} type="submit">{t("admin.team.add")}</button>
        </form>
      </AdminPanel>

      <AdminPanel title={t("admin.page.team")}>
        {team.isPending ? <AdminLoadingState /> : team.isError ? <AdminErrorState onRetry={() => void team.refetch()} /> : team.data?.items.length ? <div className="space-y-3">
          {team.data.items.map((member) => <TeamMemberCard
            key={member.id}
            member={member}
            self={member.id === session?.admin_id}
            pending={updateMember.isPending || removeMember.isPending || revokeSessions.isPending}
            onUpdate={(changes) => updateMember.mutate({ id: member.id, changes })}
            onRemove={() => removeMember.mutate(member.id)}
            onRevoke={() => revokeSessions.mutate(member.id)}
          />)}
        </div> : <AdminEmptyState />}
      </AdminPanel>
    </div>
    {(error != null || addMember.error != null) && <div className="mt-4"><AdminActionError code={(error as { response?: { data?: { error?: { code?: string } } } } | null)?.response?.data?.error?.code} /></div>}
    {notice && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900" role="status">{notice}</p>}
  </AdminPageFrame>;
}

function TeamMemberCard({ member, self, pending, onUpdate, onRemove, onRevoke }: {
  member: { id: number; telegram_id: number; full_name: string; role: AdminRole; is_active: boolean; notifications_enabled: boolean; created_at: string };
  self: boolean; pending: boolean; onUpdate: (changes: Record<string, unknown>) => void; onRemove: () => void; onRevoke: () => void;
}) {
  const t = useTranslate();
  const [role, setRole] = useState(member.role);
  const [name, setName] = useState(member.full_name);
  useEffect(() => {
    setRole(member.role);
    setName(member.full_name);
  }, [member.full_name, member.role]);
  return <article className="min-w-0 rounded-lg border border-slate-200 p-3 dark:border-white/10">
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2"><div className="min-w-0"><p className="break-words font-semibold">{member.full_name}</p><p className="text-xs text-slate-500">#{member.id} · {t("admin.team.telegram_id")} {member.telegram_id} · {t("admin.team.created")}: {formatAdminDate(member.created_at)}</p></div><span className="rounded-full bg-slate-100 px-2 py-1 text-xs dark:bg-white/10">{t(`admin.role.${member.role}` as "admin.role.superadmin" | "admin.role.manager" | "admin.role.operator")}</span></div>
    <div className="mt-3 grid min-w-0 gap-3 sm:grid-cols-2">
      <AdminField label={t("admin.team.full_name")}>{(className) => <input className={className} maxLength={128} onChange={(event) => setName(event.target.value)} value={name} />}</AdminField>
      <AdminField label={t("admin.team.role")}>{(className) => <RoleSelect className={className} role={role} onChange={setRole} />}</AdminField>
      <label className="flex min-h-11 items-center gap-3 text-sm font-medium"><input checked={member.is_active} onChange={(event) => onUpdate({ is_active: event.target.checked })} type="checkbox" />{t("admin.team.active")}</label>
      <label className="flex min-h-11 items-center gap-3 text-sm font-medium"><input checked={member.notifications_enabled} onChange={(event) => onUpdate({ notifications_enabled: event.target.checked })} type="checkbox" />{t("admin.team.notifications")}</label>
    </div>
    <div className="mt-3 flex flex-wrap gap-2">
      <button className={buttonClass} disabled={pending || !name.trim()} onClick={() => onUpdate({ full_name: name.trim(), role })} type="button">{t("admin.team.save")}</button>
      <button className={buttonClass} disabled={pending} onClick={onRevoke} type="button">{t("admin.team.revoke_sessions")}</button>
      <button className={buttonClass} disabled={pending || self} onClick={onRemove} type="button">{t("admin.team.delete")}</button>
    </div>
  </article>;
}

function RoleSelect({ className = inputClass, role, onChange }: { className?: string; role: AdminRole; onChange: (role: AdminRole) => void }) {
  const t = useTranslate();
  return <select className={className} onChange={(event) => onChange(event.target.value as AdminRole)} value={role}>{roles.map((item) => <option key={item} value={item}>{t(`admin.role.${item}` as "admin.role.superadmin" | "admin.role.manager" | "admin.role.operator")}</option>)}</select>;
}
