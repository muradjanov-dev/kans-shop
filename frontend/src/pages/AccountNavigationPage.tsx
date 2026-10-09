import { Link, useLocation } from "react-router-dom";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useTranslate } from "@/lib/i18n";
import { useAuthStore } from "@/store/auth";

type AccountSection = "profile" | "favorites" | "addresses";

const SECTION_KEYS = {
  profile: "account.profile_title",
  favorites: "account.favorites_title",
  addresses: "account.addresses_title",
} as const;

const ACCOUNT_DESTINATIONS = [
  { to: "/profile", key: "nav.profile" },
  { to: "/favorites", key: "nav.favorites" },
  { to: "/profile/addresses", key: "nav.addresses" },
] as const;

export function AccountNavigationPage({ section }: { section: AccountSection }) {
  const t = useTranslate();
  const { pathname } = useLocation();
  const { openLogin, logout } = useCustomerAuth();
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));

  return (
    <section aria-labelledby="account-page-title" className="mx-auto max-w-3xl p-4 sm:p-6">
      <h1 className="mb-3 text-xl font-semibold text-slate-900 dark:text-white" id="account-page-title">
        {t(SECTION_KEYS[section])}
      </h1>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        {isAuthenticated ? t("account.section_unavailable") : t("account.sign_in_required")}
      </p>
      {!isAuthenticated && (
        <button
          className="min-h-11 rounded-lg bg-brand px-5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          onClick={openLogin}
          type="button"
        >
          {t("auth.sign_in")}
        </button>
      )}
      {isAuthenticated && (
        <button
          className="min-h-11 rounded-lg border border-slate-200 px-5 text-sm font-semibold text-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:text-slate-200"
          onClick={logout}
          type="button"
        >
          {t("auth.logout")}
        </button>
      )}
      <nav aria-label={t("account.navigation")} className="mt-6 grid gap-2 sm:grid-cols-3">
        {ACCOUNT_DESTINATIONS.map(({ to, key }) => (
          <Link
            aria-current={pathname === to ? "page" : undefined}
            className={`flex min-h-11 items-center rounded-lg border px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
              pathname === to
                ? "border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-400/30 dark:bg-violet-400/10 dark:text-violet-100"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-white/10 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
            key={to}
            to={to}
          >
            {t(key)}
          </Link>
        ))}
      </nav>
    </section>
  );
}
