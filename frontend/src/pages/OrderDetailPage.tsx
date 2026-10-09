import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { ReceiptUpload } from "@/features/checkout/ReceiptUpload";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useOrder, usePayOrder } from "@/hooks/queries";
import { OrderTimeline } from "@/pages/OrderTimeline";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatExactPrice } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { WebApp } from "@/lib/telegram";
import type { OrderStatus, OrderType, PaymentProvider } from "@/types/api";

const ONLINE_PROVIDERS: PaymentProvider[] = ["click", "payme", "paynet"];
const ORDER_STATUSES: readonly OrderStatus[] = ["new", "confirmed", "preparing", "delivering", "completed", "cancelled"];
const ORDER_TYPES: readonly OrderType[] = ["delivery", "pickup", "preorder"];

function isOrderStatus(value: unknown): value is OrderStatus {
  return typeof value === "string" && ORDER_STATUSES.includes(value as OrderStatus);
}

function isOrderType(value: unknown): value is OrderType {
  return typeof value === "string" && ORDER_TYPES.includes(value as OrderType);
}

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const { openLogin } = useCustomerAuth();
  const parsedOrderId = id ? Number(id) : NaN;
  const orderId = Number.isSafeInteger(parsedOrderId) && parsedOrderId > 0 ? parsedOrderId : undefined;
  const { data: order, isLoading, isError, refetch } = useOrder(orderId);

  if (!accessToken || !userId) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-gray-600 dark:text-gray-300">{t("orders.open_telegram")}</p>
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
  if (isError || !order) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="p-4 pb-28">
      <Link to="/orders" className="mb-4 inline-flex min-h-11 items-center rounded-lg px-2 text-sm font-medium text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
        ← {t("common.back")}
      </Link>

      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
          {t("orders.number")} {order.order_number}
        </h1>
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700 dark:bg-white/10 dark:text-gray-200">
          {isOrderStatus(order.status) ? t(`orders.status.${order.status}` as TranslationKey) : t("orders.status.unknown")}
        </span>
      </div>

      {order.cancel_reason && (
        <p className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-200">{order.cancel_reason}</p>
      )}

      <div className="mb-4 rounded-xl border border-gray-200 bg-white p-3 dark:border-white/10 dark:bg-slate-900">
        <p className="text-sm font-medium text-gray-900 dark:text-white">{t("checkout.payment_method")}</p>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{t(`checkout.payment.${order.payment_method}` as TranslationKey)}</p>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t(`checkout.payment_status.${order.payment_status}` as TranslationKey)}</p>
        {isOrderType(order.order_type) && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t("orders.order_type_label")}: {t(`orders.order_type.${order.order_type}` as TranslationKey)}
          </p>
        )}
      </div>

      <section className="mb-4 rounded-xl border border-gray-200 bg-white p-3 dark:border-white/10 dark:bg-slate-900">
        <h2 className="text-sm font-medium text-gray-900 dark:text-white">{t("orders.customer_snapshot")}</h2>
        <p className="mt-2 text-sm text-gray-700 dark:text-gray-200">
          <span className="font-medium">{t("orders.customer_name")}:</span> {order.customer_name}
        </p>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
          <span className="font-medium">{t("orders.customer_phone")}:</span> {order.customer_phone}
        </p>
        {typeof order.address === "string" && order.address.trim() && (
          <div className="mt-2">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{t("orders.address_snapshot")}</p>
            <address className="mt-1 whitespace-pre-wrap text-sm not-italic text-gray-700 dark:text-gray-200">
              {order.address}
            </address>
          </div>
        )}
      </section>

      <OrderTimeline orderId={order.id} currentStatus={order.status} orderType={order.order_type} />

      {ONLINE_PROVIDERS.includes(order.payment_method as PaymentProvider) && order.payment_status !== "paid" && order.status !== "cancelled" && (
        <OrderPaymentRecovery orderId={order.id} provider={order.payment_method as PaymentProvider} />
      )}

      <h2 className="mb-2 text-sm font-medium text-gray-500 dark:text-gray-400">{t("orders.items")}</h2>
      <div className="flex flex-col gap-2">
        {order.items.map((item) => (
          <div key={item.id} className="flex justify-between gap-3 text-sm">
            <span className="text-gray-700 dark:text-gray-200">{item.product_name_snapshot} × {item.quantity}</span>
            <span className="font-medium text-gray-900 dark:text-white">
              {formatExactPrice(item.total)} {t("common.som")}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex justify-between border-t border-gray-200 pt-3 text-base font-semibold text-gray-900 dark:border-white/10 dark:text-white">
        <span>{t("orders.total")}</span>
        <span>{formatExactPrice(order.total)} {t("common.som")}</span>
      </div>

      {order.payment_method === "card_transfer" && order.payment_instructions && (
        <section className="mt-5 rounded-xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">{t("checkout.transfer_instructions")}</h2>
          <p className="mt-2 font-mono text-base text-gray-900 dark:text-white">{order.payment_instructions.card_number}</p>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{order.payment_instructions.card_holder}</p>
          <ReceiptUpload order={order} />
        </section>
      )}
      {order.payment_method === "card_transfer" && !order.payment_instructions && (
        <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-100" role="status">
          {t("orders.card_instructions_missing")}
        </p>
      )}
    </div>
  );
}

function OrderPaymentRecovery({ orderId, provider }: { orderId: number; provider: PaymentProvider }) {
  const t = useTranslate();
  const payOrder = usePayOrder();
  const [paymentUrl, setPaymentUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  function requestLink(): void {
    setFailed(false);
    payOrder.mutate(
      { orderId, provider },
      {
        onSuccess: (result) => setPaymentUrl(result.payment_url),
        onError: () => setFailed(true),
      },
    );
  }

  return (
    <section className="mb-4 flex flex-col gap-2 rounded-xl border border-gray-200 bg-white p-3 dark:border-white/10 dark:bg-slate-900">
      {failed && (
        <p className="text-xs text-red-600 dark:text-red-300" role="alert">
          {t("checkout.pay_error")}
        </p>
      )}
      {paymentUrl ? (
        <button
          type="button"
          onClick={() => WebApp.openLink(paymentUrl)}
          className="min-h-11 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white"
        >
          {t("checkout.pay_button")}
        </button>
      ) : (
        <button
          type="button"
          onClick={requestLink}
          disabled={payOrder.isPending}
          className="min-h-11 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {payOrder.isPending ? t("checkout.submitting") : t("checkout.retry_payment_link")}
        </button>
      )}
    </section>
  );
}
