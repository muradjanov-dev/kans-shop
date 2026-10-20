import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { useAnalyticsText } from "@/admin/analytics/text";

/* Charts for the analytics dashboard, drawn as plain SVG/HTML (no chart library).
 * One series per chart in the blue slot, sequential blue for the heatmap; thin marks,
 * hairline grid, a tooltip on hover and keyboard focus, and a table twin for every chart.
 * Colours are CSS tokens on `.admin-viz` in index.css (light and dark). */

export function VizCard({
  title,
  hint,
  table,
  children,
  className = "",
}: {
  title: string;
  hint?: string;
  table?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const { text } = useAnalyticsText();
  const [asTable, setAsTable] = useState(false);
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={`admin-viz min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950 sm:p-5 ${className}`}>
      <div className="mb-3 flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white" id={headingId}>{title}</h2>
          {hint && <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</p>}
        </div>
        {table && (
          <button
            aria-pressed={asTable}
            className="min-h-9 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-white/15 dark:text-slate-300 dark:hover:bg-white/5"
            onClick={() => setAsTable((current) => !current)}
            type="button"
          >
            {asTable ? text("view.chart") : text("view.table")}
          </button>
        )}
      </div>
      {asTable && table ? table : children}
    </section>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <article className="min-w-0 rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-white/10 dark:bg-slate-950 sm:p-4">
      <p className="text-xs leading-5 text-slate-600 dark:text-slate-300 sm:text-sm">{label}</p>
      <p className="mt-1.5 break-words text-xl font-semibold tracking-tight text-slate-900 dark:text-white sm:mt-2 sm:text-2xl">{value}</p>
      {hint && <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</p>}
    </article>
  );
}

