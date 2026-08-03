import { NavLink, Outlet } from "react-router-dom";
import { useTranslate } from "@/lib/i18n";
import { useCart } from "@/hooks/queries";
import { useAuthStore } from "@/store/auth";

function NavItem({ to, icon, label }: { to: string; icon: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex flex-1 flex-col items-center gap-1 py-3 text-sm font-semibold transition-colors ${
          isActive ? "text-brand" : "text-gray-400"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={`flex size-11 items-center justify-center rounded-2xl text-2xl transition-all ${
              isActive ? "scale-105 bg-brand/10" : "bg-transparent"
            }`}
          >
            {icon}
          </span>
          {label}
        </>
      )}
    </NavLink>
  );
}

export function Layout() {
  const t = useTranslate();
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const { data: cart } = useCart(isAuthenticated);
  const itemsCount = cart?.items_count ?? 0;

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col">
      <main className="flex-1 pb-24">
        <Outlet />
      </main>
      <nav className="fixed bottom-0 mx-auto flex w-full max-w-lg border-t border-gray-200 bg-white/95 shadow-[0_-4px_16px_rgba(0,0,0,0.06)] backdrop-blur dark:border-white/10 dark:bg-[#14161b]/95">
        <NavItem to="/" icon="🛍" label={t("nav.catalog")} />
        <div className="relative flex flex-1">
          <NavItem to="/cart" icon="🛒" label={t("nav.cart")} />
          {itemsCount > 0 && (
            <span className="absolute right-4 top-1 flex size-5 items-center justify-center rounded-full bg-brand text-[11px] font-bold text-white shadow-sm">
              {itemsCount}
            </span>
          )}
        </div>
        <NavItem to="/orders" icon="📦" label={t("nav.orders")} />
      </nav>
    </div>
  );
}
