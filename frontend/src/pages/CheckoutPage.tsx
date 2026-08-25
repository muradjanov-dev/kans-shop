import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCart,
  useCheckout,
  useLotLinks,
  usePayOrder,
  usePublicSettings,
} from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { useTranslate } from "@/lib/i18n";
import { formatPrice } from "@/lib/format";
import { isValidUzPhone, normalizeUzPhone } from "@/lib/phone";
import { getApiErrorMessage } from "@/lib/api";
import { WebApp } from "@/lib/telegram";
import type { OrderType, PaymentMethod, PaymentProvider } from "@/types/api";

const ONLINE_PROVIDERS: PaymentProvider[] = ["click", "payme", "paynet"];

export function CheckoutPage() {
  const t = useTranslate();
  const navigate = useNavigate();
  const { data: cart, isLoading: cartLoading } = useCart(true);
  const { data: settings } = usePublicSettings();
  const checkout = useCheckout();
  const payOrder = usePayOrder();

  const [orderType, setOrderType] = useState<OrderType>("delivery");
  const [name, setName] = useState(WebApp.initDataUnsafe?.user?.first_name ?? "");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [addressComment, setAddressComment] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash");
  const [comment, setComment] = useState("");
  const [phoneError, setPhoneError] = useState(false);
  const [successOrderNumber, setSuccessOrderNumber] = useState<string | null>(null);
  const [paymentUrl, setPaymentUrl] = useState<string | null>(null);
  const [payError, setPayError] = useState(false);
  const [tenderOrderId, setTenderOrderId] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const lotLinks = useLotLinks(tenderOrderId);

  // Tender is only offered when something in the cart actually has a lot page to pay through,
  // mirroring the same rule in the bot's checkout (backend/app/bot/handlers/user/checkout.py).
  const tenderAvailable = useMemo(
    () => (cart?.items ?? []).some((item) => Boolean(item.product.lot_url)),
    [cart],
  );

  const availablePaymentMethods = useMemo<PaymentMethod[]>(
    () => [
      "cash",
      "card_transfer",
      ...ONLINE_PROVIDERS.filter((p) => settings?.enabled_payment_providers?.includes(p)),
      ...(tenderAvailable ? (["tender"] as PaymentMethod[]) : []),
    ],
    [settings, tenderAvailable],
  );

  const subtotal = Number(cart?.subtotal ?? 0);
  const deliveryFee = useMemo(() => {
    if (orderType !== "delivery" || !settings) return 0;
    const freeFrom = settings.free_delivery_from ?? 0;
    if (freeFrom && subtotal >= freeFrom) return 0;
    return settings.delivery_fee ?? 0;
  }, [orderType, settings, subtotal]);
  const total = subtotal + deliveryFee;
  const minOrder = settings?.min_order_amount ?? 0;
  const belowMinimum = orderType !== "preorder" && minOrder > 0 && subtotal < minOrder;

  if (cartLoading) return <Spinner />;

  if (successOrderNumber) {
    return (
      <div className="flex flex-col items-center gap-4 p-6 text-center">
        <span className="text-5xl">✅</span>
        <p className="text-lg font-semibold text-gray-900">{t("checkout.success")}</p>
        <p className="text-sm text-gray-500">
          {t("checkout.success_number", { number: successOrderNumber })}
        </p>
        {payError && <p className="text-xs font-medium text-red-500">{t("checkout.pay_error")}</p>}
        {paymentUrl && (
          <button
            onClick={() => WebApp.openLink(paymentUrl)}
            className="mt-2 rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-white"
          >
            {t("checkout.pay_button")}
          </button>
        )}
        {tenderOrderId !== null && lotLinks.data && (
          <div className="mt-2 flex w-full flex-col gap-2">
            {lotLinks.data.links.length > 0 && (
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                {t("checkout.lot_links_intro")}
              </p>
            )}
            {lotLinks.data.links.map((link) => (
              <button
                key={link.url}
                onClick={() => WebApp.openLink(link.url)}
                className="rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white"
              >
                📄 {link.product_name}
              </button>
            ))}
            {lotLinks.data.missing.length > 0 && (
              <p className="text-xs text-amber-600">
                {t("checkout.lot_links_missing", {
                  products: lotLinks.data.missing.join(", "),
                })}
              </p>
            )}
          </div>
        )}
        <button
          onClick={() => navigate("/orders")}
          className="mt-2 rounded-lg border border-gray-200 px-6 py-2.5 text-sm font-semibold text-gray-700"
        >
          {t("nav.orders")}
        </button>
      </div>
    );
  }

  const canSubmit =
    name.trim().length > 0 &&
    isValidUzPhone(phone) &&
    (orderType !== "delivery" || address.trim().length > 0) &&
    !belowMinimum &&
    (cart?.items.length ?? 0) > 0;

  function handleSubmit() {
    if (!isValidUzPhone(phone)) {
      setPhoneError(true);
      return;
    }
    setSubmitError(null);
    checkout.mutate(
      {
        order_type: orderType,
        customer_name: name.trim(),
        customer_phone: normalizeUzPhone(phone),
        payment_method: paymentMethod,
        address: orderType === "delivery" ? address.trim() : null,
        address_comment: orderType === "delivery" ? addressComment.trim() || null : null,
        comment: comment.trim() || null,
      },
      {
        onSuccess: (order) => {
          setSuccessOrderNumber(order.order_number);
          if (paymentMethod === "tender") {
            setTenderOrderId(order.id);
          }
          if ((ONLINE_PROVIDERS as string[]).includes(paymentMethod)) {
            payOrder.mutate(
              { orderId: order.id, provider: paymentMethod as PaymentProvider },
              {
                onSuccess: (res) => setPaymentUrl(res.payment_url),
                onError: () => setPayError(true),
              },
            );
          }
        },
        onError: (error) => setSubmitError(getApiErrorMessage(error, t("common.error"))),
      },
    );
  }

  return (
    <div className="p-4 pb-40">
      <h1 className="mb-4 text-lg font-semibold text-gray-900">{t("checkout.title")}</h1>

      <Field label={t("checkout.order_type")}>
        <div className="grid grid-cols-3 gap-2">
          {(["delivery", "pickup", "preorder"] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setOrderType(type)}
              className={`rounded-lg border px-2 py-2 text-xs font-medium ${
                orderType === type
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-gray-200 text-gray-600"
              }`}
            >
              {t(`checkout.order_type.${type}`)}
            </button>
          ))}
        </div>
      </Field>

      <Field label={t("checkout.name")}>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand focus:outline-none"
        />
      </Field>

      <Field label={t("checkout.phone")}>
        <input
          value={phone}
          onChange={(event) => {
            setPhone(event.target.value);
            setPhoneError(false);
          }}
          placeholder="+998901234567"
          className={`w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none ${
            phoneError ? "border-red-400" : "border-gray-200 focus:border-brand"
          }`}
        />
      </Field>

      {orderType === "delivery" && (
        <>
          <Field label={t("checkout.address")}>
            <input
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand focus:outline-none"
            />
          </Field>
          <Field label={t("checkout.address_comment")}>
            <input
              value={addressComment}
              onChange={(event) => setAddressComment(event.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand focus:outline-none"
            />
          </Field>
        </>
      )}

      <Field label={t("checkout.payment_method")}>
        <div className="grid grid-cols-2 gap-2">
          {availablePaymentMethods.map((method) => (
            <button
              key={method}
              type="button"
              onClick={() => setPaymentMethod(method)}
              className={`rounded-lg border px-3 py-2 text-xs font-medium ${
                paymentMethod === method
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-gray-200 text-gray-600"
              }`}
            >
              {t(`checkout.payment.${method}`)}
            </button>
          ))}
        </div>
      </Field>

      <Field label={t("checkout.comment")}>
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={2}
          className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand focus:outline-none"
        />
      </Field>

      <div className="fixed bottom-0 mx-auto flex w-full max-w-lg flex-col gap-2 border-t border-gray-200 bg-white p-4">
        <div className="flex justify-between text-sm text-gray-500">
          <span>{t("cart.subtotal")}</span>
          <span>
            {formatPrice(subtotal)} {t("common.som")}
          </span>
        </div>
        {orderType === "delivery" && (
          <div className="flex justify-between text-sm text-gray-500">
            <span>{t("checkout.delivery_fee")}</span>
            <span>
              {formatPrice(deliveryFee)} {t("common.som")}
            </span>
          </div>
        )}
        <div className="flex justify-between text-base font-semibold text-gray-900">
          <span>{t("checkout.total")}</span>
          <span>
            {formatPrice(total)} {t("common.som")}
          </span>
        </div>
        {belowMinimum && (
          <p className="text-xs font-medium text-red-500">{t("checkout.min_order_error")}</p>
        )}
        {submitError && <p className="text-xs font-medium text-red-500">{submitError}</p>}
        <button
          disabled={!canSubmit || checkout.isPending}
          onClick={handleSubmit}
          className="rounded-lg bg-brand py-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {t("checkout.submit")}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-xs font-medium text-gray-500">{label}</span>
      {children}
    </label>
  );
}