export function SimpleTable({
  columns,
  rows,
  caption,
}: {
  columns: Array<{ key: string; label: string; numeric?: boolean }>;
  rows: Array<Record<string, ReactNode>>;
  caption?: string;
}) {
  return (
    <div className="max-w-full overflow-x-auto">
      <table className="w-full min-w-[22rem] border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-white/10 dark:text-slate-400">
            {columns.map((column) => (
              <th className={`px-2 py-2 font-medium ${column.numeric ? "text-right" : ""}`} key={column.key} scope="col">{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr className="border-b border-slate-100 last:border-0 dark:border-white/5" key={index}>
              {columns.map((column) => (
                <td className={`px-2 py-2 align-top text-slate-800 dark:text-slate-100 ${column.numeric ? "whitespace-nowrap text-right tabular-nums" : ""}`} key={column.key}>
                  {row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function useElementWidth(fallback = 600) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(Math.max(240, Math.round(element.getBoundingClientRect().width) || fallback));
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fallback]);
  return { ref, width };
}

function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((candidate) => candidate >= rough) ?? rough;
  const ticks: number[] = [];
  for (let value = 0; value <= max + step * 0.0001; value += step) ticks.push(value);
  if (ticks[ticks.length - 1]! < max) ticks.push(ticks[ticks.length - 1]! + step);
  return ticks;
}

function roundedTopBar(x: number, y: number, width: number, height: number, radius = 4): string {
  if (height <= 0) return "";
  const r = Math.min(radius, width / 2, height);
  return `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height}Z`;
}

export interface ColumnPoint {
  key: string;
  label: string;
  value: number;
  display: string;
}

/** Vertical columns over a category or time axis: one series, hover/arrow-key readout. */
export function ColumnChart({
  points,
  ariaLabel,
  tick = (value: number) => String(value),
  height = 180,
}: {
  points: ColumnPoint[];
  ariaLabel: string;
  tick?: (value: number) => string;
  height?: number;
}) {
  const { ref, width } = useElementWidth();
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(0, ...points.map((point) => point.value));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1] || 1;
  const left = 44;
  const right = 8;
  const plotTop = 18;
  const axisBand = 26;
  const plotWidth = Math.max(width - left - right, 40);
  const band = plotWidth / Math.max(points.length, 1);
  const barWidth = Math.max(2, Math.min(24, band * 0.62));
  const y = (value: number) => plotTop + height - (value / top) * height;
  const labelEvery = Math.max(1, Math.ceil(44 / band));
  const peak = points.reduce((best, point, index) => (point.value > (points[best]?.value ?? -1) ? index : best), 0);

  function pick(event: PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const index = Math.floor((event.clientX - bounds.left - left) / band);
    setActive(index >= 0 && index < points.length ? index : null);
  }

  function keys(event: KeyboardEvent<SVGSVGElement>) {
    if (!points.length) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const step = event.key === "ArrowRight" ? 1 : -1;
      setActive((current) => Math.min(points.length - 1, Math.max(0, (current ?? (step > 0 ? -1 : points.length)) + step)));
    } else if (event.key === "Escape") {
      setActive(null);
    }
  }

  const activePoint = active !== null ? points[active] : undefined;
  const tooltipX = active !== null ? left + active * band + band / 2 : 0;

  return (
    <div className="viz-chart relative" ref={ref}>
      <svg
        aria-label={ariaLabel}
        className="block overflow-visible focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-indigo-500"
        height={plotTop + height + axisBand}
        onBlur={() => setActive(null)}
        onKeyDown={keys}
        onPointerLeave={() => setActive(null)}
        onPointerMove={pick}
        role="img"
        tabIndex={0}
        width={width}
      >
        {ticks.map((value) => (
          <g key={value}>
            <line stroke="var(--viz-grid)" strokeWidth={1} x1={left} x2={width - right} y1={y(value)} y2={y(value)} />
            <text className="viz-tick" dominantBaseline="middle" textAnchor="end" x={left - 6} y={y(value)}>{tick(value)}</text>
          </g>
        ))}
        <line stroke="var(--viz-axis)" strokeWidth={1} x1={left} x2={width - right} y1={y(0)} y2={y(0)} />
        {points.map((point, index) => {
          const x = left + index * band + (band - barWidth) / 2;
          const barTop = y(point.value);
          return (
            <g key={point.key}>
              <path
                d={roundedTopBar(x, barTop, barWidth, y(0) - barTop)}
                fill="var(--viz-series)"
                opacity={active === null || active === index ? 1 : 0.55}
              />
              {index % labelEvery === 0 && (
                <text className="viz-tick" textAnchor="middle" x={x + barWidth / 2} y={y(0) + 16}>{point.label}</text>
              )}
            </g>
          );
        })}
        {points.length > 0 && max > 0 && active === null && (
          <text className="viz-value" textAnchor="middle" x={left + peak * band + band / 2} y={y(points[peak]!.value) - 6}>
            {points[peak]!.display}
          </text>
        )}
      </svg>
      {activePoint && (
        <div
          className="viz-tooltip"
          role="status"
          style={{ left: Math.min(Math.max(tooltipX, 70), width - 70), top: 0 }}
        >
          <strong>{activePoint.display}</strong>
          <span>{activePoint.label}</span>
        </div>
      )}
    </div>
  );
}

export interface BarItem {
  key: string;
  label: string;
  value: number;
  display: string;
  detail?: string;
}

/** Ranked horizontal bars with the value at the tip (one series). */
export function BarList({ items, emptyText }: { items: BarItem[]; emptyText?: string }) {
  const max = Math.max(0, ...items.map((item) => item.value));
  if (!items.length) return <p className="text-sm text-slate-500 dark:text-slate-400">{emptyText ?? "—"}</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li className="min-w-0" key={item.key}>
          <div className="flex min-w-0 items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 break-words text-slate-700 dark:text-slate-200">{item.label}</span>
            <span className="shrink-0 font-semibold tabular-nums text-slate-900 dark:text-white">{item.display}</span>
          </div>
          <div aria-hidden="true" className="viz-track mt-1">
            <span className="viz-fill" style={{ width: `${max > 0 ? Math.max((item.value / max) * 100, item.value > 0 ? 1.5 : 0) : 0}%` }} />
          </div>
          {item.detail && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{item.detail}</p>}
        </li>
      ))}
    </ul>
  );
}

/** A share of a whole on a same-ramp track (reach of a page section, scroll depth). */
export function Meter({ ratio, label }: { ratio: number; label: string }) {
  const clamped = Math.min(Math.max(ratio, 0), 1);
  return (
    <div className="flex min-w-[7rem] items-center gap-2">
      <div aria-hidden="true" className="viz-track flex-1">
        <span className="viz-fill" style={{ width: `${clamped * 100}%` }} />
      </div>
      <span className="w-12 shrink-0 text-right text-xs font-semibold tabular-nums text-slate-800 dark:text-slate-100">{label}</span>
    </div>
  );
}

const HEAT_STEPS = 7;

