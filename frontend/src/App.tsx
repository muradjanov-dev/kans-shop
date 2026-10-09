import { Routes, Route, useLocation } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { AccountNavigationPage } from "@/pages/AccountNavigationPage";
import { CatalogPage } from "@/pages/CatalogPage";
import { ProductPage } from "@/pages/ProductPage";
import { CartPage } from "@/pages/CartPage";
import { CheckoutPage } from "@/pages/CheckoutPage";
import { OrdersPage } from "@/pages/OrdersPage";
import { OrderDetailPage } from "@/pages/OrderDetailPage";
import { useTelegramAuth } from "@/hooks/useTelegramAuth";
import { Spinner } from "@/components/Spinner";
import { CustomerAuthProvider } from "@/features/customer-auth/CustomerAuthProvider";
import { AdminApplication } from "@/admin/adminRoutes";

export function App() {
  const location = useLocation();
  if (location.pathname === "/admin" || location.pathname.startsWith("/admin/")) {
    return <AdminApplication />;
  }
  return <CustomerApplication />;
}

function CustomerApplication() {
  const authStatus = useTelegramAuth();

  if (authStatus === "pending") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <CustomerAuthProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<CatalogPage />} />
          <Route path="/product/:id" element={<ProductPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/checkout" element={<CheckoutPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:id" element={<OrderDetailPage />} />
          <Route path="/profile" element={<AccountNavigationPage section="profile" />} />
          <Route path="/favorites" element={<AccountNavigationPage section="favorites" />} />
          <Route path="/profile/addresses" element={<AccountNavigationPage section="addresses" />} />
        </Route>
      </Routes>
    </CustomerAuthProvider>
  );
}
