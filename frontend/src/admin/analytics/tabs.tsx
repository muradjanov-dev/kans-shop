import { useState, type ReactNode } from "react";
import {
  AdminEmptyState,
  AdminErrorState,
  AdminLoadingState,
  buttonClass,
  formatAdminAmount,
  formatAdminDate,
  inputClass,
} from "@/admin/pages/AdminPageFrame";
import {
  BarList,
  ColumnChart,
  Funnel,
  Heatmap,
  Meter,
  Refetching,
  SimpleTable,
  StatTile,
  VizCard,
  type BarItem,
} from "@/admin/analytics/charts";
import {
  useAnalyticsCustomer,
  useAnalyticsCustomers,
  useAnalyticsReport,
} from "@/admin/analytics/queries";
import { useAnalyticsText, type AnalyticsTextKey } from "@/admin/analytics/text";
import type {
  AnalyticsAmount,
  AnalyticsCount,
  AnalyticsPeriod,
  AnalyticsProductInterest,
} from "@/admin/analytics/types";
import type { DecimalValue } from "@/admin/adminTypes";

interface TabProps {
  period: AnalyticsPeriod;
  includeStaff: boolean;
}

function amount(value: DecimalValue | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** "21.10": short enough for a chart axis, and the same in both languages. */
function shortDay(day: string): string {
  const match = /^\d{4}-(\d{2})-(\d{2})$/.exec(day);
  return match ? `${match[2]}.${match[1]}` : day;
}

function QueryState<T>({
  query,
  isEmpty,
  children,
}: {
  query: { data?: T; isPending: boolean; isError: boolean; isFetching: boolean; isPlaceholderData?: boolean; refetch: () => unknown };
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
}) {
  const { text } = useAnalyticsText();
  if (query.isPending) return <AdminLoadingState />;
  if (query.isError || query.data === undefined) return <AdminErrorState onRetry={() => void query.refetch()} />;
  if (isEmpty?.(query.data)) return <AdminEmptyState>{text("empty")}</AdminEmptyState>;
  return <Refetching active={Boolean(query.isPlaceholderData)}>{children(query.data)}</Refetching>;
}

function useCountItems() {
  const { lookup, number, percent } = useAnalyticsText();
  return (rows: AnalyticsCount[], prefix: string, fallback?: string): BarItem[] => {
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    return rows.map((row) => ({
      key: row.key,
      label: lookup(prefix, row.key, row.key === "direct" && fallback ? fallback : row.key),
      value: row.count,
      display: `${number(row.count)} · ${percent(total ? row.count / total : 0)}`,
    }));
  };
}

/* --------------------------------------------------------------------------- overview */

export function OverviewTab({ period, includeStaff }: TabProps) {
  const { text, number, percent, duration, compact } = useAnalyticsText();
  const summary = useAnalyticsReport("summary", period, includeStaff);
  const countItems = useCountItems();

  return (
    <QueryState query={summary}>
      {(data) => {
        const sales = data.sales;
        const timeline = data.timeline.map((point) => ({ ...point, label: shortDay(point.day) }));
        const sessionsTable = (
          <SimpleTable
            caption={text("chart.sessions")}
            columns={[
              { key: "day", label: text("col.day") },
              { key: "sessions", label: text("kpi.sessions"), numeric: true },
              { key: "visitors", label: text("kpi.visitors"), numeric: true },
              { key: "orders", label: text("kpi.orders"), numeric: true },
              { key: "revenue", label: text("kpi.revenue"), numeric: true },
            ]}
            rows={timeline.map((point) => ({
              day: point.label,
              sessions: number(point.sessions),
              visitors: number(point.visitors),
              orders: number(point.orders),
              revenue: formatAdminAmount(point.revenue),
            }))}
          />
        );
        return (
          <div className="space-y-5">
            <div className="grid min-w-0 grid-cols-2 gap-2.5 sm:gap-3 xl:grid-cols-4">
              <StatTile
                hint={text("kpi.visitors_hint", { new: number(data.new_visitors), returning: number(data.returning_visitors) })}
                label={text("kpi.visitors")}
                value={number(data.visitors)}
              />
              <StatTile
                hint={text("kpi.sessions_hint", { signed: number(data.signed_in_visitors) })}
                label={text("kpi.sessions")}
                value={number(data.sessions)}
              />
              <StatTile label={text("kpi.avg_time")} value={duration(data.avg_session_seconds)} />
              <StatTile
                hint={text("kpi.total_time_hint", { views: number(data.page_views) })}
                label={text("kpi.total_time")}
                value={duration(data.engaged_seconds)}
              />
              <StatTile hint={text("kpi.bounce_hint")} label={text("kpi.bounce")} value={percent(data.bounce_rate)} />
              <StatTile label={text("kpi.conversion")} value={percent(data.conversion_rate)} />
              <StatTile label={text("kpi.product_views")} value={number(data.product_views)} />
              <StatTile label={text("kpi.cart_adds")} value={number(data.cart_adds)} />
            </div>

            <div className="grid min-w-0 grid-cols-2 gap-2.5 sm:gap-3 xl:grid-cols-4">
              <StatTile
                hint={text("kpi.orders_hint", { cancelled: number(sales.cancelled) })}
                label={text("kpi.orders")}
                value={number(sales.orders)}
              />
              <StatTile label={text("kpi.revenue")} value={formatAdminAmount(sales.revenue)} />
              <StatTile label={text("kpi.paid")} value={formatAdminAmount(sales.paid_amount)} />
              <StatTile
                hint={text("kpi.customers_hint", { new: number(sales.new_customers), returning: number(sales.returning_customers) })}
                label={text("kpi.customers")}
                value={number(sales.customers)}
              />
            </div>

            <div className="grid min-w-0 gap-4 xl:grid-cols-2">
              <VizCard table={sessionsTable} title={text("chart.sessions")}>
                <ColumnChart
                  ariaLabel={text("chart.sessions")}
                  points={timeline.map((point) => ({
                    key: point.day,
                    label: point.label,
                    value: point.sessions,
                    display: number(point.sessions),
                  }))}
                  tick={(value) => compact(value)}
                />
              </VizCard>
              <VizCard table={sessionsTable} title={text("chart.revenue")}>
                <ColumnChart
                  ariaLabel={text("chart.revenue")}
                  points={timeline.map((point) => ({
                    key: point.day,
                    label: point.label,
                    value: amount(point.revenue),
                    display: formatAdminAmount(point.revenue),
                  }))}
                  tick={(value) => compact(value)}
                />
              </VizCard>
            </div>

            <div className="grid min-w-0 gap-4 lg:grid-cols-3">
              <VizCard title={text("chart.platforms")}>
                <BarList emptyText={text("empty")} items={countItems(data.platforms, "platform")} />
              </VizCard>
              <VizCard title={text("chart.devices")}>
                <BarList emptyText={text("empty")} items={countItems(data.devices, "device")} />
              </VizCard>
              <VizCard title={text("chart.sources")}>
                <BarList emptyText={text("empty")} items={countItems(data.sources, "source", text("source.direct"))} />
              </VizCard>
            </div>
          </div>
        );
      }}
    </QueryState>
  );
}

/* --------------------------------------------------------------------------- behaviour */

export function BehaviorTab({ period, includeStaff }: TabProps) {
  const t = useAnalyticsText();
  const { text, number, percent, duration, page, target, lookup } = t;
  const behavior = useAnalyticsReport("behavior", period, includeStaff);

  return (
    <QueryState isEmpty={(data) => data.sessions === 0} query={behavior}>
      {(data) => {
        const sessions = data.funnel[0]?.sessions ?? data.sessions;
        const funnel = data.funnel.map((step) => ({
          key: step.key,
          label: text(`funnel.${step.key}` as AnalyticsTextKey),
          value: step.sessions,
          display: number(step.sessions),
          share: text("funnel.share", { share: percent(sessions ? step.sessions / sessions : 0) }),
        }));
        const pages = [...new Set(data.sections.map((section) => section.path))];
        const maxHour = Math.max(0, ...data.hours);
        return (
          <div className="space-y-5">
            <div className="grid min-w-0 gap-4 xl:grid-cols-2">
              <VizCard
                table={<SimpleTable
                  columns={[{ key: "step", label: text("funnel.title") }, { key: "sessions", label: text("kpi.sessions"), numeric: true }, { key: "share", label: text("col.share"), numeric: true }]}
                  rows={funnel.map((step) => ({ step: step.label, sessions: step.display, share: step.share }))}
                />}
                title={text("funnel.title")}
              >
                <Funnel steps={funnel} />
              </VizCard>
              <VizCard
                hint={text("hours.hint")}
                table={<SimpleTable
                  columns={[{ key: "hour", label: text("col.hour") }, { key: "sessions", label: text("kpi.sessions"), numeric: true }]}
                  rows={data.hours.map((count, hour) => ({ hour: `${String(hour).padStart(2, "0")}:00`, sessions: number(count) }))}
                />}
                title={text("hours.title")}
              >
                {maxHour > 0 ? (
                  <ColumnChart
                    ariaLabel={text("hours.title")}
                    height={150}
                    points={data.hours.map((count, hour) => ({
                      key: String(hour),
                      label: String(hour).padStart(2, "0"),
                      value: count,
                      display: `${number(count)} · ${String(hour).padStart(2, "0")}:00`,
                    }))}
                  />
                ) : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
              </VizCard>
            </div>

            <VizCard hint={text("sections.hint")} title={text("sections.title")}>
              {pages.length ? (
                <div className="space-y-5">
                  {pages.map((path) => (
                    <div className="min-w-0" key={path}>
                      <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">{page(path)}</h3>
                      <SimpleTable
                        columns={[
                          { key: "section", label: text("sections.section") },
                          { key: "reach", label: text("sections.reach") },
                          { key: "avg", label: text("sections.avg"), numeric: true },
                          { key: "total", label: text("sections.total"), numeric: true },
                        ]}
                        rows={data.sections
                          .filter((section) => section.path === path)
                          .map((section) => ({
                            section: lookup("section", section.section),
                            reach: <Meter label={percent(section.reach_rate)} ratio={section.reach_rate} />,
                            avg: duration(section.avg_seconds),
                            total: duration(section.total_seconds),
                          }))}
                      />
                    </div>
                  ))}
                </div>
              ) : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
            </VizCard>

            <div className="grid min-w-0 gap-4 xl:grid-cols-2">
              <VizCard title={text("pages.title")}>
                <SimpleTable
                  columns={[
                    { key: "page", label: text("pages.page") },
                    { key: "views", label: text("pages.views"), numeric: true },
                    { key: "sessions", label: text("pages.sessions"), numeric: true },
                    { key: "avg", label: text("pages.avg"), numeric: true },
                  ]}
                  rows={data.pages.map((item) => ({
                    page: page(item.path),
                    views: number(item.views),
                    sessions: number(item.sessions),
                    avg: duration(item.avg_seconds),
                  }))}
                />
              </VizCard>
              <VizCard title={text("scroll.title")}>
                {data.scroll.length ? (
                  <div className="space-y-4">
                    {data.scroll.map((item) => (
                      <div className="min-w-0" key={item.path}>
                        <p className="mb-1.5 text-sm font-medium text-slate-800 dark:text-slate-100">
                          {page(item.path)} <span className="font-normal text-slate-500 dark:text-slate-400">· {number(item.page_views)}</span>
                        </p>
                        <div className="grid gap-1.5 sm:grid-cols-2">
                          {([25, 50, 75, 90] as const).map((depth) => {
                            const ratio = item[`reached_${depth}`];
                            return (
                              <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300" key={depth}>
                                <span className="w-16 shrink-0">{text("scroll.reached", { depth })}</span>
                                <Meter label={percent(ratio)} ratio={ratio} />
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
              </VizCard>
            </div>

            <VizCard title={text("clicks.title")}>
              {data.clicks.length ? (
                <SimpleTable
                  columns={[
                    { key: "element", label: text("clicks.element") },
                    { key: "section", label: text("clicks.section") },
                    { key: "clicks", label: text("clicks.clicks"), numeric: true },
                    { key: "sessions", label: text("clicks.sessions"), numeric: true },
                  ]}
                  rows={data.clicks.map((click) => ({
                    element: target(click.target, click.label),
                    section: click.section ? lookup("section", click.section) : "—",
                    clicks: number(click.clicks),
                    sessions: number(click.sessions),
                  }))}
                />
              ) : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
            </VizCard>

            <div className="grid min-w-0 gap-4 xl:grid-cols-3">
              <VizCard className="xl:col-span-2" title={text("searches.title")}>
                {data.searches.length ? (
                  <SimpleTable
                    columns={[
                      { key: "term", label: text("searches.term") },
                      { key: "count", label: text("searches.count"), numeric: true },
                      { key: "zero", label: text("searches.zero"), numeric: true },
                    ]}
                    rows={data.searches.map((search) => ({
                      term: search.term,
                      count: number(search.searches),
                      zero: search.zero_results > 0
                        ? <span className="inline-flex items-center gap-1 font-semibold text-red-700 dark:text-red-300"><span aria-hidden="true">⚠</span>{number(search.zero_results)}</span>
                        : "0",
                    }))}
                  />
                ) : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
              </VizCard>
              <div className="space-y-4">
                <VizCard title={text("filters.title")}>
                  <BarList
                    emptyText={text("empty")}
                    items={data.filters.map((item) => ({ key: item.key, label: lookup("filter", item.key), value: item.count, display: number(item.count) }))}
                  />
                </VizCard>
                <VizCard title={text("carousel.title")}>
                  <BarList
                    emptyText={text("empty")}
                    items={data.carousel.map((item) => ({ key: item.key, label: lookup("carousel", item.key), value: item.count, display: number(item.count) }))}
                  />
                </VizCard>
              </div>
            </div>
          </div>
        );
      }}
    </QueryState>
  );
}

/* --------------------------------------------------------------------------- products */

function ProductCell({ product }: { product: Pick<AnalyticsProductInterest, "name" | "image_url" | "price"> }) {
  return (
    <span className="flex min-w-[12rem] items-center gap-2.5">
      {product.image_url ? (
        <img alt="" className="size-9 shrink-0 rounded-lg border border-slate-200 bg-white object-contain p-0.5 dark:border-white/10" loading="lazy" src={product.image_url} />
      ) : <span aria-hidden="true" className="size-9 shrink-0 rounded-lg bg-slate-100 dark:bg-white/10" />}
      <span className="min-w-0">
        <span className="block break-words font-medium">{product.name}</span>
        {product.price !== null && <span className="text-xs text-slate-500 dark:text-slate-400">{formatAdminAmount(product.price)}</span>}
      </span>
    </span>
  );
}

export function ProductsTab({ period, includeStaff }: TabProps) {
  const { text, number, percent, duration } = useAnalyticsText();
  const products = useAnalyticsReport("products", period, includeStaff);
  const columns = [
    { key: "product", label: text("products.product") },
    { key: "impressions", label: text("products.impressions"), numeric: true },
    { key: "views", label: text("products.views"), numeric: true },
    { key: "viewers", label: text("products.viewers"), numeric: true },
    { key: "time", label: text("products.time"), numeric: true },
    { key: "cart", label: text("products.cart"), numeric: true },
    { key: "favorites", label: text("products.favorites"), numeric: true },
    { key: "ordered", label: text("products.ordered"), numeric: true },
    { key: "revenue", label: text("products.revenue"), numeric: true },
    { key: "conversion", label: text("products.conversion"), numeric: true },
  ];
  const row = (item: AnalyticsProductInterest) => ({
    product: <ProductCell product={item} />,
    impressions: number(item.impressions),
    views: number(item.views),
    viewers: number(item.viewers),
    time: duration(item.view_seconds),
    cart: number(item.cart_adds),
    favorites: number(item.favorites),
    ordered: number(item.ordered_qty),
    revenue: formatAdminAmount(item.revenue),
    conversion: item.views ? percent(Math.min(item.cart_adds / item.views, 1)) : "—",
  });
  return (
    <QueryState isEmpty={(data) => data.products.length === 0} query={products}>
      {(data) => (
        <div className="space-y-5">
          <VizCard hint={text("products.not_bought_hint")} title={text("products.not_bought")}>
            {data.interested_not_bought.length
              ? <SimpleTable columns={columns} rows={data.interested_not_bought.map(row)} />
              : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
          </VizCard>
          <VizCard title={text("products.title")}>
            <SimpleTable columns={columns} rows={data.products.map(row)} />
          </VizCard>
        </div>
      )}
    </QueryState>
  );
}

/* --------------------------------------------------------------------------- customers */

export function CustomersTab({ period, includeStaff }: TabProps) {
  const { text, number, duration, lookup, page: pageName, target } = useAnalyticsText();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const customers = useAnalyticsCustomers(period, includeStaff, page, search);
  const detail = useAnalyticsCustomer(selected, period);

  return (
    <div className="space-y-5">
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
        <label className="flex min-w-[14rem] flex-1 flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200 sm:max-w-sm">
          <span>{text("customers.search")}</span>
          <input
            className={inputClass}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            type="search"
            value={search}
          />
        </label>
        {customers.data && (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {text("customers.guests", { visitors: number(customers.data.guest_visitors), sessions: number(customers.data.guest_sessions) })}
          </p>
        )}
      </div>

      <QueryState query={customers}>
        {(data) => {
          const pages = Math.max(1, Math.ceil(data.total / data.limit));
          return (
            <VizCard title={text("customers.title")}>
              {data.items.length ? (
                <>
                  <SimpleTable
                    columns={[
                      { key: "customer", label: text("customers.customer") },
                      { key: "activity", label: `${text("customers.sessions")} · ${text("customers.time")}` },
                      { key: "interest", label: `${text("customers.viewed")} · ${text("customers.cart")}` },
                      { key: "orders", label: text("customers.revenue"), numeric: true },
                      { key: "interests", label: text("customers.interests") },
                    ]}
                    rows={data.items.map((customer) => ({
                      customer: (
                        <span className="block min-w-[11rem]">
                          <span className="block font-medium">{customer.name}</span>
                          <span className="block text-xs text-slate-500 dark:text-slate-400">
                            {[customer.username ? `@${customer.username}` : null, customer.phone, lookup("platform", customer.platform)].filter(Boolean).join(" · ")}
                          </span>
                          <button
                            aria-expanded={selected === customer.user_id}
                            className="-ml-2 mt-1 min-h-9 rounded-lg px-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-white/5"
                            onClick={() => setSelected((current) => (current === customer.user_id ? null : customer.user_id))}
                            type="button"
                          >
                            {selected === customer.user_id ? text("customers.close") : text("customers.open")}
                          </button>
                        </span>
                      ),
                      activity: (
                        <span className="block whitespace-nowrap">
                          <span className="block font-medium">{number(customer.sessions)} · {duration(customer.engaged_seconds)}</span>
                          <span className="block text-xs text-slate-500 dark:text-slate-400">{text("customers.last_seen")}: {formatAdminDate(customer.last_seen)}</span>
                        </span>
                      ),
                      interest: `${number(customer.products_viewed)} · ${number(customer.cart_adds)}`,
                      orders: (
                        <span className="block whitespace-nowrap">
                          <span className="block font-medium">{formatAdminAmount(customer.revenue)}</span>
                          <span className="block text-xs text-slate-500 dark:text-slate-400">{text("customers.orders")}: {number(customer.orders)}</span>
                        </span>
                      ),
                      interests: (
                        <span className="flex min-w-[10rem] flex-wrap gap-1">
                          {customer.interests.map((interest) => (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:bg-white/10 dark:text-slate-200" key={interest}>{interest}</span>
                          ))}
                        </span>
                      ),
                    }))}
                  />
                  {pages > 1 && (
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <button className={buttonClass} disabled={page <= 1} onClick={() => setPage((current) => current - 1)} type="button">‹</button>
                      <span className="text-sm text-slate-600 dark:text-slate-300">{page} / {pages}</span>
                      <button className={buttonClass} disabled={page >= pages} onClick={() => setPage((current) => current + 1)} type="button">›</button>
                    </div>
                  )}
                </>
              ) : <AdminEmptyState>{text("empty")}</AdminEmptyState>}
            </VizCard>
          );
        }}
      </QueryState>

      {selected !== null && (
        <QueryState query={detail}>
          {(data) => (
            <VizCard title={text("customers.detail", { name: data.customer.name })}>
              <div className="grid min-w-0 gap-5 xl:grid-cols-2">
                <div className="min-w-0">
                  <h3 className="mb-2 text-sm font-semibold">{text("customers.products")}</h3>
                  <SimpleTable
                    columns={[
                      { key: "name", label: text("products.product") },
                      { key: "views", label: text("products.views"), numeric: true },
                      { key: "time", label: text("products.time"), numeric: true },
                      { key: "cart", label: text("products.cart"), numeric: true },
                      { key: "ordered", label: text("products.ordered"), numeric: true },
                    ]}
                    rows={data.products.map((item) => ({
                      name: item.name,
                      views: number(item.views),
                      time: duration(item.view_seconds),
                      cart: number(item.cart_adds),
                      ordered: number(item.ordered_qty),
                    }))}
                  />
                  {data.searches.length > 0 && (
                    <>
                      <h3 className="mb-2 mt-5 text-sm font-semibold">{text("customers.searches")}</h3>
                      <p className="flex flex-wrap gap-1.5">
                        {data.searches.map((term) => (
                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs dark:bg-white/10" key={term}>{term}</span>
                        ))}
                      </p>
                    </>
                  )}
                  <h3 className="mb-2 mt-5 text-sm font-semibold">{text("customers.history")}</h3>
                  <SimpleTable
                    columns={[
                      { key: "started", label: text("customers.started") },
                      { key: "time", label: text("customers.time"), numeric: true },
                      { key: "pages", label: text("customers.pages"), numeric: true },
                      { key: "entry", label: text("customers.entry") },
                    ]}
                    rows={data.sessions.map((session) => ({
                      started: <span className="whitespace-nowrap">{formatAdminDate(session.started_at)}</span>,
                      time: duration(session.engaged_seconds),
                      pages: number(session.page_views),
                      entry: `${pageName(session.entry_path)} · ${lookup("device", session.device)}`,
                    }))}
                  />
                </div>
                <div className="min-w-0">
                  <h3 className="mb-2 text-sm font-semibold">{text("customers.events")}</h3>
                  <ol className="space-y-2">
                    {data.events.map((event, index) => (
                      <li className="flex min-w-0 gap-3 text-sm" key={`${event.occurred_at}-${index}`}>
                        <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-slate-400">{formatAdminDate(event.occurred_at)}</span>
                        <span className="min-w-0 break-words">
                          <span className="font-medium">{lookup("event", event.type)}</span>
                          {" "}
                          <span className="text-slate-600 dark:text-slate-300">
                            {event.product_name
                              ?? (event.type === "click" || event.type === "carousel" ? target(event.target, event.label) : null)
                              ?? event.label
                              ?? (event.section ? lookup("section", event.section) : pageName(event.path))}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            </VizCard>
          )}
        </QueryState>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------- sales */

export function SalesTab({ period }: TabProps) {
  const { text, number, lookup, language } = useAnalyticsText();
  const sales = useAnalyticsReport("sales", period, false);
  const amountItems = (rows: AnalyticsAmount[], prefix: string): BarItem[] =>
    rows.map((row) => ({
      key: row.key,
      label: lookup(prefix, row.key),
      value: amount(row.amount),
      display: formatAdminAmount(row.amount),
      detail: `${text("sales.orders")}: ${number(row.count)}`,
    }));
  const weekday = (day: number) => text(`weekday.${day}` as AnalyticsTextKey);

  return (
    <QueryState query={sales}>
      {(data) => {
        const summary = data.summary;
        return (
          <div className="space-y-5">
            <div className="grid min-w-0 grid-cols-2 gap-2.5 sm:gap-3 xl:grid-cols-4">
              <StatTile hint={text("kpi.orders_hint", { cancelled: number(summary.cancelled) })} label={text("kpi.orders")} value={number(summary.orders)} />
              <StatTile label={text("kpi.revenue")} value={formatAdminAmount(summary.revenue)} />
              <StatTile label={text("kpi.avg_check")} value={formatAdminAmount(summary.avg_check)} />
              <StatTile
                hint={text("kpi.items_hint", { n: new Intl.NumberFormat(language === "uz" ? "uz-UZ" : "ru-RU", { maximumFractionDigits: 1 }).format(data.avg_items_per_order) })}
                label={text("kpi.items")}
                value={number(summary.items_sold)}
              />
            </div>

            <div className="grid min-w-0 gap-4 lg:grid-cols-3">
              <VizCard title={text("sales.statuses")}>
                <BarList
                  emptyText={text("empty")}
                  items={data.statuses.map((row) => ({ key: row.key, label: lookup("status", row.key), value: row.count, display: number(row.count) }))}
                />
              </VizCard>
              <VizCard title={text("sales.payment_methods")}>
                <BarList emptyText={text("empty")} items={amountItems(data.payment_methods, "payment")} />
              </VizCard>
              <VizCard title={text("sales.order_types")}>
                <BarList emptyText={text("empty")} items={amountItems(data.order_types, "order_type")} />
              </VizCard>
            </div>

            <VizCard
              hint={text("sales.heatmap_hint")}
              table={<SimpleTable
                columns={[{ key: "day", label: text("col.day") }, { key: "hour", label: text("col.hour") }, { key: "orders", label: text("sales.orders"), numeric: true }]}
                rows={[...data.heatmap]
                  .sort((left, right) => left.weekday - right.weekday || left.hour - right.hour)
                  .map((cell) => ({ day: weekday(cell.weekday), hour: `${String(cell.hour).padStart(2, "0")}:00`, orders: number(cell.orders) }))}
              />}
              title={text("sales.heatmap")}
            >
              <Heatmap
                ariaLabel={text("sales.heatmap")}
                cells={data.heatmap.map((cell) => ({ row: cell.weekday, column: cell.hour, value: cell.orders }))}
                less={text("sales.less")}
                more={text("sales.more")}
                rowLabel={weekday}
              />
            </VizCard>

            <div className="grid min-w-0 gap-4 lg:grid-cols-2">
              <VizCard title={text("sales.categories")}>
                <BarList
                  emptyText={text("empty")}
                  items={data.categories.map((row) => ({
                    key: row.key,
                    label: row.key,
                    value: amount(row.amount),
                    display: formatAdminAmount(row.amount),
                    detail: `${text("sales.quantity")}: ${number(row.count)}`,
                  }))}
                />
              </VizCard>
              <VizCard className="lg:col-span-2 lg:row-start-2" title={text("sales.top_products")}>
                <SimpleTable
                  columns={[
                    { key: "name", label: text("products.product") },
                    { key: "quantity", label: text("sales.quantity"), numeric: true },
                    { key: "revenue", label: text("sales.amount"), numeric: true },
                  ]}
                  rows={data.top_products.map((item) => ({ name: item.name, quantity: number(item.quantity), revenue: formatAdminAmount(item.revenue) }))}
                />
              </VizCard>
              <VizCard title={text("sales.top_customers")}>
                <SimpleTable
                  columns={[
                    { key: "name", label: text("customers.customer") },
                    { key: "orders", label: text("sales.orders"), numeric: true },
                    { key: "revenue", label: text("sales.amount"), numeric: true },
                  ]}
                  rows={data.top_customers.map((item) => ({ name: item.name, orders: number(item.orders), revenue: formatAdminAmount(item.revenue) }))}
                />
              </VizCard>
            </div>
          </div>
        );
      }}
    </QueryState>
  );
}

export const ANALYTICS_TABS = ["overview", "behavior", "products", "customers", "sales"] as const;
export type AnalyticsTab = (typeof ANALYTICS_TABS)[number];
