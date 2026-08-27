import { NavLink, Outlet, useLocation } from "react-router-dom";
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
              isActive ? "scale-110 bg-brand/15 text-brand shadow-[0_0_15px_rgba(79,70,229,0.4)] dark:shadow-[0_0_20px_rgba(99,102,241,0.6)]" : "bg-transparent text-gray-500 dark:text-gray-400"
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
  const location = useLocation();
  
  const isProductPage = location.pathname.startsWith('/product/');
  const isCheckoutPage = location.pathname.startsWith('/checkout');
  const hideNav = isProductPage || isCheckoutPage;

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col">
      <main className="flex-1 pb-24">
        <Outlet />
      </main>
      
      <button 
        onClick={() => document.documentElement.classList.toggle('dark')}
        className="fixed top-4 right-4 z-50 flex size-10 items-center justify-center rounded-full glass-panel text-gray-700 dark:text-gray-300 shadow-md"
      >
        <span className="dark:hidden">🌙</span>
        <span className="hidden dark:block">☀️</span>
      </button>

      {!hideNav && (
        <nav className="fixed bottom-4 left-0 right-0 z-50 mx-auto flex w-[calc(100%-2rem)] max-w-md overflow-hidden rounded-2xl glass-panel">
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
      )}
    </div>
  );
}
