import { Link } from "react-router-dom";
import { useOrders } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatPrice } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import type { OrderStatus } from "@/types/api";

const STATUS_COLORS: Record<OrderStatus, string> = {
  new: "bg-blue-100 text-blue-700",
  confirmed: "bg-indigo-100 text-indigo-700",
  preparing: "bg-amber-100 text-amber-700",
  delivering: "bg-purple-100 text-purple-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700",
};

export function OrdersPage() {
  const t = useTranslate();
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const { data: orders, isLoading, isError, refetch } = useOrders(isAuthenticated);

  if (!isAuthenticated) {
    return <p className="p-6 text-center text-sm text-gray-500">{t("orders.open_telegram")}</p>;
  }
  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold text-gray-900">{t("orders.title")}</h1>
      {!orders || orders.length === 0 ? (
        <p className="py-10 text-center text-sm text-gray-500">{t("orders.empty")}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {orders.map((order) => (
            <Link
              key={order.id}
              to={`/orders/${order.id}`}
              className="flex items-center justify-between rounded-xl border border-gray-100 p-3"
            >
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {t("orders.number")} {order.order_number}
                </p>
                <p className="text-xs text-gray-500">
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
