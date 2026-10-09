import { Routes, Route, useLocation } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ProfilePage } from "@/pages/ProfilePage";
import { FavoritesPage } from "@/pages/FavoritesPage";
import { AddressesPage } from "@/pages/AddressesPage";
import { CatalogPage as CustomerCatalogPage } from "@/pages/CatalogPage";
import { ProductPage } from "@/pages/ProductPage";
import { CartPage } from "@/pages/CartPage";
import { CheckoutPage } from "@/pages/CheckoutPage";
import { OrdersPage as CustomerOrdersPage } from "@/pages/OrdersPage";
import { OrderDetailPage } from "@/pages/OrderDetailPage";
import { useTelegramAuth } from "@/hooks/useTelegramAuth";
import { Spinner } from "@/components/Spinner";
import { CustomerAuthProvider } from "@/features/customer-auth/CustomerAuthProvider";
import { AdminApplication } from "@/admin/adminRoutes";
import { AuditPage } from "@/admin/pages/AuditPage";
import { BroadcastsPage } from "@/admin/pages/BroadcastsPage";
import { CatalogPage } from "@/admin/pages/CatalogPage";
import { CustomersPage } from "@/admin/pages/CustomersPage";
import { DashboardPage } from "@/admin/pages/DashboardPage";
import { OrdersPage } from "@/admin/pages/OrdersPage";
import { ReportsPage } from "@/admin/pages/ReportsPage";
import { SettingsPage } from "@/admin/pages/SettingsPage";
import { SourcesPage } from "@/admin/pages/SourcesPage";
import { TeamPage } from "@/admin/pages/TeamPage";

export function App() {
  const location = useLocation();
  if (location.pathname === "/admin" || location.pathname.startsWith("/admin/")) {
    return <AdminApplication pageComponents={{
      dashboard: DashboardPage,
      orders: OrdersPage,
      catalog: CatalogPage,
      customers: CustomersPage,
      reports: ReportsPage,
      settings: SettingsPage,
      team: TeamPage,
      sources: SourcesPage,
      audit: AuditPage,
      broadcasts: BroadcastsPage,
    }} />;
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
          <Route path="/" element={<CustomerCatalogPage />} />
          <Route path="/product/:id" element={<ProductPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/checkout" element={<CheckoutPage />} />
          <Route path="/orders" element={<CustomerOrdersPage />} />
          <Route path="/orders/:id" element={<OrderDetailPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/profile/addresses" element={<AddressesPage />} />
        </Route>
      </Routes>
    </CustomerAuthProvider>
  );
}
