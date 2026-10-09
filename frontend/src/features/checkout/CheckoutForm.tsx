import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatExactPrice } from "@/lib/format";
import type { OrderType, PaymentMethod } from "@/types/api";
import type { useCheckoutFlow } from "./useCheckoutFlow";

type CheckoutFlow = ReturnType<typeof useCheckoutFlow>;

const ORDER_TYPES: OrderType[] = ["delivery", "pickup", "preorder"];

export function CheckoutForm({ flow }: { flow: CheckoutFlow }) {
  const t = useTranslate();
  const quote = flow.quote;
  const isPreorder = flow.orderType === "preorder";

  return (
    <div className="p-4 pb-44">
      <h1 className="mb-4 text-lg font-semibold text-gray-900">{t("checkout.title")}</h1>

      <Field label={t("checkout.order_type")}>
        <div className="grid grid-cols-3 gap-2">
          {ORDER_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              disabled={flow.locked}
              onClick={() => flow.setOrderType(type)}
              aria-pressed={flow.orderType === type}
              className={`rounded-lg border px-2 py-2 text-xs font-medium disabled:opacity-50 ${
                flow.orderType === type
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-gray-200 text-gray-600"
              }`}
            >
              {t(`checkout.order_type.${type}`)}
            </button>
          ))}
        </div>
      </Field>

      <Field label={t("checkout.name")} error={flow.errors.name ? t(flow.errors.name as TranslationKey) : undefined}>
        <input
          value={flow.name}
          onChange={(event) => flow.setName(event.target.value)}
          onBlur={() => flow.touch("name")}
          disabled={flow.locked}
          aria-invalid={Boolean(flow.errors.name)}
          autoComplete="name"
          className={inputClass(Boolean(flow.errors.name))}
        />
      </Field>

      <Field label={t("checkout.phone")} error={flow.errors.phone ? t(flow.errors.phone as TranslationKey) : undefined}>
        <input
          value={flow.phone}
          onChange={(event) => flow.setPhone(event.target.value)}
          onBlur={() => flow.touch("phone")}
          disabled={flow.locked}
          aria-invalid={Boolean(flow.errors.phone)}
          autoComplete="tel"
          inputMode="tel"
          placeholder="+998901234567"
          className={inputClass(Boolean(flow.errors.phone))}
        />
      </Field>

      {flow.orderType === "delivery" && (
        <>
          <Field label={t("checkout.address")} error={flow.errors.address ? t(flow.errors.address as TranslationKey) : undefined}>
            <input
              value={flow.address}
              onChange={(event) => flow.setAddress(event.target.value)}
              onBlur={() => flow.touch("address")}
              disabled={flow.locked}
              aria-invalid={Boolean(flow.errors.address)}
              autoComplete="street-address"
              className={inputClass(Boolean(flow.errors.address))}
            />
          </Field>
          <Field label={t("checkout.address_comment")}>
            <input
              value={flow.addressComment}
              onChange={(event) => flow.setAddressComment(event.target.value)}
              disabled={flow.locked}
              className={inputClass(false)}
            />
          </Field>
        </>
      )}

      {!isPreorder && (
        <Field label={t("checkout.payment_method")}>
          <div className="grid grid-cols-2 gap-2">
            {quote?.payment_methods.map((method) => (
              <PaymentOption
                key={method}
                method={method}
                selected={flow.paymentMethod === method}
                disabled={flow.locked}
                onSelect={flow.setPaymentMethod}
              />
            ))}
          </div>
          {!flow.quoteLoading && !flow.quoteError && quote?.payment_methods.length === 0 && (
            <p className="mt-2 text-xs text-gray-500">{t("checkout.no_payment_methods")}</p>
          )}
        </Field>
      )}
      {isPreorder && quote?.ready && !flow.quoteMethodAvailable && (
        <p role="alert" className="mb-3 text-xs text-red-600">{t("checkout.no_payment_methods")}</p>
      )}

      <Field label={t("checkout.comment")}>
        <textarea
          value={flow.comment}
          onChange={(event) => flow.setComment(event.target.value)}
          disabled={flow.locked}
          rows={2}
          className={inputClass(false)}
        />
      </Field>

      <div className="fixed bottom-0 mx-auto flex w-full max-w-lg flex-col gap-2 border-t border-gray-200 bg-white p-4">
        {flow.quoteLoading && <p className="text-xs text-gray-500">{t("checkout.quote_loading")}</p>}
        {flow.quoteError && (
          <div className="flex items-center justify-between gap-3 text-xs text-red-600" role="alert">
            <span>{t("checkout.quote_error")}</span>
            <button className="font-semibold underline" onClick={flow.refreshQuote} type="button">
              {t("common.retry")}
            </button>
          </div>
        )}
        {quote?.reasons.map((reason, index) => (
          <p
            key={`${index}-${reason}`}
            role={quote.ready ? "note" : "alert"}
            className={`text-xs ${quote.ready ? "text-amber-700" : "font-medium text-red-500"}`}
          >
            {reason}
          </p>
        ))}

        <div className="flex justify-between text-sm text-gray-500">
          <span>{t("cart.subtotal")}</span>
          <span>{price(quote?.subtotal)} {t("common.som")}</span>
        </div>
        {flow.orderType === "delivery" && (
          <div className="flex justify-between text-sm text-gray-500">
            <span>{t("checkout.delivery_fee")}</span>
            <span>{price(quote?.delivery_fee)} {t("common.som")}</span>
          </div>
        )}
        <div className="flex justify-between text-base font-semibold text-gray-900">
          <span>{t("checkout.total")}</span>
          <span>{price(quote?.total)} {t("common.som")}</span>
        </div>

        {flow.submitError && (
          <p role="alert" className="text-xs font-medium text-red-600">
            {translateFlowError(flow.submitError, t)}
          </p>
        )}

        {flow.requiresQuoteConfirmation && quote?.ready && (
          <button
            type="button"
            onClick={flow.confirmUpdatedQuote}
            className="rounded-lg border border-amber-400 bg-amber-50 py-2 text-sm font-semibold text-amber-900"
          >
            {t("checkout.confirm_updated_quote")}
          </button>
        )}

        {flow.locked && flow.submitError === "checkout.unknown_outcome" && (
          <button
            type="button"
            onClick={flow.retryUnknown}
            disabled={flow.isSubmitting}
            className="rounded-lg bg-brand py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {flow.isSubmitting ? t("checkout.submitting") : t("common.retry")}
          </button>
        )}

        {!flow.locked && (
          <button
            type="button"
            disabled={!flow.canSubmit || flow.isSubmitting}
            onClick={() => void flow.submit()}
            className="rounded-lg bg-brand py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {flow.isSubmitting ? t("checkout.submitting") : t("checkout.submit")}
          </button>
        )}
      </div>
    </div>
  );
}

