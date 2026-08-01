import { NavLink, Outlet } from "react-router-dom";
import { useTranslate } from "@/lib/i18n";
import { useCart } from "@/hooks/queries";
import { useAuthStore } from "@/store/auth";

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium ${
          isActive ? "text-brand" : "text-gray-500"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export function Layout() {
  const t = useTranslate();
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const { data: cart } = useCart(isAuthenticated);
  const itemsCount = cart?.items_count ?? 0;

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col bg-white">
      <main className="flex-1 pb-16">
        <Outlet />
      </main>
      <nav className="fixed bottom-0 mx-auto flex w-full max-w-lg border-t border-gray-200 bg-white">
        <NavItem to="/" label={t("nav.catalog")} />
        <div className="relative flex flex-1">
          <NavItem to="/cart" label={t("nav.cart")} />
          {itemsCount > 0 && (
            <span className="absolute right-6 top-1 flex size-4 items-center justify-center rounded-full bg-brand text-[10px] font-semibold text-white">
              {itemsCount}
            </span>
          )}
        </div>
        <NavItem to="/orders" label={t("nav.orders")} />
      </nav>
    </div>
  );
}
