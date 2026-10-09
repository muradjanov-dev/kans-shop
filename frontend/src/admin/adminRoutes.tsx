import { useState, type ComponentType, type FormEvent } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AdminAuthProvider, useAdminAuth } from "@/admin/AdminAuthProvider";
import { AdminLayout } from "@/admin/AdminLayout";
import { RequireAdmin } from "@/admin/RequireAdmin";
import type { AdminRole } from "@/admin/api";
import { useTranslate, type TranslationKey } from "@/lib/i18n";

export type AdminPageId =
  | "dashboard"
  | "orders"
  | "catalog"
  | "customers"
  | "reports"
  | "settings"
  | "team"
  | "sources"
  | "audit"
  | "broadcasts";

export interface AdminRouteDefinition {
  id: AdminPageId;
  path: string;
  segment: string;
  titleKey: TranslationKey;
  navKey: TranslationKey;
  roles: readonly AdminRole[];
}

export interface AdminPageProps {
  route: AdminRouteDefinition;
}

export type AdminPageComponents = Partial<Record<AdminPageId, ComponentType<AdminPageProps>>>;

export const adminRouteRegistry: readonly AdminRouteDefinition[] = [
  { id: "dashboard", path: "/admin", segment: "", titleKey: "admin.page.dashboard", navKey: "admin.nav.home", roles: ["operator", "manager", "superadmin"] },
  { id: "orders", path: "/admin/orders", segment: "orders", titleKey: "admin.page.orders", navKey: "admin.nav.orders", roles: ["operator", "manager", "superadmin"] },
  { id: "catalog", path: "/admin/catalog", segment: "catalog", titleKey: "admin.page.catalog", navKey: "admin.nav.catalog", roles: ["manager", "superadmin"] },
  { id: "customers", path: "/admin/customers", segment: "customers", titleKey: "admin.page.customers", navKey: "admin.nav.customers", roles: ["manager", "superadmin"] },
  { id: "reports", path: "/admin/reports", segment: "reports", titleKey: "admin.page.reports", navKey: "admin.nav.reports", roles: ["operator", "manager", "superadmin"] },
  { id: "settings", path: "/admin/settings", segment: "settings", titleKey: "admin.page.settings", navKey: "admin.nav.settings", roles: ["manager", "superadmin"] },
  { id: "team", path: "/admin/team", segment: "team", titleKey: "admin.page.team", navKey: "admin.nav.team", roles: ["superadmin"] },
  { id: "sources", path: "/admin/sources", segment: "sources", titleKey: "admin.page.sources", navKey: "admin.nav.sources", roles: ["manager", "superadmin"] },
  { id: "audit", path: "/admin/audit", segment: "audit", titleKey: "admin.page.audit", navKey: "admin.nav.audit", roles: ["operator", "manager", "superadmin"] },
  { id: "broadcasts", path: "/admin/broadcasts", segment: "broadcasts", titleKey: "admin.page.broadcasts", navKey: "admin.nav.broadcasts", roles: ["manager", "superadmin"] },
];

export function buildAdminRouteRegistry(components: AdminPageComponents = {}) {
  return adminRouteRegistry.map((route) => ({
    ...route,
    Page: components[route.id] ?? AdminModulePlaceholder,
  }));
}

export function AdminApplication({ pageComponents }: { pageComponents?: AdminPageComponents }) {
  const routes = buildAdminRouteRegistry(pageComponents);

  return (
    <AdminAuthProvider>
      <Routes>
        <Route path="/admin/login" element={<AdminLoginRoute />} />
        <Route path="/admin" element={<RequireAdmin><AdminLayout /></RequireAdmin>}>
          {routes.map((route) => {
            const Page = route.Page;
            const page = <Page route={route} />;
            return (
              <Route
                element={<RequireAdmin roles={route.roles}>{page}</RequireAdmin>}
                index={route.path === "/admin"}
                key={route.id}
                path={route.path === "/admin" ? undefined : route.segment}
              />
            );
          })}
        </Route>
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </AdminAuthProvider>
  );
}

