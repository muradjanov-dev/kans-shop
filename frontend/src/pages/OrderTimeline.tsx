import { useMemo } from "react";
import { useOrderTimeline } from "@/hooks/queries";
import { formatDateTime } from "@/lib/format";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import type { OrderStatus, OrderTimelineEvent, OrderType } from "@/types/api";

const ORDER_STATUSES: readonly OrderStatus[] = [
  "new",
  "confirmed",
  "preparing",
  "delivering",
  "completed",
  "cancelled",
];

const DELIVERY_LIFECYCLE: readonly OrderStatus[] = [
  "new",
  "confirmed",
  "preparing",
  "delivering",
  "completed",
];

const PICKUP_LIFECYCLE: readonly OrderStatus[] = [
  "new",
  "confirmed",
  "preparing",
  "completed",
];

type TimelineState = "completed" | "current" | "pending";

interface TimelineStep {
  status: OrderStatus | null;
  state: TimelineState;
  occurredAt: string | null;
}

function isOrderStatus(value: unknown): value is OrderStatus {
  return typeof value === "string" && ORDER_STATUSES.includes(value as OrderStatus);
}

function isOrderType(value: unknown): value is OrderType {
  return value === "delivery" || value === "pickup" || value === "preorder";
}

function lifecycleFor(orderType: OrderType): readonly OrderStatus[] {
  return orderType === "delivery" ? DELIVERY_LIFECYCLE : PICKUP_LIFECYCLE;
}

function validEvents(
  events: unknown,
  currentStatus: OrderStatus,
  orderType: OrderType,
): OrderTimelineEvent[] | null {
  if (!Array.isArray(events) || events.length === 0) return null;

  const lifecycle = lifecycleFor(orderType);
  const currentIndex = lifecycle.indexOf(currentStatus);
  if (currentStatus !== "cancelled" && currentIndex < 0) return null;

  let previousIndex = -1;
  let previousTimestamp = Number.NEGATIVE_INFINITY;
  const normalized: OrderTimelineEvent[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    if (!event || typeof event !== "object") return null;
    const record = event as Record<string, unknown>;
    if (!isOrderStatus(record.status) || typeof record.occurred_at !== "string") return null;
    const timestamp = Date.parse(record.occurred_at);
    if (!Number.isFinite(timestamp) || timestamp > Date.now() || timestamp < previousTimestamp) return null;

    if (record.status === "cancelled") {
      if (currentStatus !== "cancelled" || index !== events.length - 1 ||
        normalized.some((item) => item.status === "completed")) return null;
    } else {
      const statusIndex = lifecycle.indexOf(record.status);
      if (statusIndex < 0 || statusIndex < previousIndex ||
        (currentStatus !== "cancelled" && statusIndex > currentIndex) ||
        (record.status === "completed" && currentStatus !== "completed")) return null;
      previousIndex = statusIndex;
    }

    normalized.push({ status: record.status, occurred_at: record.occurred_at });
    previousTimestamp = timestamp;
  }
  return normalized;
}

function stepsFor(
  events: OrderTimelineEvent[] | null,
  currentStatus: OrderStatus,
  orderType: OrderType,
): TimelineStep[] {
  if (!events) return [{ status: currentStatus, state: "current", occurredAt: null }];

  const lifecycle = lifecycleFor(orderType);
  const eventByStatus = new Map<OrderStatus, string>();
  for (const event of events) eventByStatus.set(event.status, event.occurred_at);

  if (currentStatus === "cancelled") {
    const historicalSteps = lifecycle.flatMap((status) => {
      const occurredAt = eventByStatus.get(status);
      return occurredAt ? [{ status, state: "completed" as const, occurredAt }] : [];
    });
    return [
      ...historicalSteps,
      {
        status: "cancelled",
        state: "current",
        occurredAt: eventByStatus.get("cancelled") ?? null,
      },
    ];
  }

  const currentIndex = lifecycle.indexOf(currentStatus);
  const result: TimelineStep[] = [];
  lifecycle.forEach((status, index) => {
    if (status === currentStatus) {
      result.push({
        status,
        state: "current",
        occurredAt: eventByStatus.get(status) ?? null,
      });
    } else if (index < currentIndex) {
      const occurredAt = eventByStatus.get(status);
      if (occurredAt) result.push({ status, state: "completed", occurredAt });
    } else {
      result.push({ status, state: "pending", occurredAt: null });
    }
  });
  return result;
}

export function OrderTimeline({
  orderId,
  currentStatus,
  orderType,
}: {
  orderId: number;
  currentStatus: string;
  orderType: string;
}) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const timeline = useOrderTimeline(orderId);
  const currentKnown = isOrderStatus(currentStatus) ? currentStatus : null;
  const knownType = isOrderType(orderType) ? orderType : null;
  const events = useMemo(
    () => currentKnown && knownType
      ? validEvents(timeline.data, currentKnown, knownType)
      : null,
    [currentKnown, knownType, timeline.data],
  );
  const steps = currentKnown && knownType
    ? stepsFor(events, currentKnown, knownType)
    : [{ status: null, state: "current" as const, occurredAt: null }];

  return (
    <section className="my-5 rounded-xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white">
        {t("orders.timeline.title")}
      </h2>
      {timeline.isLoading && (
        <p className="mb-2 text-xs text-gray-500 dark:text-gray-400" role="status">
          {t("orders.timeline.loading")}
        </p>
      )}
      {timeline.isError && (
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-red-700 dark:text-red-200" role="alert">
          <p>{t("orders.timeline.load_error")}</p>
          <button
            className="min-h-11 rounded-lg border border-red-300 px-3 font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-red-300/40"
            onClick={() => void timeline.refetch()}
            type="button"
          >
            {t("common.retry")}
          </button>
        </div>
      )}
      <ol aria-label={t("orders.timeline.accessible_name")} className="flex flex-col gap-2">
        {steps.map((step, index) => {
          const label = step.status
            ? t(`orders.status.${step.status}` as TranslationKey)
            : t("orders.status.unknown");
          const timeText = step.occurredAt ? formatDateTime(step.occurredAt, language) : null;
          return (
            <li
              aria-current={step.state === "current" ? "step" : undefined}
              className={`flex min-h-11 items-start gap-3 rounded-lg px-2 py-2 ${
                step.state === "current"
                  ? "bg-violet-50 dark:bg-violet-400/10"
                  : step.state === "completed"
                    ? "text-slate-700 dark:text-slate-200"
                    : "text-slate-500 dark:text-slate-400"
              }`}
              data-state={step.state}
              key={`${step.status ?? "unknown"}-${index}`}
            >
              <span aria-hidden="true" className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-current text-xs">
                {step.state === "completed" ? "✓" : step.state === "current" ? "●" : "○"}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white">{label}</p>
                {timeText && step.occurredAt && (
                  <time className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400" dateTime={step.occurredAt}>
                    {timeText}
                  </time>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
