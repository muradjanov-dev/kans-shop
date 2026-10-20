import { useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { AdminPageFrame } from "@/admin/pages/AdminPageFrame";
import {
  ANALYTICS_TABS,
  BehaviorTab,
  CustomersTab,
  OverviewTab,
  ProductsTab,
  SalesTab,
  type AnalyticsTab,
} from "@/admin/analytics/tabs";
import { useAnalyticsText, type AnalyticsTextKey } from "@/admin/analytics/text";
import type { AnalyticsPeriod } from "@/admin/analytics/types";

const PERIODS: AnalyticsPeriod[] = ["today", "week", "month", "quarter"];
const PERIOD_KEY = "kans-admin-analytics-period";

function storedPeriod(): AnalyticsPeriod {
  try {
    const value = localStorage.getItem(PERIOD_KEY);
    return PERIODS.includes(value as AnalyticsPeriod) ? (value as AnalyticsPeriod) : "week";
  } catch {
    return "week";
  }
}

/** Customer behaviour and sales in one place: filters on top, five tabs below. */
export function AnalyticsPage({ route }: AdminPageProps) {
  const { text } = useAnalyticsText();
  const [params, setParams] = useSearchParams();
  const [period, setPeriodState] = useState<AnalyticsPeriod>(storedPeriod);
  const [includeStaff, setIncludeStaff] = useState(false);
  const requested = params.get("tab");
  const tab: AnalyticsTab = ANALYTICS_TABS.includes(requested as AnalyticsTab) ? (requested as AnalyticsTab) : "overview";

  function setPeriod(next: AnalyticsPeriod) {
    setPeriodState(next);
    try {
      localStorage.setItem(PERIOD_KEY, next);
    } catch {
      // Private mode: the choice simply is not remembered.
    }
  }

  function selectTab(next: AnalyticsTab) {
    setParams((current) => {
      const updated = new URLSearchParams(current);
      updated.set("tab", next);
      return updated;
    }, { replace: true });
  }

  function tabKeys(event: KeyboardEvent<HTMLDivElement>) {
    const index = ANALYTICS_TABS.indexOf(tab);
    const next = event.key === "ArrowRight" ? index + 1 : event.key === "ArrowLeft" ? index - 1 : null;
    if (next === null) return;
    event.preventDefault();
    const target = ANALYTICS_TABS[(next + ANALYTICS_TABS.length) % ANALYTICS_TABS.length]!;
    selectTab(target);
    document.getElementById(`analytics-tab-${target}`)?.focus();
  }

  const props = { period, includeStaff };
  return (
    <AdminPageFrame route={route}>
      <div className="mb-4 flex min-w-0 flex-wrap items-center gap-3">
        <div aria-label={text("period.label")} className="inline-flex flex-wrap rounded-xl border border-slate-200 bg-white p-1 dark:border-white/10 dark:bg-slate-950" role="group">
          {PERIODS.map((value) => (
            <button
              aria-pressed={period === value}
              className={`min-h-10 rounded-lg px-3.5 text-sm font-semibold ${period === value
                ? "bg-indigo-600 text-white"
                : "text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-white/5"}`}
              key={value}
              onClick={() => setPeriod(value)}
              type="button"
            >
              {text(`period.${value}` as AnalyticsTextKey)}
            </button>
          ))}
        </div>
        {tab !== "sales" && (
          <label className="inline-flex min-h-10 items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <input checked={includeStaff} className="size-4 accent-indigo-600" onChange={(event) => setIncludeStaff(event.target.checked)} type="checkbox" />
            {text("filters.staff")}
          </label>
        )}
      </div>

      <div
        aria-label={text("tabs.label")}
        className="mb-5 flex min-w-0 gap-1 overflow-x-auto border-b border-slate-200 dark:border-white/10"
        onKeyDown={tabKeys}
        role="tablist"
      >
        {ANALYTICS_TABS.map((value) => (
          <button
            aria-controls={`analytics-panel-${value}`}
            aria-selected={tab === value}
            className={`-mb-px min-h-11 shrink-0 border-b-2 px-3.5 text-sm font-semibold ${tab === value
              ? "border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-200"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white"}`}
            id={`analytics-tab-${value}`}
            key={value}
            onClick={() => selectTab(value)}
            role="tab"
            tabIndex={tab === value ? 0 : -1}
            type="button"
          >
            {text(`tabs.${value}` as AnalyticsTextKey)}
          </button>
        ))}
      </div>

      <div aria-labelledby={`analytics-tab-${tab}`} id={`analytics-panel-${tab}`} role="tabpanel">
        {tab === "overview" && <OverviewTab {...props} />}
        {tab === "behavior" && <BehaviorTab {...props} />}
        {tab === "products" && <ProductsTab {...props} />}
        {tab === "customers" && <CustomersTab {...props} />}
        {tab === "sales" && <SalesTab {...props} />}
      </div>
    </AdminPageFrame>
  );
}
