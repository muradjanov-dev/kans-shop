import { useTranslate } from "@/lib/i18n";
import type { CatalogQuery, CatalogSort } from "@/types/api";

export type CatalogFilterValues = Pick<
  CatalogQuery,
  "min_price" | "max_price" | "in_stock" | "sort"
>;

export function CatalogFilters({
  values,
  onChange,
  onClear,
}: {
  values: CatalogFilterValues;
  onChange: (values: Partial<CatalogFilterValues>) => void;
  onClear: () => void;
}) {
  const t = useTranslate();

  return (
    <fieldset className="mb-5 grid grid-cols-2 gap-3 rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-900 sm:grid-cols-4">
      <legend className="sr-only">{t("catalog.filters")}</legend>
      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-600 dark:text-slate-300">
        {t("catalog.min_price")}
        <input
          aria-label={t("catalog.min_price")}
          className="min-h-11 w-full rounded-lg border border-slate-200 bg-transparent px-3 text-sm text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:text-white"
          inputMode="decimal"
          onChange={(event) => onChange({ min_price: event.target.value })}
          type="text"
          value={values.min_price}
        />
      </label>
      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-600 dark:text-slate-300">
        {t("catalog.max_price")}
        <input
          aria-label={t("catalog.max_price")}
          className="min-h-11 w-full rounded-lg border border-slate-200 bg-transparent px-3 text-sm text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:text-white"
          inputMode="decimal"
          onChange={(event) => onChange({ max_price: event.target.value })}
          type="text"
          value={values.max_price}
        />
      </label>
      <label className="flex min-h-11 items-center gap-2 self-end rounded-lg px-2 text-sm font-medium text-slate-700 dark:text-slate-200">
        <input
          aria-label={t("catalog.in_stock")}
          checked={values.in_stock}
          className="size-5 accent-brand"
          onChange={(event) => onChange({ in_stock: event.target.checked })}
          type="checkbox"
        />
        {t("catalog.in_stock")}
      </label>
      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-slate-600 dark:text-slate-300">
        {t("catalog.sort")}
        <select
          aria-label={t("catalog.sort")}
          className="min-h-11 w-full rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-white"
          onChange={(event) => onChange({ sort: event.target.value as CatalogSort })}
          value={values.sort}
        >
          <option value="default">{t("catalog.sort.default")}</option>
          <option value="price_asc">{t("catalog.sort.price_asc")}</option>
          <option value="price_desc">{t("catalog.sort.price_desc")}</option>
          <option value="newest">{t("catalog.sort.newest")}</option>
        </select>
      </label>
      <button
        className="col-span-2 min-h-11 justify-self-start rounded-lg px-3 text-sm font-semibold text-brand underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand sm:col-span-4"
        onClick={onClear}
        type="button"
      >
        {t("catalog.clear_filters")}
      </button>
    </fieldset>
  );
}
