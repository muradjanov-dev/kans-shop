import { Link } from "react-router-dom";
import { useOrders } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatPrice } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import type { OrderStatus } from "@/types/api";

const STATUS_COLORS: Record<OrderStatus, string> = {
  new: "bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-200",
  confirmed: "bg-indigo-100 text-indigo-700 dark:bg-indigo-400/15 dark:text-indigo-200",
  preparing: "bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-200",
  delivering: "bg-purple-100 text-purple-700 dark:bg-purple-400/15 dark:text-purple-200",
  completed: "bg-green-100 text-green-700 dark:bg-green-400/15 dark:text-green-200",
  cancelled: "bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-200",
};

export function OrdersPage() {
  const t = useTranslate();
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const { openLogin } = useCustomerAuth();
  const { data: orders, isLoading, isError, refetch } = useOrders(isAuthenticated);

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-gray-500 dark:text-gray-400">{t("orders.open_telegram")}</p>
        <button
          type="button"
          onClick={openLogin}
          className="min-h-11 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {t("auth.sign_in")}
        </button>
      </div>
    );
  }
  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">{t("orders.title")}</h1>
      {!orders || orders.length === 0 ? (
        <p className="py-10 text-center text-sm text-gray-500 dark:text-gray-400">{t("orders.empty")}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {orders.map((order) => (
            <Link
              key={order.id}
              to={`/orders/${order.id}`}
              className="flex items-center justify-between rounded-xl border border-gray-100 bg-white p-3 dark:border-white/10 dark:bg-slate-900"
            >
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {t("orders.number")} {order.order_number}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-300">
                  {formatPrice(order.total)} {t("common.som")}
                </p>
              </div>
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_COLORS[order.status]}`}
              >
                {t(`orders.status.${order.status}` as TranslationKey)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
