import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import { adminRouteRegistry } from "@/admin/adminRoutes";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";

function roleKey(role: string): TranslationKey {
  return `admin.role.${role}` as TranslationKey;
}

export function AdminLayout() {
  const { session, logout, logoutAll } = useAdminAuth();
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const setLanguage = useLanguageStore((state) => state.setLanguage);
  const [action, setAction] = useState<"logout" | "logout-all" | null>(null);
  const [error, setError] = useState(false);

  async function runLogout(kind: "logout" | "logout-all") {
    setAction(kind);
    setError(false);
    try {
      if (kind === "logout-all") await logoutAll();
      else await logout();
    } catch {
      setError(true);
    } finally {
      setAction(null);
    }
  }

  return (
    <div className="admin-shell">
      <header className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-white/10 dark:bg-slate-950 sm:px-6">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600">Kans Shop</p>
          <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{t("admin.brand")}</p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {session && <span className="max-w-40 truncate text-sm text-slate-600 dark:text-slate-300">{session.full_name}</span>}
          {session && <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-400/10 dark:text-indigo-200">{t(roleKey(session.role))}</span>}
          <button
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-white/15 dark:text-slate-200 dark:hover:bg-white/5"
            onClick={() => setLanguage(language === "uz" ? "ru" : "uz")}
            type="button"
          >
            {language === "uz" ? "РУ" : "UZ"}
          </button>
          <button
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-white/15 dark:text-slate-200 dark:hover:bg-white/5"
            disabled={action !== null}
            onClick={() => void runLogout("logout")}
            type="button"
          >
            {t("admin.logout")}
          </button>
          <button
            className="rounded-lg px-2 py-2 text-sm font-medium text-slate-500 underline decoration-slate-300 underline-offset-4 hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:text-white"
            disabled={action !== null}
            onClick={() => void runLogout("logout-all")}
            type="button"
          >
            {t("admin.logout_all")}
          </button>
        </div>
        {error && <p className="w-full text-right text-sm text-red-700 dark:text-red-300" role="alert">{t("admin.logout_error")}</p>}
      </header>
      <div className="admin-workspace">
        <aside className="admin-sidebar">
          <nav
            aria-label={t("admin.navigation")}
            className="admin-navigation"
            style={{ maxWidth: "100%", overflowX: "auto" }}
          >
            {adminRouteRegistry
              .filter((route) => session && route.roles.includes(session.role))
              .map((route) => (
                <NavLink
                  className={({ isActive }) => `admin-nav-link${isActive ? " admin-nav-link-active" : ""}`}
                  end={route.path === "/admin"}
                  key={route.id}
                  to={route.path}
                >
                  {t(route.navKey)}
                </NavLink>
              ))}
          </nav>
        </aside>
        <main className="admin-content-scroll" data-testid="admin-content-scroll" style={{ maxWidth: "100%", overflowX: "auto" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
