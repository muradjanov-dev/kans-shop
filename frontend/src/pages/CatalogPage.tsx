import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { useSearchParams, useLocation } from "react-router-dom";
import { ProductCard } from "@/components/ProductCard";
import { CatalogFilters } from "@/components/storefront/CatalogFilters";
import { CategoryBreadcrumbs } from "@/components/storefront/CategoryBreadcrumbs";
import { CategoryTile } from "@/components/storefront/CategoryTile";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { useCatalog, useCategoryTree } from "@/hooks/useCatalog";
import { useFeaturedProducts, usePublicSettings } from "@/hooks/queries";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import type { CatalogQuery, CatalogSort } from "@/types/api";

const SORT_VALUES = new Set<CatalogSort>(["default", "price_asc", "price_desc", "newest"]);

function readCatalogQuery(params: URLSearchParams): CatalogQuery {
  const rawCategory = params.get("category");
  const categoryValue = rawCategory ? Number(rawCategory) : NaN;
  const rawPage = Number(params.get("page"));
  const sortValue = params.get("sort") as CatalogSort | null;

  return {
    q: params.get("q") ?? "",
    category: Number.isSafeInteger(categoryValue) && categoryValue > 0 ? categoryValue : null,
    min_price: params.get("min_price") ?? "",
    max_price: params.get("max_price") ?? "",
    in_stock: params.get("in_stock") === "true",
    sort: sortValue && SORT_VALUES.has(sortValue) ? sortValue : "default",
    page: Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1,
  };
}

function responseIsRateLimited(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 429;
}

