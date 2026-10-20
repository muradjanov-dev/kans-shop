import type { ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AdminAuthProvider, useAdminAuth } from "@/admin/AdminAuthProvider";
import { AdminLayout } from "@/admin/AdminLayout";
import { AdminLoginPage } from "@/admin/AdminLoginPage";
import { RequireAdmin } from "@/admin/RequireAdmin";
import type { AdminRole } from "@/admin/api";
import { useTranslate, type TranslationKey } from "@/lib/i18n";

export type AdminPageId =
  | "dashboard"
  | "analytics"
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
  { id: "analytics", path: "/admin/analytics", segment: "analytics", titleKey: "admin.page.analytics", navKey: "admin.nav.analytics", roles: ["manager", "superadmin"] },
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