/** Orders by weekday × hour on a sequential blue ramp, with a scale legend. */
export function Heatmap({
  cells,
  rowLabel,
  less,
  more,
  ariaLabel,
}: {
  cells: Array<{ row: number; column: number; value: number }>;
  rowLabel: (row: number) => string;
  less: string;
  more: string;
  ariaLabel: string;
}) {
  const { number } = useAnalyticsText();
  const grid = useMemo(() => {
    const values = new Map<string, number>();
    for (const cell of cells) values.set(`${cell.row}:${cell.column}`, cell.value);
    return values;
  }, [cells]);
  const max = Math.max(0, ...cells.map((cell) => cell.value));
  const [active, setActive] = useState<{ row: number; column: number } | null>(null);
  const rows = [1, 2, 3, 4, 5, 6, 7];
  const step = (value: number) => (value <= 0 || max <= 0 ? -1 : Math.min(HEAT_STEPS - 1, Math.ceil((value / max) * HEAT_STEPS) - 1));

  function keys(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, [number, number]> = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] };
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    setActive((current) => {
      const base = current ?? { row: 1, column: 0 };
      return {
        row: Math.min(7, Math.max(1, base.row + move[0])),
        column: Math.min(23, Math.max(0, base.column + move[1])),
      };
    });
  }

  const activeValue = active ? grid.get(`${active.row}:${active.column}`) ?? 0 : 0;
  return (
    <div className="viz-chart">
      <div
        aria-label={ariaLabel}
        className="max-w-full overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-indigo-500"
        onBlur={() => setActive(null)}
        onKeyDown={keys}
        onPointerLeave={() => setActive(null)}
        role="img"
        tabIndex={0}
      >
        <div className="viz-heatmap">
          {rows.map((row) => (
            <div className="viz-heat-row" key={row}>
              <span className="viz-tick w-7 shrink-0">{rowLabel(row)}</span>
              {Array.from({ length: 24 }, (_, column) => {
                const value = grid.get(`${row}:${column}`) ?? 0;
                const level = step(value);
                const isActive = active?.row === row && active.column === column;
                return (
                  <span
                    className={`viz-heat-cell${isActive ? " is-active" : ""}`}
                    key={column}
                    onPointerEnter={() => setActive({ row, column })}
                    style={{ background: level < 0 ? "var(--viz-empty)" : `var(--viz-seq-${level})` }}
                  />
                );
              })}
            </div>
          ))}
          <div className="viz-heat-row">
            <span className="w-7 shrink-0" />
            {Array.from({ length: 24 }, (_, column) => (
              <span className="viz-tick viz-heat-hour" key={column}>{column % 3 === 0 ? column : ""}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div aria-hidden="true" className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          <span>{less}</span>
          {Array.from({ length: HEAT_STEPS }, (_, level) => (
            <span className="viz-legend-cell" key={level} style={{ background: `var(--viz-seq-${level})` }} />
          ))}
          <span>{more}</span>
        </div>
        <p aria-live="polite" className="min-h-5 text-sm text-slate-700 dark:text-slate-200">
          {active && (
            <>
              <strong className="font-semibold">{number(activeValue)}</strong>{" "}
              <span className="text-slate-500 dark:text-slate-400">· {rowLabel(active.row)} {String(active.column).padStart(2, "0")}:00</span>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

/** Stage-by-stage drop-off: each bar is sessions that reached the step. */
export function Funnel({ steps }: { steps: Array<{ key: string; label: string; value: number; display: string; share: string }> }) {
  const first = steps[0]?.value ?? 0;
  return (
    <ol className="space-y-3">
      {steps.map((step) => (
        <li className="min-w-0" key={step.key}>
          <div className="flex min-w-0 items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 text-slate-700 dark:text-slate-200">{step.label}</span>
            <span className="shrink-0 text-slate-500 dark:text-slate-400">
              <strong className="mr-1.5 font-semibold tabular-nums text-slate-900 dark:text-white">{step.display}</strong>
              {step.share}
            </span>
          </div>
          <div aria-hidden="true" className="viz-track viz-track-tall mt-1">
            <span className="viz-fill" style={{ width: `${first > 0 ? Math.max((step.value / first) * 100, step.value > 0 ? 1.5 : 0) : 0}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Keeps the previous render visible (dimmed) while a new period loads. */
export function Refetching({ active, children }: { active: boolean; children: ReactNode }) {
  const [shown, setShown] = useState(active);
  useEffect(() => {
    if (active) {
      const timer = window.setTimeout(() => setShown(true), 150);
      return () => window.clearTimeout(timer);
    }
    setShown(false);
    return undefined;
  }, [active]);
  return <div aria-busy={active} className={`transition-opacity ${shown ? "opacity-50" : "opacity-100"}`}>{children}</div>;
}