export function CatalogPage() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const serializedParams = searchParams.toString();
  const query = useMemo(
    () => readCatalogQuery(new URLSearchParams(serializedParams)),
    [serializedParams],
  );
  const updateParams = useCallback((patch: Partial<CatalogQuery>, clearAll = false) => {
    setSearchParams((current) => {
      const next = clearAll ? new URLSearchParams() : new URLSearchParams(current);
      const update = (key: string, value: string | null) => {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      };
      if ("q" in patch) update("q", patch.q?.trim() ? patch.q : null);
      if ("category" in patch) update("category", patch.category ? String(patch.category) : null);
      if ("min_price" in patch) update("min_price", patch.min_price?.trim() ?? null);
      if ("max_price" in patch) update("max_price", patch.max_price?.trim() ?? null);
      if ("in_stock" in patch) update("in_stock", patch.in_stock ? "true" : null);
      if ("sort" in patch) update("sort", patch.sort === "default" ? null : patch.sort ?? null);
      if ("page" in patch) update("page", patch.page && patch.page > 1 ? String(patch.page) : "1");
      else if (!clearAll) next.set("page", "1");
      return next;
    }, { replace: true });
  }, [setSearchParams]);
  const [debouncedQuery, setDebouncedQuery] = useState(query.q.trim());
  const restoredCatalogScroll = useRef(false);

  useEffect(() => {
    const nextQuery = query.q.trim();
    if (nextQuery === debouncedQuery) return;
    const timeout = window.setTimeout(() => setDebouncedQuery(nextQuery), 300);
    return () => window.clearTimeout(timeout);
  }, [query.q, debouncedQuery]);

  useEffect(() => {
    const locationState = location.state as { restoreCatalogScrollY?: unknown } | null;
    const restoreCatalogScrollY = locationState?.restoreCatalogScrollY;
    if (
      typeof restoreCatalogScrollY !== "number" ||
      restoreCatalogScrollY <= 0 ||
      restoredCatalogScroll.current
    ) return;
    restoredCatalogScroll.current = true;
    window.requestAnimationFrame(() => window.scrollTo({ top: restoreCatalogScrollY }));
  }, [location.key, location.state]);

  const categoryTree = useCategoryTree();
  const categories = categoryTree.categories;
  const categoriesById = useMemo(
    () => new Map(categories.map((category) => [category.id, category])),
    [categories],
  );
  const selectedCategory = query.category ? categoriesById.get(query.category) : undefined;
  const effectiveCategoryId = query.category;

  useEffect(() => {
    if (!categoryTree.isLoading && query.category && !selectedCategory) {
      updateParams({ category: null });
    }
  }, [categoryTree.isLoading, query.category, selectedCategory, updateParams]);

  const catalog = useCatalog({ ...query, q: debouncedQuery, category: query.category });
  const lastCatalogPage = catalog.pages.at(-1);
  useEffect(() => {
    const lastAvailablePage = lastCatalogPage ? Math.max(1, lastCatalogPage.total_pages) : null;
    if (lastAvailablePage !== null && query.page > lastAvailablePage) {
      updateParams({ page: lastAvailablePage });
    }
  }, [lastCatalogPage, query.page, updateParams]);
  const featuredQuery = useFeaturedProducts();
  const settingsQuery = usePublicSettings();
  const welcomeText = language === "ru"
    ? settingsQuery.data?.welcome_text_ru?.trim()
    : settingsQuery.data?.welcome_text_uz?.trim();
  const childCategories = selectedCategory
    ? categories.filter((category) => category.parent_id === selectedCategory.id)
    : categories.filter((category) => category.parent_id === null);

  function updateFilters(patch: Partial<Pick<CatalogQuery, "min_price" | "max_price" | "in_stock" | "sort">>) {
    updateParams(patch);
  }

  async function loadMore(): Promise<void> {
    if (await catalog.loadMore()) updateParams({ page: query.page + 1 });
  }

  const hasActiveFilters = Boolean(
    query.q.trim() || query.category || query.min_price || query.max_price || query.in_stock || query.sort !== "default",
  );

  return (
    <div className="pb-8">
      <div className="p-4 pb-3">
        <h1 className="mb-3 text-xl font-bold text-slate-900 dark:text-white">
          {t("catalog.title")}
        </h1>
        <input
          aria-label={t("storefront.search")}
          className="min-h-11 w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm shadow-sm focus:border-brand focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500"
          onChange={(event) => updateParams({ q: event.target.value })}
          placeholder={t("common.search")}
          type="search"
          value={query.q}
        />
      </div>

      {welcomeText && (
        <p className="mx-4 mb-5 rounded-2xl bg-violet-50 px-4 py-3 text-sm text-violet-950 dark:bg-violet-400/10 dark:text-violet-100">
          {welcomeText}
        </p>
      )}

      <div className="px-4">
        <CategoryBreadcrumbs
          categories={categories}
          categoryId={effectiveCategoryId}
          onSelect={(categoryId) => updateParams({ category: categoryId })}
        />
        <CatalogFilters
          onChange={updateFilters}
          onClear={() => updateParams({}, true)}
          values={{
            min_price: query.min_price,
            max_price: query.max_price,
            in_stock: query.in_stock,
            sort: query.sort,
          }}
        />
      </div>

      {categoryTree.isError ? (
        <div className="px-4"><ErrorState onRetry={() => void categoryTree.refetch()} /></div>
      ) : childCategories.length > 0 ? (
        <section aria-label={t("catalog.categories")} className="mb-5 px-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {childCategories.map((category) => (
              <CategoryTile
                category={category}
                key={category.id}
                onSelect={(nextCategory) => updateParams({ category: nextCategory.id })}
                selected={category.id === effectiveCategoryId}
              />
            ))}
          </div>
        </section>
      ) : null}

      {featuredQuery.data && featuredQuery.data.length > 0 && (
        <section aria-labelledby="featured-products-heading" className="mb-7 px-4">
          <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white" id="featured-products-heading">
            {t("catalog.featured")}
          </h2>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            {featuredQuery.data.map((product) => <ProductCard key={product.id} product={product} />)}
          </div>
        </section>
      )}

      <section aria-labelledby="all-products-heading" className="px-4">
        <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white" id="all-products-heading">
          {t("catalog.all_products")}
        </h2>
        {catalog.isLoading ? (
          <div className="flex flex-col items-center gap-2 py-10" role="status">
            <Spinner />
            <p className="text-sm text-slate-500">{t("catalog.loading")}</p>
          </div>
        ) : catalog.isError && catalog.products.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-10 text-center" role="alert">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {responseIsRateLimited(catalog.error) ? t("catalog.rate_limited") : t("common.error")}
            </p>
            <button
              className="min-h-11 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              onClick={() => void catalog.retry()}
              type="button"
            >
              {t("common.retry")}
            </button>
          </div>
        ) : catalog.products.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {query.q.trim() ? t("catalog.empty") : t("catalog.no_products")}
            </p>
            {hasActiveFilters && (
              <button
                className="min-h-11 rounded-lg px-3 text-sm font-semibold text-brand underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                onClick={() => updateParams({}, true)}
                type="button"
              >
                {t("catalog.clear_filters")}
              </button>
            )}
          </div>
        ) : (
          <>
            {catalog.isError && (
              <div className="mb-4 flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-center dark:border-red-300/20 dark:bg-red-950/30" role="alert">
                <p className="text-sm text-red-800 dark:text-red-200">
                  {responseIsRateLimited(catalog.error) ? t("catalog.rate_limited") : t("common.error")}
                </p>
                <button
                  className="min-h-11 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                  onClick={() => void catalog.retry()}
                  type="button"
                >
                  {t("common.retry")}
                </button>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              {catalog.products.map((product) => <ProductCard key={product.id} product={product} />)}
            </div>
            {catalog.hasMore && (
              <button
                className="mt-5 min-h-11 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-brand shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-60 dark:border-white/10 dark:bg-slate-900"
                disabled={catalog.isFetchingNextPage}
                onClick={() => void loadMore()}
                type="button"
              >
                {catalog.isFetchingNextPage ? t("catalog.loading_more") : t("catalog.load_more")}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
