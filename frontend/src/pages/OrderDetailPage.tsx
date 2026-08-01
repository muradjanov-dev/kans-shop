import { Link, useParams } from "react-router-dom";
import { useOrder } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatPrice } from "@/lib/format";

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslate();
  const { data: order, isLoading, isError, refetch } = useOrder(id ? Number(id) : undefined);

  if (isLoading) return <Spinner />;
  if (isError || !order) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="p-4">
      <Link to="/orders" className="mb-4 inline-block text-sm font-medium text-brand">
        ← {t("common.back")}
      </Link>

      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">
          {t("orders.number")} {order.order_number}
        </h1>
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">
          {t(`orders.status.${order.status}` as TranslationKey)}
        </span>
      </div>

      {order.cancel_reason && (
        <p className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {order.cancel_reason}
        </p>
      )}

      <h2 className="mb-2 text-sm font-medium text-gray-500">{t("orders.items")}</h2>
      <div className="flex flex-col gap-2">
        {order.items.map((item) => (
          <div key={item.id} className="flex justify-between text-sm">
            <span className="text-gray-700">
              {item.product_name_snapshot} × {item.quantity}
            </span>
            <span className="font-medium text-gray-900">
              {formatPrice(item.total)} {t("common.som")}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex justify-between border-t border-gray-200 pt-3 text-base font-semibold text-gray-900">
        <span>{t("orders.total")}</span>
        <span>
          {formatPrice(order.total)} {t("common.som")}
        </span>
      </div>
    </div>
  );
}