function PaymentOption({
  method,
  selected,
  disabled,
  onSelect,
}: {
  method: PaymentMethod;
  selected: boolean;
  disabled: boolean;
  onSelect: (method: PaymentMethod) => void;
}) {
  const t = useTranslate();
  return (
    <button
      key={method}
      type="button"
      disabled={disabled}
      aria-pressed={selected}
      onClick={() => onSelect(method)}
      className={`rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-50 ${
        selected ? "border-brand bg-brand/10 text-brand" : "border-gray-200 text-gray-600"
      }`}
    >
      {t(`checkout.payment.${method}`)}
    </button>
  );
}

function Field({
  label,
  children,
  error,
}: {
  label: string;
  children: React.ReactNode;
  error?: string;
}) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-xs font-medium text-gray-500">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-600" role="alert">{error}</span>}
    </label>
  );
}

function inputClass(hasError: boolean): string {
  return `w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none disabled:bg-gray-50 disabled:opacity-60 ${
    hasError ? "border-red-400" : "border-gray-200 focus:border-brand"
  }`;
}

function price(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : formatExactPrice(value);
}

function translateFlowError(
  error: string,
  t: ReturnType<typeof useTranslate>,
): string {
  if (error.startsWith("checkout.")) return t(error as TranslationKey);
  return error;
}
