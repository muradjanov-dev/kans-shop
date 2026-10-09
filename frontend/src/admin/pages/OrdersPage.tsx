import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminOrder, AdminOrderDetail, OrderStatus } from "@/admin/adminTypes";
import type { AdminPageProps } from "@/admin/adminRoutes";
import {
  acceptAdminOrderPayment,
  adminQueryKeys,
  readAdminOrderReceipt,
  queueAdminOrderMessage,
  updateAdminOrderStatus,
  useAdminOrder,
  useAdminOrders,
} from "@/admin/adminQueries";
import { getAdminApiErrorCode } from "@/admin/api";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import {
  AdminActionError,
  AdminEmptyState,
  AdminErrorState,
  AdminField,
  AdminLoadingState,
  AdminPageFrame,
  AdminPanel,
  buttonClass,
  formatAdminAmount,
  formatAdminDate,
  primaryButtonClass,
} from "@/admin/pages/AdminPageFrame";

const orderStatuses: OrderStatus[] = ["new", "confirmed", "preparing", "delivering", "completed", "cancelled"];

export function OrdersPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const filters = useMemo(() => ({
    page,
    limit: 20,
    ...(status ? { status } : {}),
    ...(query.trim() ? { query: query.trim() } : {}),
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  }), [dateFrom, dateTo, page, query, status]);
  const orders = useAdminOrders(filters);
  const order = useAdminOrder(selectedId);

  async function refreshOrderViews(id: number) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin", "orders"] }),
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.order(id) }),
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.dashboard() }),
    ]);
  }

  const statusMutation = useMutation({
    mutationFn: ({ id, nextStatus, comment }: { id: number; nextStatus: string; comment: string }) =>
      updateAdminOrderStatus(id, { status: nextStatus, comment: comment || undefined }),
    onSuccess: async (_updated, variables) => refreshOrderViews(variables.id),
  });
  const paymentMutation = useMutation({
    mutationFn: ({ id, receiptVersion }: { id: number; receiptVersion: number }) => acceptAdminOrderPayment(id, receiptVersion),
    onSuccess: async (_updated, variables) => refreshOrderViews(variables.id),
  });
  const messageMutation = useMutation({
    mutationFn: ({ id, text, key }: { id: number; text: string; key: string }) => queueAdminOrderMessage(id, text, key),
  });

  return (
    <AdminPageFrame route={route}>
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <AdminPanel>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <AdminField label={t("admin.orders.search")}>
              {(className) => <input className={className} onChange={(event) => { setQuery(event.target.value); setPage(1); }} value={query} />}
            </AdminField>
            <AdminField label={t("admin.orders.status")}>
              {(className) => <select className={className} onChange={(event) => { setStatus(event.target.value); setPage(1); }} value={status}>
                <option value="">{t("admin.orders.all")}</option>
                {orderStatuses.map((item) => <option key={item} value={item}>{statusLabel(item, t)}</option>)}
              </select>}
            </AdminField>
            <AdminField label={t("admin.orders.date_from")}>
              {(className) => <input className={className} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} type="date" value={dateFrom} />}
            </AdminField>
            <AdminField label={t("admin.orders.date_to")}>
              {(className) => <input className={className} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} type="date" value={dateTo} />}
            </AdminField>
          </div>
          <div className="mt-4 space-y-2" aria-live="polite">
            {orders.isPending ? <AdminLoadingState /> : orders.isError ? <AdminErrorState onRetry={() => void orders.refetch()} /> : orders.data?.items.length ? orders.data.items.map((item) => (
              <OrderRow item={item} key={item.id} selected={selectedId === item.id} onSelect={() => { setSelectedId(item.id); messageMutation.reset(); }} />
            )) : <AdminEmptyState />}
          </div>
          {orders.data && <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("admin.common.page", { page: orders.data.page, total: orders.data.total_pages })}</p>
            <div className="flex gap-2">
              <button className={buttonClass} disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} type="button">{t("admin.common.previous")}</button>
              <button className={buttonClass} disabled={page >= orders.data.total_pages} onClick={() => setPage((value) => value + 1)} type="button">{t("admin.common.next")}</button>
            </div>
          </div>}
        </AdminPanel>

        <div className="min-w-0">
          {selectedId === null ? <AdminEmptyState>{t("admin.orders.select")}</AdminEmptyState>
            : order.isPending ? <AdminLoadingState />
              : order.isError ? <AdminErrorState onRetry={() => void order.refetch()} />
                : order.data && <OrderDetails
                  order={order.data}
                  statusPending={statusMutation.isPending}
                  statusError={statusMutation.error}
                  paymentPending={paymentMutation.isPending}
                  paymentError={paymentMutation.error}
                  messagePending={messageMutation.isPending}
                  messageError={messageMutation.error}
                  queuedMessageId={messageMutation.data?.message_id ?? null}
                  onStatus={(nextStatus, comment) => statusMutation.mutate({ id: order.data!.id, nextStatus, comment })}
                  onAcceptPayment={() => paymentMutation.mutate({ id: order.data!.id, receiptVersion: order.data!.receipt_version })}
                  onQueueMessage={(text) => messageMutation.mutate({ id: order.data!.id, text, key: crypto.randomUUID() })}
                />}
        </div>
      </div>
    </AdminPageFrame>
  );
}

