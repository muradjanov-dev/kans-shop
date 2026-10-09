import { Link, useLocation } from "react-router-dom";
import { useTranslate } from "@/lib/i18n";

function isProfileRoute(pathname: string): boolean {
  return pathname === "/profile" || pathname === "/favorites" || pathname.startsWith("/profile/");
}

function destinationIsActive(to: string, pathname: string): boolean {
  if (to === "/") return pathname === "/";
  if (to === "/orders") return pathname === "/orders" || pathname.startsWith("/orders/");
  if (to === "/profile") return isProfileRoute(pathname);
  return pathname === to;
}

export function MobileNavigation({ cartCount = 0 }: { cartCount?: number }) {
  const t = useTranslate();
  const { pathname } = useLocation();
  const destinations = [
    { to: "/", label: t("nav.catalog"), icon: "▦" },
    { to: "/cart", label: t("nav.cart"), icon: "▤" },
    { to: "/orders", label: t("nav.orders"), icon: "▣" },
    { to: "/profile", label: t("nav.profile"), icon: "○" },
  ];

  return (
    <nav
      aria-label={t("storefront.mobile_navigation")}
      className="fixed inset-x-0 bottom-0 z-40 mx-auto grid w-full max-w-xl grid-cols-4 border-t border-slate-200 bg-white/95 px-2 pt-1 pb-[max(0.25rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden dark:border-white/10 dark:bg-slate-950/95"
    >
      {destinations.map(({ to, label, icon }) => {
        const active = destinationIsActive(to, pathname);
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={`relative flex min-h-14 min-w-11 flex-col items-center justify-center gap-0.5 rounded-lg px-1 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
              active ? "text-brand" : "text-slate-600 dark:text-slate-300"
            }`}
            key={to}
            to={to}
          >
            <span aria-hidden="true" className="text-xl leading-6">{icon}</span>
            <span>{label}</span>
            {to === "/cart" && cartCount > 0 && (
              <span aria-label={t("storefront.cart_items", { count: cartCount })} className="absolute right-3 top-1 flex min-h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold text-white">
                {cartCount}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
