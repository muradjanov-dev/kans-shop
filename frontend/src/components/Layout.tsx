import { Outlet, useLocation } from "react-router-dom";
import { StorefrontHeader } from "@/components/storefront/StorefrontHeader";
import { MobileNavigation } from "@/components/storefront/MobileNavigation";
import { useCart } from "@/hooks/queries";
import { useAuthStore } from "@/store/auth";

export function Layout() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const isAuthenticated = Boolean(accessToken && userId);
  const { data: cart } = useCart(isAuthenticated);
  const itemsCount = cart?.items_count ?? 0;
  const pathname = useLocation().pathname;
  const hideMobileNavigation = pathname.startsWith("/product/") || pathname.startsWith("/checkout");

  return (
    <div className="storefront-shell flex min-h-screen w-full flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <StorefrontHeader cartCount={itemsCount} isAuthenticated={isAuthenticated} />
      <main className="mx-auto w-full max-w-7xl flex-1 px-0 pb-24 sm:px-4 lg:px-8 lg:pb-8">
        <Outlet />
      </main>
      {!hideMobileNavigation && <MobileNavigation cartCount={itemsCount} />}
    </div>
  );
}
