import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useOrderHistory } from "@/hooks/queries";
import { formatDateTime, formatExactPrice } from "@/lib/format";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";
import type { OrderStatus, OrderType, PaymentStatus } from "@/types/api";

const ORDER_STATUSES: readonly OrderStatus[] = [
  "new",
  "confirmed",
  "preparing",
  "delivering",
  "completed",
  "cancelled",
];

const ORDER_TYPES: readonly OrderType[] = ["delivery", "pickup", "preorder"];
const PAYMENT_STATUSES: readonly PaymentStatus[] = [
  "pending",
  "receipt_uploaded",
  "paid",
  "failed",
];

const STATUS_COLORS: Record<OrderStatus, string> = {
  new: "bg-[var(--soft)] text-brand",
  confirmed: "bg-[#DCEADF] text-[#153F32]",
  preparing: "bg-amber-100 text-amber-700",
  delivering: "bg-[#E2EEF4] text-[#315D72]",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700",
};

function isOrderStatus(value: unknown): value is OrderStatus {
  return (
    typeof value === "string" && ORDER_STATUSES.includes(value as OrderStatus)
  );
}

function isOrderType(value: unknown): value is OrderType {
  return typeof value === "string" && ORDER_TYPES.includes(value as OrderType);
}

function isPaymentStatus(value: unknown): value is PaymentStatus {
  return (
    typeof value === "string" &&
    PAYMENT_STATUSES.includes(value as PaymentStatus)
  );
}

export function OrdersPage() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const { openLogin } = useCustomerAuth();
  const [page, setPage] = useState(1);
  const isAuthenticated = Boolean(accessToken && userId);
  const history = useOrderHistory(page);
  const totalPagesValue = history.data?.total_pages;
  const totalPages =
    typeof totalPagesValue === "number" &&
    Number.isSafeInteger(totalPagesValue) &&
    totalPagesValue > 0
      ? totalPagesValue
      : 1;
  const items = Array.isArray(history.data?.items) ? history.data.items : [];

  useEffect(() => {
    setPage(1);
  }, [userId]);

  useEffect(() => {
    if (history.data && page > totalPages) setPage(totalPages);
  }, [history.data, page, totalPages]);

  if (!isAuthenticated) {
    return (
      <div className="page-shell empty-state flex flex-col items-center gap-4">
        <p className="text-sm text-[var(--muted)] dark:text-gray-400">
          {t("orders.open_telegram")}
        </p>
        <button
          className="primary-button focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          onClick={openLogin}
          type="button"
        >
          {t("auth.sign_in")}
        </button>
      </div>
    );
  }
  if (history.isLoading) return <Spinner />;
  if (history.isError)
    return <ErrorState onRetry={() => void history.refetch()} />;

  return (
    <div className="page-shell page-shell-wide">
      <h1 className="page-title mb-7 dark:text-white">{t("orders.title")}</h1>
      {items.length === 0 ? (
        <p className="surface empty-state text-sm text-[var(--muted)] dark:text-gray-400 dark:border-white/10 dark:bg-slate-900">
          {t("orders.empty")}
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((order) => {
            const status = isOrderStatus(order.status) ? order.status : null;
            const orderType = isOrderType(order.order_type)
              ? order.order_type
              : null;
            const paymentStatus = isPaymentStatus(order.payment_status)
              ? order.payment_status
              : null;
            const orderDate =
              typeof order.created_at === "string"
                ? formatDateTime(order.created_at, language)
                : null;
            return (
              <Link
                aria-label={t("orders.open_order", {
                  number: order.order_number,
                })}
                className="surface flex min-h-11 flex-col gap-5 p-5 sm:p-6 transition-colors hover:border-[#94A187] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/10 dark:bg-slate-900"
                key={order.id}
                to={`/orders/${order.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-lg font-bold text-brand dark:text-white">
                      {t("orders.number")} {order.order_number}
                    </p>
                    {orderDate && (
                      <time
                        className="mt-1 block text-xs text-[var(--muted)] dark:text-gray-400"
                        dateTime={order.created_at}
                      >
                        {orderDate}
                      </time>
                    )}
                  </div>
                  <p className="shrink-0 text-lg font-bold text-brand dark:text-white">
                    {formatExactPrice(
                      typeof order.total === "string" ? order.total : "",
                    )}{" "}
                    {t("common.som")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span
                    className={`rounded-full px-2.5 py-1 font-medium ${status ? STATUS_COLORS[status] : "bg-[var(--soft)] text-[var(--ink)]"}`}
                  >
                    {status
                      ? t(`orders.status.${status}` as TranslationKey)
                      : t("orders.status.unknown")}
                  </span>
                  <span className="rounded-full bg-[var(--soft)] px-2.5 py-1 text-[var(--ink)] dark:text-white dark:bg-slate-800">
                    {orderType
                      ? t(`orders.order_type.${orderType}` as TranslationKey)
                      : t("orders.order_type.unknown")}
                  </span>
                  <span className="text-[var(--muted)] dark:text-gray-400">
                    {t("orders.payment_status_label")}:{" "}
                    {paymentStatus
                      ? t(
                          `checkout.payment_status.${paymentStatus}` as TranslationKey,
                        )
                      : t("orders.payment_status.unknown")}
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {history.data && totalPages > 1 && (
        <nav
          aria-label={t("orders.history.pagination")}
          className="mt-5 flex items-center justify-center gap-3"
        >
          <button
            className="secondary-button min-w-11 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            type="button"
          >
            {t("orders.history.previous")}
          </button>
          <span
            aria-live="polite"
            className="text-sm text-[var(--muted)] dark:text-gray-400"
          >
            {t("orders.history.page", {
              page: Math.min(page, totalPages),
              total: totalPages,
            })}
          </span>
          <button
            className="secondary-button min-w-11 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
            disabled={page >= totalPages}
            onClick={() =>
              setPage((current) => Math.min(totalPages, current + 1))
            }
            type="button"
          >
            {t("orders.history.next")}
          </button>
        </nav>
      )}
    </div>
  );
}
