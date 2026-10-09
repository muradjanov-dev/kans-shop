import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { useCart, useCheckout } from "@/hooks/queries";
import { useCustomerProfile } from "@/hooks/customer";
import { useCheckoutQuote } from "@/hooks/checkout";
import { getApiErrorCode, getApiErrorMessage } from "@/lib/api";
import { isValidUzPhone, normalizeUzPhone } from "@/lib/phone";
import { WebApp } from "@/lib/telegram";
import { useAuthStore } from "@/store/auth";
import type { CheckoutPayload, Order, OrderType, PaymentMethod } from "@/types/api";

type CheckoutField = "name" | "phone" | "address";
type CheckoutErrors = Partial<Record<CheckoutField, string>>;

interface CheckoutAttempt {
  payload: CheckoutPayload;
  key: string;
}

interface RecoveryRecord {
  checkoutKey: string;
  quoteFingerprint: string;
  attemptId: string;
}

function recoveryStorageKey(userId: string): string {
  return `kans-checkout-recovery:${userId}`;
}

function readRecoveryRecord(userId: string | null): RecoveryRecord | null {
  if (!userId) return null;
  try {
    const raw = sessionStorage.getItem(recoveryStorageKey(userId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<RecoveryRecord>;
    if (
      typeof value.checkoutKey === "string" &&
      typeof value.quoteFingerprint === "string" &&
      typeof value.attemptId === "string"
    ) {
      return {
        checkoutKey: value.checkoutKey,
        quoteFingerprint: value.quoteFingerprint,
        attemptId: value.attemptId,
      };
    }
  } catch {
    // A malformed opaque recovery marker should not make checkout unusable.
  }
  sessionStorage.removeItem(recoveryStorageKey(userId));
  return null;
}

function writeRecoveryRecord(userId: string, record: RecoveryRecord): void {
  sessionStorage.setItem(recoveryStorageKey(userId), JSON.stringify(record));
}

function clearRecoveryRecord(userId: string | null): void {
  if (userId) sessionStorage.removeItem(recoveryStorageKey(userId));
}

function makeUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

function isUnknownOutcome(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return true;
  return !error.response || error.response.status >= 500;
}

function getErrors(
  values: { name: string; phone: string; address: string },
  orderType: OrderType,
): CheckoutErrors {
  const errors: CheckoutErrors = {};
  if (!values.name.trim()) errors.name = "checkout.validation.name";
  if (!isValidUzPhone(values.phone)) errors.phone = "checkout.validation.phone";
  if (orderType === "delivery" && !values.address.trim()) {
    errors.address = "checkout.validation.address";
  }
  return errors;
}

export function useCheckoutFlow() {
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken) && userId);
  const { data: cart, isLoading: cartLoading } = useCart(isAuthenticated);
  const profile = useCustomerProfile();
  const checkout = useCheckout();

  const [orderType, setOrderTypeState] = useState<OrderType>("delivery");
  const [name, setNameState] = useState(WebApp.initDataUnsafe?.user?.first_name ?? "");
  const [phone, setPhoneState] = useState("");
  const [address, setAddressState] = useState("");
  const [addressComment, setAddressCommentState] = useState("");
  const [paymentMethod, setPaymentMethodState] = useState<PaymentMethod>("cash");
  const [comment, setCommentState] = useState("");
  const [touched, setTouched] = useState<CheckoutField[]>([]);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<CheckoutAttempt | null>(null);
  const [recoveryRecord, setRecoveryRecord] = useState(() => readRecoveryRecord(userId));
  const [createdOrder, setCreatedOrder] = useState<Order | null>(null);
  const [quoteConfirmationRequired, setQuoteConfirmationRequired] = useState(false);
  const [confirmedQuoteFingerprint, setConfirmedQuoteFingerprint] = useState<string | null>(null);
  const ownerRef = useRef({ userId, authEpoch });
  const profileOwnerRef = useRef<string | null>(null);
  const nameEditedRef = useRef(false);
  const phoneEditedRef = useRef(false);

  const cartRevision = cart
    ? JSON.stringify({
        subtotal: cart.subtotal,
        items: cart.items
          .map((item) => ({
            product_id: item.product_id,
            quantity: item.quantity,
            price: item.product?.price ?? null,
            is_active: item.product?.is_active ?? null,
            stock_qty: item.product?.stock_qty ?? null,
            lot_url: item.product?.lot_url ?? null,
          }))
          .sort((left, right) => left.product_id - right.product_id),
      })
    : "no-cart";
  const quoteQuery = useCheckoutQuote(
    orderType,
    paymentMethod,
    cartRevision,
    isAuthenticated && !createdOrder && !recoveryRecord && !cartLoading && (cart?.items.length ?? 0) > 0,
  );
  const quote = quoteQuery.isFetching || quoteQuery.isError ? undefined : quoteQuery.data;
  const quotePaymentMethod = orderType === "preorder" ? "cash" : paymentMethod;
  const quoteOffersPaymentMethod = Boolean(quote?.payment_methods?.includes(quotePaymentMethod));

  useEffect(() => {
    const previous = ownerRef.current;
    if (previous.userId === userId && previous.authEpoch === authEpoch) return;
    ownerRef.current = { userId, authEpoch };
    setOrderTypeState("delivery");
    setNameState(WebApp.initDataUnsafe?.user?.first_name ?? "");
    setPhoneState("");
    profileOwnerRef.current = null;
    nameEditedRef.current = false;
    phoneEditedRef.current = false;
    setAddressState("");
    setAddressCommentState("");
    setPaymentMethodState("cash");
    setCommentState("");
    setTouched([]);
    setSubmitAttempted(false);
    setSubmitError(null);
    setAttempt(null);
    setCreatedOrder(null);
    setRecoveryRecord(readRecoveryRecord(userId));
    setQuoteConfirmationRequired(false);
    setConfirmedQuoteFingerprint(null);
  }, [authEpoch, userId]);

  useEffect(() => {
    if (!userId || !profile.data || profileOwnerRef.current === userId) return;
    if (!nameEditedRef.current) setNameState(profile.data.display_name);
    if (!phoneEditedRef.current) setPhoneState(profile.data.phone ?? "");
    profileOwnerRef.current = userId;
  }, [profile.data, userId]);

  useEffect(() => {
    const available = quote?.payment_methods;
    if (!available?.length || orderType === "preorder" || available.includes(paymentMethod)) return;
    setPaymentMethodState(available[0]!);
  }, [orderType, paymentMethod, quote?.payment_methods]);

  const locked = Boolean(attempt || recoveryRecord || checkout.isPending);
  const allErrors = useMemo(
    () => getErrors({ name, phone, address }, orderType),
    [address, name, orderType, phone],
  );
  const visibleErrors = useMemo(() => {
    const result: CheckoutErrors = {};
    for (const field of touched) {
      if (allErrors[field]) result[field] = allErrors[field];
    }
    if (submitAttempted) Object.assign(result, allErrors);
    return result;
  }, [allErrors, submitAttempted, touched]);

  const updateField = useCallback(<T extends string>(setter: (value: T) => void, value: T) => {
    if (locked) return;
    setter(value);
    setSubmitError(null);
    setSubmitAttempted(false);
  }, [locked]);

  const setOrderType = useCallback((value: OrderType) => {
    if (locked) return;
    setOrderTypeState(value);
    if (value === "preorder") setPaymentMethodState("cash");
    setSubmitError(null);
    setQuoteConfirmationRequired(false);
    setConfirmedQuoteFingerprint(null);
  }, [locked]);

  const setPaymentMethod = useCallback((value: PaymentMethod) => {
    if (locked) return;
    setPaymentMethodState(value);
    setSubmitError(null);
    setQuoteConfirmationRequired(false);
    setConfirmedQuoteFingerprint(null);
  }, [locked]);

  const setName = useCallback((value: string) => {
    nameEditedRef.current = true;
    updateField(setNameState, value);
  }, [updateField]);
  const setPhone = useCallback((value: string) => {
    phoneEditedRef.current = true;
    updateField(setPhoneState, value);
  }, [updateField]);
  const setAddress = useCallback((value: string) => updateField(setAddressState, value), [updateField]);
  const setAddressComment = useCallback((value: string) => updateField(setAddressCommentState, value), [updateField]);
  const setComment = useCallback((value: string) => updateField(setCommentState, value), [updateField]);

  const touch = useCallback((field: CheckoutField) => {
    setTouched((current) => current.includes(field) ? current : [...current, field]);
  }, []);

  const finishAttempt = useCallback((attemptKey: string) => {
    if (useAuthStore.getState().userId !== userId) return;
    clearRecoveryRecord(userId);
    setRecoveryRecord(null);
    setAttempt((current) => current?.key === attemptKey ? null : current);
  }, [userId]);

  const performAttempt = useCallback(async (currentAttempt: CheckoutAttempt) => {
    setSubmitError(null);
    try {
      const result = await checkout.mutateAsync({
        payload: currentAttempt.payload,
        checkoutKey: currentAttempt.key,
      });
      const currentAuth = useAuthStore.getState();
      if (currentAuth.userId !== userId || currentAuth.authEpoch !== authEpoch) return;
      finishAttempt(currentAttempt.key);
      setCreatedOrder(result);
    } catch (error) {
      const currentAuth = useAuthStore.getState();
      if (currentAuth.userId !== userId || currentAuth.authEpoch !== authEpoch) return;
      const errorCode = getApiErrorCode(error);
      if (errorCode === "QUOTE_CHANGED") {
        finishAttempt(currentAttempt.key);
        setQuoteConfirmationRequired(true);
        setConfirmedQuoteFingerprint(null);
        setSubmitError("checkout.quote_changed");
        await quoteQuery.refetch();
      } else if (isUnknownOutcome(error)) {
        setAttempt(currentAttempt);
        setRecoveryRecord({
          checkoutKey: currentAttempt.key,
          quoteFingerprint: currentAttempt.payload.expected_quote,
          attemptId: makeUuid(),
        });
        setSubmitError("checkout.unknown_outcome");
      } else {
        finishAttempt(currentAttempt.key);
        setSubmitError(errorCode === "CLIENT_UPDATE_REQUIRED"
          ? "checkout.client_update_required"
          : errorCode === "UNSUPPORTED_PURCHASE_CONTRACT_VERSION"
            ? "checkout.unsupported_version"
            : getApiErrorMessage(error, "checkout.submit_error"));
      }
    }
  }, [authEpoch, checkout, finishAttempt, quoteQuery, userId]);

  const submit = useCallback(async () => {
    if (locked || !isAuthenticated) return;
    setSubmitAttempted(true);
    const validation = getErrors({ name, phone, address }, orderType);
    if (Object.keys(validation).length) return;
    if (!quote?.ready || !quoteOffersPaymentMethod || quote.total === null || !quote.quote_fingerprint) return;
    if (quoteConfirmationRequired && confirmedQuoteFingerprint !== quote.quote_fingerprint) return;
    if ((cart?.items.length ?? 0) === 0) return;

    const addressSnapshot = orderType === "delivery"
      ? { address: address.trim(), address_comment: addressComment.trim() || null }
      : {};
    const payload: CheckoutPayload = {
      order_type: orderType,
      customer_name: name.trim(),
      customer_phone: normalizeUzPhone(phone),
      payment_method: quotePaymentMethod,
      ...addressSnapshot,
      comment: comment.trim() || null,
      purchase_contract_version: 1,
      expected_total: quote.total,
      expected_quote: quote.quote_fingerprint,
    };
    const nextAttempt = { payload, key: makeUuid() };
    if (userId) {
      const record = {
        checkoutKey: nextAttempt.key,
        quoteFingerprint: payload.expected_quote,
        attemptId: makeUuid(),
      };
      writeRecoveryRecord(userId, record);
      setRecoveryRecord(record);
    }
    setAttempt(nextAttempt);
    setSubmitError(null);
    await performAttempt(nextAttempt);
  }, [
    address,
    addressComment,
    cart?.items.length,
    comment,
    confirmedQuoteFingerprint,
    isAuthenticated,
    locked,
    name,
    orderType,
    paymentMethod,
    performAttempt,
    phone,
    quote,
    quoteConfirmationRequired,
    userId,
    quoteOffersPaymentMethod,
    quotePaymentMethod,
  ]);

  const retryUnknown = useCallback(() => {
    if (attempt) void performAttempt(attempt);
  }, [attempt, performAttempt]);

  const confirmUpdatedQuote = useCallback(() => {
    if (!quote?.ready || !quoteOffersPaymentMethod || quote.total === null || !quote.quote_fingerprint || locked) return;
    setConfirmedQuoteFingerprint(quote.quote_fingerprint);
    setQuoteConfirmationRequired(false);
    setSubmitError(null);
    const validation = getErrors({ name, phone, address }, orderType);
    if (Object.keys(validation).length) {
      setSubmitAttempted(true);
      return;
    }
    const addressSnapshot = orderType === "delivery"
      ? { address: address.trim(), address_comment: addressComment.trim() || null }
      : {};
    const payload: CheckoutPayload = {
      order_type: orderType,
      customer_name: name.trim(),
      customer_phone: normalizeUzPhone(phone),
      payment_method: quotePaymentMethod,
      ...addressSnapshot,
      comment: comment.trim() || null,
      purchase_contract_version: 1,
      expected_total: quote.total,
      expected_quote: quote.quote_fingerprint,
    };
    const nextAttempt = { payload, key: makeUuid() };
    if (userId) {
      const record = {
        checkoutKey: nextAttempt.key,
        quoteFingerprint: payload.expected_quote,
        attemptId: makeUuid(),
      };
      writeRecoveryRecord(userId, record);
      setRecoveryRecord(record);
    }
    setAttempt(nextAttempt);
    void performAttempt(nextAttempt);
  }, [address, addressComment, comment, locked, name, orderType, performAttempt, phone, quote, quoteOffersPaymentMethod, quotePaymentMethod, userId]);

  const quoteCanSubmit = Boolean(
    quote?.ready && quoteOffersPaymentMethod && quote.total !== null && quote.quote_fingerprint,
  );
  const quoteConfirmationPassed = !quoteConfirmationRequired || confirmedQuoteFingerprint === quote?.quote_fingerprint;
  const canSubmit = Boolean(
    isAuthenticated &&
    !locked &&
    !checkout.isPending &&
    !cartLoading &&
    (cart?.items.length ?? 0) > 0 &&
    Object.keys(allErrors).length === 0 &&
    quoteCanSubmit &&
    quoteConfirmationPassed,
  );

  return {
    isResettingOwner: ownerRef.current.userId !== userId || ownerRef.current.authEpoch !== authEpoch,
    isAuthenticated,
    profileLoadError: profile.isError,
    retryProfile: () => void profile.refetch(),
    orderType,
    setOrderType,
    name,
    setName,
    phone,
    setPhone,
    address,
    setAddress,
    addressComment,
    setAddressComment,
    paymentMethod,
    setPaymentMethod,
    comment,
    setComment,
    touch,
    errors: visibleErrors,
    cart,
    cartLoading,
    quote,
    quoteMethodAvailable: quoteOffersPaymentMethod,
    quoteLoading: quoteQuery.isLoading || quoteQuery.isFetching,
    quoteError: quoteQuery.isError,
    refreshQuote: () => void quoteQuery.refetch(),
    canSubmit,
    isSubmitting: checkout.isPending,
    locked,
    submitError,
    submit,
    retryUnknown,
    requiresQuoteConfirmation: quoteConfirmationRequired,
    confirmUpdatedQuote,
    recoveryRequired: Boolean(recoveryRecord && !attempt),
    createdOrder,
  };
}
