import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslate } from "@/lib/i18n";
import { isTelegramWebApp } from "@/lib/telegram";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { LanguageSwitcher } from "@/components/storefront/LanguageSwitcher";
import { ThemeToggle } from "@/components/storefront/ThemeToggle";

interface TelegramBackButton {
  show?: () => void;
  hide?: () => void;
  onClick?: (handler: () => void) => void;
  offClick?: (handler: () => void) => void;
}

interface TelegramWebAppWindow extends Window {
  Telegram?: { WebApp?: { BackButton?: TelegramBackButton } };
}

function isProfileRoute(pathname: string): boolean {
  return pathname === "/profile" || pathname === "/favorites" || pathname.startsWith("/profile/");
}

function destinationIsActive(to: string, pathname: string): boolean {
  if (to === "/") return pathname === "/";
  if (to === "/orders") return pathname === "/orders" || pathname.startsWith("/orders/");
  if (to === "/profile") return isProfileRoute(pathname);
  return pathname === to;
}

export function StorefrontHeader({
  cartCount = 0,
  isAuthenticated,
}: {
  cartCount?: number;
  isAuthenticated: boolean;
}) {
  const t = useTranslate();
  const location = useLocation();
  const navigate = useNavigate();
  const { openLogin, logout } = useCustomerAuth();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") ?? "");
  const showBack = location.pathname !== "/";
  const insideTelegram = isTelegramWebApp();
  const destinations = [
    { to: "/", label: t("nav.catalog") },
    { to: "/orders", label: t("nav.orders") },
    { to: "/cart", label: t("nav.cart") },
    { to: "/profile", label: t("nav.profile") },
  ];

  useEffect(() => {
    setSearch(searchParams.get("q") ?? "");
  }, [searchParams]);

  function goBack(): void {
    const historyIndex = (window.history.state as { idx?: number } | null)?.idx;
    if (typeof historyIndex === "number" && historyIndex > 0) {
      navigate(-1);
      return;
    }
    if (location.pathname.startsWith("/orders/")) {
      navigate("/orders");
      return;
    }
    if (location.pathname === "/favorites" || location.pathname === "/profile/addresses") {
      navigate("/profile");
      return;
    }
    navigate("/");
  }

  useEffect(() => {
    const backButton = (window as TelegramWebAppWindow).Telegram?.WebApp?.BackButton;
    if (!backButton || !isTelegramWebApp()) return;
    if (showBack) {
      backButton.show?.();
      backButton.onClick?.(goBack);
    } else {
      backButton.hide?.();
    }
    return () => {
      backButton.offClick?.(goBack);
      if (showBack) backButton.hide?.();
    };
  }, [location.pathname, showBack, navigate]);

  function submitSearch(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const query = search.trim();
    navigate({ pathname: "/", search: query ? `?q=${encodeURIComponent(query)}` : "" });
  }

  return (
    <header className="storefront-header sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-white/10 dark:bg-slate-950/95" data-track-area="header">
      <div className="header-inner mx-auto flex min-h-16 max-w-7xl items-center gap-2 px-3 sm:gap-4 sm:px-6 lg:px-8">
        <div className="flex min-w-0 shrink-0 items-center gap-2">
          {showBack && (
            <button
              aria-label={t("common.back")}
              className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-lg text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:text-slate-100 dark:hover:bg-white/10"
              onClick={goBack}
              type="button"
            >
              <span aria-hidden="true">←</span>
            </button>
          )}
          <Link className="brand-link flex min-h-11 items-center rounded-lg font-semibold tracking-tight text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:text-white" to="/">
            <span aria-hidden="true" className="brand-mark"><svg width="25" height="28" viewBox="0 0 28 32" fill="none"><path d="M7 5v22M21 5 8 17l14 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round"/><circle cx="22" cy="5" r="3" fill="#EE7938"/></svg></span>
            <span className="brand-name"><span>Kans</span> <span>Shop</span></span>
          </Link>
        </div>

        <form className="hidden min-w-40 flex-1 lg:flex" onSubmit={submitSearch} role="search">
          <label className="sr-only" htmlFor="storefront-search">{t("storefront.search")}</label>
          <input
            className="min-h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 placeholder:text-slate-500 focus:border-brand focus:outline-2 focus:outline-offset-2 focus:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-white dark:placeholder:text-slate-400"
            id="storefront-search"
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("storefront.search")}
            type="search"
            value={search}
          />
        </form>

        <nav aria-label={t("storefront.desktop_navigation")} className="hidden flex-1 items-center justify-center gap-1 lg:flex">
          {destinations.map(({ to, label }) => {
            const active = destinationIsActive(to, location.pathname);
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 min-w-11 items-center justify-center rounded-lg px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
                  active ? "bg-violet-50 text-violet-800 dark:bg-violet-400/15 dark:text-violet-100" : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/10"
                }`}
                key={to}
                to={to}
              >
                <span>{label}</span>
                {to === "/cart" && cartCount > 0 && <span aria-hidden="true" className="ml-1 rounded-full bg-violet-100 px-1.5 text-xs text-violet-800 dark:bg-violet-400/20 dark:text-violet-100">{cartCount}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
          {isAuthenticated ? (
            // Inside Telegram the Mini App signs the customer in from initData, so a code-based
            // account switch is never needed there; it only confused people as a "refresh" icon.
            insideTelegram ? null : <>
              <button
                aria-label={t("auth.switch_account")}
                className="flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-2 text-sm font-medium text-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-slate-100"
                onClick={openLogin}
                title={t("auth.switch_account")}
                type="button"
              >
                <svg aria-hidden="true" className="size-5 xl:hidden" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.6" /><path d="M5 20c.9-3.6 3.6-5.4 7-5.4s6.1 1.8 7 5.4" /></svg>
                <span className="hidden xl:inline">{t("auth.switch_account")}</span>
              </button>
              <button
                aria-label={t("auth.logout")}
                className="hidden min-h-11 items-center rounded-lg px-2 text-sm font-medium text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand xl:flex dark:text-slate-300 dark:hover:bg-white/10"
                onClick={logout}
                type="button"
              >
                {t("auth.logout")}
              </button>
            </>
          ) : (
            <button
              className="min-h-11 rounded-lg bg-brand px-2 text-xs font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand sm:px-3 sm:text-sm"
              onClick={openLogin}
              type="button"
            >
              {t("auth.sign_in")}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
