import { useEffect } from "react";
import { useLanguageStore } from "@/store/language";
import { Outlet, useLocation } from "react-router-dom";
import { AnalyticsTracker } from "@/components/storefront/AnalyticsTracker";
import { BackToTop } from "@/components/storefront/BackToTop";
import { FloatingBackground } from "@/components/storefront/FloatingBackground";
import { StorefrontHeader } from "@/components/storefront/StorefrontHeader";
import { MobileNavigation } from "@/components/storefront/MobileNavigation";
import { SupportLinks } from "@/components/storefront/SupportLinks";
import { useCart } from "@/hooks/queries";
import { useAuthStore } from "@/store/auth";

export function Layout() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const isAuthenticated = Boolean(accessToken && userId);
  const { data: cart } = useCart(isAuthenticated);
  const itemsCount = cart?.items_count ?? 0;
  const pathname = useLocation().pathname;
  const language = useLanguageStore((state) => state.language);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  const hideMobileNavigation = pathname.startsWith("/product/") || pathname.startsWith("/checkout");

  return (
    <div className={`storefront-shell flex min-h-screen w-full flex-col${pathname.startsWith("/product/") ? " storefront-product-detail" : ""}`}>
      <AnalyticsTracker />
      <FloatingBackground />
      <StorefrontHeader cartCount={itemsCount} isAuthenticated={isAuthenticated} />
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="storefront-footer mx-auto w-full max-w-7xl px-5 sm:px-8" data-track-section="footer">
        <SupportLinks showWelcome={pathname !== "/"} /><div className="site-footer"><span>© {new Date().getFullYear()} Kans Shop</span><span>{language === "uz" ? "Yaxshi ishlar kichik buyumlardan boshlanadi." : "Большие идеи начинаются с простых вещей."}</span></div>
      </footer>
      {!hideMobileNavigation && <MobileNavigation cartCount={itemsCount} />}
      <BackToTop />
    </div>
  );
}
