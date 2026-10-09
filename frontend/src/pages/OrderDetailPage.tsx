import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { ReceiptUpload } from "@/features/checkout/ReceiptUpload";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useOrder, usePayOrder } from "@/hooks/queries";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatExactPrice } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { WebApp } from "@/lib/telegram";
import type { PaymentProvider } from "@/types/api";

const ONLINE_PROVIDERS: PaymentProvider[] = ["click", "payme", "paynet"];

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const { openLogin } = useCustomerAuth();
  const { data: order, isLoading, isError, refetch } = useOrder(id ? Number(id) : undefined);

  if (!accessToken || !userId) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-gray-600">{t("orders.open_telegram")}</p>
        <button
          type="button"
          onClick={openLogin}
          className="rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white"
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
      <Link to="/orders" className="mb-4 inline-block text-sm font-medium text-brand">
        ← {t("common.back")}
      </Link>

      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-gray-900">
          {t("orders.number")} {order.order_number}
        </h1>
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700">
          {t(`orders.status.${order.status}` as TranslationKey)}
        </span>
      </div>

      {order.cancel_reason && (
        <p className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-600">{order.cancel_reason}</p>
      )}

      <div className="mb-4 rounded-xl border border-gray-200 p-3">
        <p className="text-sm font-medium text-gray-900">{t("checkout.payment_method")}</p>
        <p className="mt-1 text-sm text-gray-600">{t(`checkout.payment.${order.payment_method}` as TranslationKey)}</p>
        <p className="mt-1 text-xs text-gray-500">{t(`checkout.payment_status.${order.payment_status}` as TranslationKey)}</p>
      </div>

      {ONLINE_PROVIDERS.includes(order.payment_method as PaymentProvider) && order.payment_status !== "paid" && order.status !== "cancelled" && (
        <OrderPaymentRecovery orderId={order.id} provider={order.payment_method as PaymentProvider} />
      )}

      <h2 className="mb-2 text-sm font-medium text-gray-500">{t("orders.items")}</h2>
      <div className="flex flex-col gap-2">
        {order.items.map((item) => (
          <div key={item.id} className="flex justify-between gap-3 text-sm">
            <span className="text-gray-700">{item.product_name_snapshot} × {item.quantity}</span>
            <span className="font-medium text-gray-900">
              {formatExactPrice(item.total)} {t("common.som")}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex justify-between border-t border-gray-200 pt-3 text-base font-semibold text-gray-900">
        <span>{t("orders.total")}</span>
        <span>{formatExactPrice(order.total)} {t("common.som")}</span>
      </div>

      {order.payment_method === "card_transfer" && order.payment_instructions && (
        <section className="mt-5 rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-900">{t("checkout.transfer_instructions")}</h2>
          <p className="mt-2 font-mono text-base text-gray-900">{order.payment_instructions.card_number}</p>
          <p className="mt-1 text-sm text-gray-600">{order.payment_instructions.card_holder}</p>
          <ReceiptUpload order={order} />
        </section>
      )}
      {order.payment_method === "card_transfer" && !order.payment_instructions && (
        <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900" role="status">
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
    <section className="mb-4 flex flex-col gap-2 rounded-xl border border-gray-200 p-3">
      {failed && <p className="text-xs text-red-600" role="alert">{t("checkout.pay_error")}</p>}
      {paymentUrl ? (
        <button type="button" onClick={() => WebApp.openLink(paymentUrl)} className="rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white">
          {t("checkout.pay_button")}
        </button>
      ) : (
        <button type="button" onClick={requestLink} disabled={payOrder.isPending} className="rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
          {payOrder.isPending ? t("checkout.submitting") : t("checkout.retry_payment_link")}
        </button>
      )}
    </section>
  );
}
