import { useState } from "react";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatExactPrice } from "@/lib/format";
import type { Address } from "@/types/api";
import type { AddressInput } from "@/hooks/customer";
import type { OrderType, PaymentMethod } from "@/types/api";
import type { useCheckoutFlow } from "./useCheckoutFlow";

type CheckoutFlow = ReturnType<typeof useCheckoutFlow>;

const ORDER_TYPES: OrderType[] = ["delivery", "pickup", "preorder"];

export function CheckoutForm({
  flow,
  addresses,
  addressesError,
  retryAddresses,
  saveAddress,
  savingAddress,
}: {
  flow: CheckoutFlow;
  addresses: Address[];
  addressesError: boolean;
  retryAddresses: () => void;
  saveAddress: (address: AddressInput) => Promise<unknown>;
  savingAddress: boolean;
}) {
  const t = useTranslate();
  const quote = flow.quote;
  const isPreorder = flow.orderType === "preorder";
  const [selectedAddressId, setSelectedAddressId] = useState("");
  const [savedAddressLabel, setSavedAddressLabel] = useState("");
  const [addressSaved, setAddressSaved] = useState(false);
  const [addressSaveError, setAddressSaveError] = useState(false);

  async function saveCurrentAddress() {
    const label = savedAddressLabel.trim();
    const addressText = flow.address.trim();
    if (!label || label.length > 60 || !addressText || flow.locked) return;
    setAddressSaved(false);
    setAddressSaveError(false);
    try {
      await saveAddress({
        label,
        address_text: addressText,
        address_comment: flow.addressComment.trim() || null,
      });
      setAddressSaved(true);
    } catch {
      setAddressSaveError(true);
    }
  }

  return (
    <div className="p-4 pb-44">
      <h1 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">{t("checkout.title")}</h1>

      <Field label={t("checkout.order_type")}>
        <div className="grid grid-cols-3 gap-2">
          {ORDER_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              disabled={flow.locked}
              onClick={() => flow.setOrderType(type)}
              aria-pressed={flow.orderType === type}
              className={`min-h-11 rounded-lg border px-2 py-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 ${
                flow.orderType === type
                  ? "border-brand bg-brand/10 text-brand"
                  : "border-gray-200 text-gray-600 dark:border-white/15 dark:text-gray-200"
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
          {addresses.length > 0 && (
            <Field label={t("checkout.saved_address")}>
              <select
                className="min-h-11 rounded-lg border border-gray-300 bg-white px-3 text-base text-gray-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-white"
                disabled={flow.locked}
                onChange={(event) => {
                  const selectedId = event.target.value;
                  setSelectedAddressId(selectedId);
                  const savedAddress = addresses.find(({ id }) => String(id) === selectedId);
                  if (savedAddress) {
                    flow.setAddress(savedAddress.address_text);
                    flow.setAddressComment(savedAddress.address_comment ?? "");
                    setAddressSaved(false);
                    setAddressSaveError(false);
                  }
                }}
                value={selectedAddressId}
              >
                <option value="">—</option>
                {addresses.map((address) => <option key={address.id} value={address.id}>{address.label}</option>)}
              </select>
            </Field>
          )}
          {addressesError && (
            <div className="flex items-center justify-between gap-3 text-xs text-red-600 dark:text-red-300" role="alert">
              <span>{t("checkout.saved_addresses_error")}</span>
              <button className="min-h-11 px-2 font-semibold underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={retryAddresses} type="button">
                {t("common.retry")}
              </button>
            </div>
          )}
          <Field label={t("checkout.address")} error={flow.errors.address ? t(flow.errors.address as TranslationKey) : undefined}>
            <input
              value={flow.address}
              maxLength={1000}
              onChange={(event) => {
                setSelectedAddressId("");
                setAddressSaved(false);
                flow.setAddress(event.target.value);
              }}
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
              maxLength={500}
              onChange={(event) => {
                setSelectedAddressId("");
                setAddressSaved(false);
                flow.setAddressComment(event.target.value);
              }}
              disabled={flow.locked}
              className={inputClass(false)}
            />
          </Field>
          <div className="flex flex-col gap-2 rounded-lg border border-slate-200 p-3 dark:border-white/10">
            <Field label={t("checkout.save_address_label")}>
              <input
                className={inputClass(false)}
                disabled={flow.locked || savingAddress}
                maxLength={60}
                onChange={(event) => { setSavedAddressLabel(event.target.value); setAddressSaved(false); }}
                value={savedAddressLabel}
              />
            </Field>
            <button
              className="min-h-11 self-start rounded-lg border border-slate-300 px-4 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 dark:border-white/15"
              disabled={flow.locked || savingAddress || !savedAddressLabel.trim() || !flow.address.trim()}
              onClick={() => void saveCurrentAddress()}
              type="button"
            >
              {savingAddress ? t("checkout.saving_address") : t("checkout.save_for_later")}
            </button>
            {addressSaveError && <p className="text-xs text-red-700 dark:text-red-200" role="alert">{t("checkout.address_save_error")}</p>}
            {addressSaved && <p className="text-xs text-emerald-700 dark:text-emerald-300" role="status">{t("checkout.address_saved")}</p>}
          </div>
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
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{t("checkout.no_payment_methods")}</p>
          )}
        </Field>
      )}
      {isPreorder && quote?.ready && !flow.quoteMethodAvailable && (
        <p role="alert" className="mb-3 text-xs text-red-600 dark:text-red-300">{t("checkout.no_payment_methods")}</p>
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

      <div className="fixed bottom-0 mx-auto flex w-full max-w-lg flex-col gap-2 border-t border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
        {flow.profileLoadError && (
          <div className="flex items-center justify-between gap-3 text-xs text-red-600 dark:text-red-300" role="alert">
            <span>{t("profile.load_error")}</span>
            <button className="min-h-11 px-2 font-semibold underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={flow.retryProfile} type="button">
              {t("common.retry")}
            </button>
          </div>
        )}
        {flow.quoteLoading && <p className="text-xs text-gray-500 dark:text-gray-400">{t("checkout.quote_loading")}</p>}
        {flow.quoteError && (
          <div className="flex items-center justify-between gap-3 text-xs text-red-600 dark:text-red-300" role="alert">
            <span>{t("checkout.quote_error")}</span>
            <button className="min-h-11 px-2 font-semibold underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={flow.refreshQuote} type="button">
              {t("common.retry")}
            </button>
          </div>
        )}
        {quote?.reasons.map((reason, index) => (
          <p
            key={`${index}-${reason}`}
            role={quote.ready ? "note" : "alert"}
            className={`text-xs ${quote.ready ? "text-amber-700 dark:text-amber-300" : "font-medium text-red-500 dark:text-red-300"}`}
          >
            {reason}
          </p>
        ))}

        <div className="flex justify-between text-sm text-gray-500 dark:text-gray-400">
          <span>{t("cart.subtotal")}</span>
          <span>{price(quote?.subtotal)} {t("common.som")}</span>
        </div>
        {flow.orderType === "delivery" && (
          <div className="flex justify-between text-sm text-gray-500 dark:text-gray-400">
            <span>{t("checkout.delivery_fee")}</span>
            <span>{price(quote?.delivery_fee)} {t("common.som")}</span>
          </div>
        )}
        <div className="flex justify-between text-base font-semibold text-gray-900 dark:text-white">
          <span>{t("checkout.total")}</span>
          <span>{price(quote?.total)} {t("common.som")}</span>
        </div>

        {flow.submitError && (
          <p role="alert" className="text-xs font-medium text-red-600 dark:text-red-300">
            {translateFlowError(flow.submitError, t)}
          </p>
        )}

        {flow.requiresQuoteConfirmation && quote?.ready && (
          <button
            type="button"
            onClick={flow.confirmUpdatedQuote}
            className="min-h-11 rounded-lg border border-amber-400 bg-amber-50 py-2 text-sm font-semibold text-amber-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:bg-amber-950/30 dark:text-amber-100"
          >
            {t("checkout.confirm_updated_quote")}
          </button>
        )}

        {flow.locked && flow.submitError === "checkout.unknown_outcome" && (
          <button
            type="button"
            onClick={flow.retryUnknown}
            disabled={flow.isSubmitting}
            className="min-h-11 rounded-lg bg-brand py-2.5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
          >
            {flow.isSubmitting ? t("checkout.submitting") : t("common.retry")}
          </button>
        )}

        {!flow.locked && (
          <button
            type="button"
            disabled={!flow.canSubmit || flow.isSubmitting}
            onClick={() => void flow.submit()}
            className="min-h-11 rounded-lg bg-brand py-2.5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
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
      className={`min-h-11 rounded-lg border px-3 py-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 ${
        selected ? "border-brand bg-brand/10 text-brand" : "border-gray-200 text-gray-600 dark:border-white/15 dark:text-gray-200"
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
      <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-600" role="alert">{error}</span>}
    </label>
  );
}

function inputClass(hasError: boolean): string {
  return `min-h-11 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-gray-900 focus:border-brand focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:bg-gray-50 disabled:opacity-60 dark:border-white/15 dark:bg-slate-900 dark:text-white dark:disabled:bg-slate-800 ${
    hasError ? "border-red-400" : "border-gray-200"
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