function AdminLoginRoute() {
  const { status } = useAdminAuth();
  const t = useTranslate();
  if (status === "checking") return <p className="p-6 text-center" role="status">{t("admin.loading_session")}</p>;
  if (status === "authenticated") return <Navigate to="/admin" replace />;
  return <AdminLoginPage />;
}

function AdminLoginPage() {
  const { login, loginErrorCode, clearLoginError, notice, retrySessionCheck } = useAdminAuth();
  const t = useTranslate();
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = code.trim();
    if (!/^[0-9]{6}$/.test(normalized)) return;
    setPending(true);
    try {
      await login(normalized);
    } catch {
      // The provider keeps an accessible error code for the login form.
    } finally {
      setPending(false);
    }
  }

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText("/admin_login");
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function retrySession() {
    setRetrying(true);
    await retrySessionCheck();
    setRetrying(false);
  }

  const loginError = loginErrorCode === "INVALID_OR_EXPIRED_CODE"
    ? t("admin.invalid_code")
    : loginErrorCode === "RATE_LIMITED"
      ? t("admin.rate_limited")
      : loginErrorCode
        ? t("admin.login_error")
        : null;

  return (
    <main className="flex min-h-screen w-full items-center justify-center p-4 sm:p-6">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-white/10 dark:bg-slate-950 sm:p-7" aria-labelledby="admin-login-title">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600">Kans Shop</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white" id="admin-login-title">{t("admin.login_title")}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{t("admin.login_instructions")}</p>
        <a className="mt-4 inline-flex min-h-11 items-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700" href="https://t.me/kansshopbot" rel="noreferrer" target="_blank">
          {t("admin.open_bot")}
        </a>
        <div className="mt-4 flex items-center gap-3 rounded-lg bg-slate-50 p-3 dark:bg-white/5">
          <code className="min-w-0 flex-1 break-all rounded bg-white px-2 py-1.5 text-sm text-slate-800 dark:bg-slate-900 dark:text-slate-100">/admin_login</code>
          <button className="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 dark:border-white/15 dark:text-slate-200" onClick={() => void copyCommand()} type="button">
            {copied ? t("admin.copied") : t("admin.copy_command")}
          </button>
        </div>
        <p aria-live="polite" className="sr-only">{copied ? t("admin.copied") : ""}</p>
        <form className="mt-5 flex flex-col gap-3" onSubmit={(event) => void submit(event)}>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200" htmlFor="admin-code">
            {t("admin.code_label")}
            <input
              autoComplete="one-time-code"
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-white/15 dark:bg-slate-900 dark:text-white"
              disabled={pending}
              id="admin-code"
              inputMode="numeric"
              maxLength={6}
              onChange={(event) => {
                setCode(event.target.value.replace(/\D/g, ""));
                clearLoginError();
              }}
              pattern="[0-9]{6}"
              value={code}
            />
          </label>
          {notice === "session-expired" && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-300/10 dark:text-amber-100" role="alert">{t("admin.session_expired")}</p>}
          {notice === "unavailable" && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">
              <span>{t("admin.session_unavailable")}</span>
              <button className="underline underline-offset-2" disabled={retrying} onClick={() => void retrySession()} type="button">{retrying ? t("admin.checking") : t("common.retry")}</button>
            </div>
          )}
          {loginError && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{loginError}</p>}
          <button className="min-h-11 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={pending || code.length !== 6} type="submit">
            {pending ? t("admin.signing_in") : t("admin.login")}
          </button>
        </form>
      </section>
    </main>
  );
}

function AdminModulePlaceholder({ route }: AdminPageProps) {
  const t = useTranslate();
  return (
    <section aria-describedby="admin-page-placeholder" className="min-w-0 p-4 sm:p-6 lg:p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{t(route.titleKey)}</h1>
      <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-white/70 p-5 text-sm leading-6 text-slate-600 dark:border-white/15 dark:bg-slate-950/60 dark:text-slate-300" id="admin-page-placeholder">
        {t("admin.module_placeholder")}
      </div>
    </section>
  );
}