function OrderRow({ item, selected, onSelect }: { item: AdminOrder; selected: boolean; onSelect: () => void }) {
  return <button aria-pressed={selected} className={`block min-h-11 w-full rounded-lg border p-3 text-left transition ${selected ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-400/10" : "border-slate-200 hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"}`} onClick={onSelect} type="button">
    <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
      <span className="font-semibold text-slate-900 dark:text-white">#{item.order_number}</span>
      <span className="rounded-full bg-slate-100 px-2 py-1 text-xs dark:bg-white/10">{statusLabel(item.status, useTranslate())}</span>
    </span>
    <span className="mt-1 block truncate text-sm text-slate-600 dark:text-slate-300">{item.customer_name} · {formatAdminAmount(item.total)}</span>
    <span className="mt-1 block text-xs text-slate-500">{formatAdminDate(item.created_at)}</span>
  </button>;
}

function OrderDetails({
  order,
  statusPending,
  statusError,
  paymentPending,
  paymentError,
  messagePending,
  messageError,
  queuedMessageId,
  onStatus,
  onAcceptPayment,
  onQueueMessage,
}: {
  order: AdminOrderDetail;
  statusPending: boolean;
  statusError: unknown;
  paymentPending: boolean;
  paymentError: unknown;
  messagePending: boolean;
  messageError: unknown;
  queuedMessageId: number | null;
  onStatus: (status: string, comment: string) => void;
  onAcceptPayment: () => void;
  onQueueMessage: (text: string) => void;
}) {
  const t = useTranslate();
  const [nextStatus, setNextStatus] = useState(order.status);
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("");
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null);
  const [receiptError, setReceiptError] = useState(false);
  useEffect(() => {
    setNextStatus(order.status);
    setComment("");
    setMessage("");
    setReceiptError(false);
  }, [order.id, order.status]);
  useEffect(() => () => { if (receiptUrl) URL.revokeObjectURL(receiptUrl); }, [receiptUrl]);

  async function openReceipt() {
    setReceiptError(false);
    try {
      const blob = await readAdminOrderReceipt(order.id);
      setReceiptUrl((current) => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(blob); });
    } catch {
      setReceiptError(true);
    }
  }

  return <AdminPanel title={`#${order.order_number}`}>
    <div className="grid min-w-0 gap-4 sm:grid-cols-2">
      <div><p className="text-xs uppercase tracking-wide text-slate-500">{t("admin.orders.customer")}</p><p className="mt-1 break-words font-semibold">{order.customer_name}</p><p className="mt-1 break-all text-sm">{order.customer_phone}</p></div>
      <div><p className="text-xs uppercase tracking-wide text-slate-500">{t("admin.orders.payment")}</p><p className="mt-1 font-medium">{paymentMethodLabel(order.payment_method, t)} · {paymentStatusLabel(order.payment_status, t)}</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{t("admin.orders.total")}: {formatAdminAmount(order.total)}</p></div>
    </div>
    {(order.address || order.address_comment || order.comment) && <div className="mt-4 rounded-lg bg-slate-50 p-3 text-sm dark:bg-white/5">{order.address && <p className="break-words">{order.address}</p>}{order.address_comment && <p>{order.address_comment}</p>}{order.comment && <p>{order.comment}</p>}</div>}

    <div className="mt-5">
      <h3 className="font-semibold">{t("admin.orders.items")}</h3>
      <ul className="mt-2 divide-y divide-slate-100 dark:divide-white/10">
        {order.items.map((item) => <li className="flex min-w-0 justify-between gap-3 py-2 text-sm" key={item.id}><span className="min-w-0 break-words">{item.product_name_snapshot} × {item.quantity}</span><span className="shrink-0">{formatAdminAmount(item.total)}</span></li>)}
      </ul>
    </div>

    <div className="mt-5 grid min-w-0 gap-3 sm:grid-cols-2">
      <AdminField label={t("admin.orders.update_status")}>
        {(className) => <select className={className} onChange={(event) => setNextStatus(event.target.value as OrderStatus)} value={nextStatus}>
          {orderStatuses.map((value) => <option key={value} value={value}>{statusLabel(value, t)}</option>)}
        </select>}
      </AdminField>
      <AdminField label={t("admin.orders.status_comment")}>
        {(className) => <input className={className} onChange={(event) => setComment(event.target.value)} value={comment} />}
      </AdminField>
    </div>
    <button className={`${primaryButtonClass} mt-3 w-full sm:w-auto`} disabled={statusPending || nextStatus === order.status} onClick={() => onStatus(nextStatus, comment)} type="button">{t("admin.orders.update_status")}</button>
    {statusError != null && <div className="mt-3"><AdminActionError code={getAdminApiErrorCode(statusError)} /></div>}

    {order.has_receipt && <div className="mt-4 flex flex-wrap items-center gap-3">
      <button className={buttonClass} onClick={() => void openReceipt()} type="button">{t("admin.orders.receipt")}</button>
      {receiptUrl && <a className="min-h-11 inline-flex items-center text-sm font-semibold text-indigo-700 underline dark:text-indigo-300" href={receiptUrl} rel="noreferrer" target="_blank">{t("admin.orders.receipt")}</a>}
      {order.payment_method === "card_transfer" && order.payment_status === "receipt_uploaded" && <button className={primaryButtonClass} disabled={paymentPending} onClick={onAcceptPayment} type="button">{t("admin.orders.accept_payment")}</button>}
      {receiptError && <p className="text-sm text-red-700" role="alert">{t("admin.common.load_error")}</p>}
    </div>}
    {paymentError != null && <div className="mt-3"><AdminActionError code={getAdminApiErrorCode(paymentError)} /></div>}

    <HistoryList title={t("admin.orders.history")} items={order.status_history.map((item) => `${item.from_status ? statusLabel(item.from_status, t) : "—"} → ${statusLabel(item.to_status, t)} · ${formatAdminDate(item.created_at)}${item.comment ? ` · ${item.comment}` : ""}`)} />
    <HistoryList title={t("admin.orders.payment_history")} items={[
      ...order.payment_history.map((item) => `${item.provider} · ${item.state} · ${formatAdminAmount(item.amount)} · ${formatAdminDate(item.created_at)}`),
      ...order.payment_review_history.map((item) => `${item.actor_name_snapshot ?? item.actor_admin_id ?? "—"} · ${item.action} · ${formatAdminDate(item.created_at)}`),
    ]} />

    <form className="mt-5 border-t border-slate-200 pt-4 dark:border-white/10" onSubmit={(event) => { event.preventDefault(); if (message.trim() && message.length <= 4096) onQueueMessage(message); }}>
      <AdminField label={t("admin.orders.message")}>
        {(className) => <textarea className={`${className} min-h-28`} maxLength={4096} onChange={(event) => setMessage(event.target.value)} value={message} />}
      </AdminField>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-slate-500">{message.length} / 4096</span>
        <button className={primaryButtonClass} disabled={messagePending || !message.trim() || message.length > 4096} type="submit">{messagePending ? t("admin.common.loading") : t("admin.orders.send_message")}</button>
      </div>
      {messageError != null && <div className="mt-3"><AdminActionError code={getAdminApiErrorCode(messageError)} /></div>}
      {queuedMessageId !== null && <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300" role="status">{t("admin.orders.message_queued", { id: queuedMessageId })}</p>}
    </form>
  </AdminPanel>;
}

function HistoryList({ title, items }: { title: string; items: string[] }) {
  return <section className="mt-5 border-t border-slate-200 pt-4 dark:border-white/10">
    <h3 className="font-semibold">{title}</h3>
    {items.length ? <ul className="mt-2 space-y-2 text-sm text-slate-600 dark:text-slate-300">{items.map((item, index) => <li className="break-words" key={`${item}-${index}`}>{item}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">—</p>}
  </section>;
}

function statusLabel(status: OrderStatus, t: ReturnType<typeof useTranslate>) {
  const key = `orders.status.${status}` as const;
  return t(key);
}

function paymentMethodLabel(method: string, t: ReturnType<typeof useTranslate>) {
  const key = `checkout.payment.${method}` as TranslationKey;
  const translated = t(key);
  return translated === key ? method : translated;
}

function paymentStatusLabel(status: string, t: ReturnType<typeof useTranslate>) {
  const key = `checkout.payment_status.${status}` as TranslationKey;
  const translated = t(key);
  return translated === key ? status : translated;
}
