import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useLotLinks, usePayOrder } from "@/hooks/queries";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatExactPrice } from "@/lib/format";
import { WebApp } from "@/lib/telegram";
import type { Order, PaymentProvider } from "@/types/api";
import { ReceiptUpload } from "./ReceiptUpload";

const ONLINE_PROVIDERS: PaymentProvider[] = ["click", "payme", "paynet"];

export function CheckoutSuccess({ order }: { order: Order }) {
  const t = useTranslate();
  const payOrder = usePayOrder();
  const lotLinks = useLotLinks(order.payment_method === "tender" ? order.id : null);
  const startedPaymentRequest = useRef(false);
  const [paymentUrl, setPaymentUrl] = useState<string | null>(null);
  const [paymentLinkFailed, setPaymentLinkFailed] = useState(false);
  const hasOnlinePayment = ONLINE_PROVIDERS.includes(order.payment_method as PaymentProvider);

  useEffect(() => {
    if (!hasOnlinePayment || startedPaymentRequest.current) return;
    startedPaymentRequest.current = true;
    requestPaymentLink();
    // The created order remains the payment identity for every retry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasOnlinePayment, order.id]);

  function requestPaymentLink() {
    if (!hasOnlinePayment) return;
    setPaymentLinkFailed(false);
    payOrder.mutate(
      { orderId: order.id, provider: order.payment_method as PaymentProvider },
      {
        onSuccess: (result) => setPaymentUrl(result.payment_url),
        onError: () => setPaymentLinkFailed(true),
      },
    );
  }

  async function copyCardNumber(): Promise<void> {
    const cardNumber = order.payment_instructions?.card_number;
    if (!cardNumber || !navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(cardNumber).catch(() => undefined);
  }

  return (
    <div className="flex flex-col gap-4 p-4 pb-32">
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="text-5xl" aria-hidden="true">✅</span>
        <p className="text-lg font-semibold text-gray-900">{t("checkout.success")}</p>
        <p className="text-sm text-gray-500">{t("checkout.success_number", { number: order.order_number })}</p>
        <p className="text-sm text-gray-600">
          {t(`checkout.payment_status.${order.payment_status}` as TranslationKey)}
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 p-4">
        <div className="flex justify-between text-sm text-gray-500">
          <span>{t("checkout.total")}</span>
          <span className="font-semibold text-gray-900">{formatExactPrice(order.total)} {t("common.som")}</span>
        </div>
      </div>

      {hasOnlinePayment && (
        <div className="flex flex-col gap-2" aria-live="polite">
          {paymentLinkFailed && (
            <p className="text-sm text-red-600" role="alert">{t("checkout.pay_error")}</p>
          )}
          {paymentUrl ? (
            <button
              type="button"
              onClick={() => WebApp.openLink(paymentUrl)}
              className="rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-white"
            >
              {t("checkout.pay_button")}
            </button>
          ) : paymentLinkFailed ? (
            <button
              type="button"
              onClick={requestPaymentLink}
              disabled={payOrder.isPending}
              className="rounded-lg border border-brand px-6 py-2.5 text-sm font-semibold text-brand disabled:opacity-50"
            >
              {payOrder.isPending ? t("checkout.submitting") : t("checkout.retry_payment_link")}
            </button>
          ) : (
            <p className="text-center text-xs text-gray-500">{t("checkout.payment_link_loading")}</p>
          )}
        </div>
      )}

      {order.payment_method === "card_transfer" && order.payment_instructions && (
        <section className="rounded-xl border border-gray-200 p-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-900">{t("checkout.transfer_instructions")}</h2>
          <p className="font-mono text-base text-gray-900">{order.payment_instructions.card_number}</p>
          <p className="mt-1 text-sm text-gray-600">{order.payment_instructions.card_holder}</p>
          <button type="button" onClick={() => void copyCardNumber()} className="mt-3 text-sm font-semibold text-brand">
            {t("checkout.copy_card")}
          </button>
          <ReceiptUpload order={order} />
        </section>
      )}
      {order.payment_method === "card_transfer" && !order.payment_instructions && (
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{t("orders.card_instructions_missing")}</p>
      )}

      {order.payment_method === "tender" && lotLinks.data && (
        <section className="flex flex-col gap-2">
          {lotLinks.data.links.length > 0 && <p className="text-sm font-medium text-gray-700">{t("checkout.lot_links_intro")}</p>}
          {lotLinks.data.links.map((link) => (
            <button
              key={link.url}
              type="button"
              onClick={() => WebApp.openLink(link.url)}
              className="rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white"
            >
              📄 {link.product_name}
            </button>
          ))}
          {lotLinks.data.missing.length > 0 && (
            <p className="text-xs text-amber-700">
              {t("checkout.lot_links_missing", { products: lotLinks.data.missing.join(", ") })}
            </p>
          )}
        </section>
      )}

      <Link
        to={`/orders/${order.id}`}
        className="rounded-lg border border-gray-200 px-6 py-2.5 text-center text-sm font-semibold text-gray-700"
      >
        {t("orders.open_order", { number: order.order_number })}
      </Link>
      <Link to="/orders" className="text-center text-sm font-medium text-brand">{t("nav.orders")}</Link>
    </div>
  );
}
