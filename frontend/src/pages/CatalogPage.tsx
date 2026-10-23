import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useLocation } from "react-router-dom";
import { ProductCard } from "@/components/ProductCard";
import { CatalogFilters } from "@/components/storefront/CatalogFilters";
import { CategoryBreadcrumbs } from "@/components/storefront/CategoryBreadcrumbs";
import { CategoryTile } from "@/components/storefront/CategoryTile";
import { ErrorState } from "@/components/ErrorState";
import { HeroCarousel } from "@/components/storefront/HeroCarousel";
import { useCatalog, useCategoryTree } from "@/hooks/useCatalog";
import { useFeaturedProducts, usePublicSettings } from "@/hooks/queries";
import { track } from "@/lib/analytics";
import { isRateLimitedError } from "@/lib/api";
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
  // setSearchParams hands its updater the params of the last render, not the last update, so
  // two quick changes (min price, then max price) could drop the first one. Each update builds
  // on the newest params instead. The router commits navigations in a transition, so an
  // older update can still commit after a newer one was issued: until our last update has
  // landed, those in-between commits are ignored. Changes from elsewhere (back button, a
  // link) are adopted as soon as nothing of ours is pending.
  const latestParams = useRef(searchParams);
  const pendingParams = useRef<{ value: string; at: number } | null>(null);
  useLayoutEffect(() => {
    const pending = pendingParams.current;
    if (pending && serializedParams !== pending.value && Date.now() - pending.at < 2000) return;
    pendingParams.current = null;
    latestParams.current = searchParams;
  }, [searchParams, serializedParams]);
  const updateParams = useCallback((patch: Partial<CatalogQuery>, clearAll = false) => {
    const next = clearAll ? new URLSearchParams() : new URLSearchParams(latestParams.current);
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
    latestParams.current = next;
    pendingParams.current = { value: next.toString(), at: Date.now() };
    setSearchParams(next, { replace: true });
  }, [setSearchParams]);
  const [debouncedQuery, setDebouncedQuery] = useState(query.q.trim());
  const [filtersOpen, setFiltersOpen] = useState(() =>
    Boolean(query.min_price || query.max_price || query.in_stock || query.sort !== "default"),
  );
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

  const settingsQuery = usePublicSettings();
  const stockTrackingEnabled = settingsQuery.data?.stock_tracking_enabled !== false;
  const catalogQuery = {
    ...query,
    q: debouncedQuery,
    category: query.category,
    in_stock: stockTrackingEnabled && query.in_stock,
  };
  const catalog = useCatalog(catalogQuery);
  const lastCatalogPage = catalog.pages.at(-1);
  // Each finished search is counted once, with how many products it found (0 = a gap).
  const searchTotal = catalog.isLoading ? undefined : catalog.pages[0]?.total;
  const trackedSearch = useRef<string | null>(null);
  useEffect(() => {
    if (!debouncedQuery || searchTotal === undefined) return;
    if (trackedSearch.current === debouncedQuery) return;
    trackedSearch.current = debouncedQuery;
    track({ type: "search", label: debouncedQuery, value: searchTotal });
  }, [debouncedQuery, searchTotal]);
  useEffect(() => {
    const lastAvailablePage = lastCatalogPage ? Math.max(1, lastCatalogPage.total_pages) : null;
    if (lastAvailablePage !== null && query.page > lastAvailablePage) {
      updateParams({ page: lastAvailablePage });
    }
  }, [lastCatalogPage, query.page, updateParams]);
  const featuredQuery = useFeaturedProducts();
  const welcomeText = language === "ru"
    ? settingsQuery.data?.welcome_text_ru?.trim()
    : settingsQuery.data?.welcome_text_uz?.trim();
  const childCategories = selectedCategory
    ? categories.filter((category) => category.parent_id === selectedCategory.id)
    : categories.filter((category) => category.parent_id === null);

  function updateFilters(patch: Partial<Pick<CatalogQuery, "min_price" | "max_price" | "in_stock" | "sort">>) {
    updateParams(patch);
    for (const [key, value] of Object.entries(patch)) {
      track({ type: "filter", target: key, label: String(value ?? "") });
    }
  }

  function selectCategory(categoryId: number | null) {
    updateParams({ category: categoryId });
    const name = categoryId ? categoriesById.get(categoryId)?.name_uz : "all";
    track({ type: "filter", target: "category", label: name ?? String(categoryId) });
  }

  async function loadMore(): Promise<void> {
    if (await catalog.loadMore()) updateParams({ page: query.page + 1 });
  }

  const activeFilterCount = [
    query.min_price,
    query.max_price,
    stockTrackingEnabled && query.in_stock,
    query.sort !== "default",
  ].filter(Boolean).length;

  const hasActiveFilters = Boolean(
    query.q.trim() || query.category || query.min_price || query.max_price || (stockTrackingEnabled && query.in_stock) || query.sort !== "default",
  );

  return (
    <div className="catalog-page space-y-7 pb-8">
      <h1 className="sr-only">{t("hero.page_title")}</h1>
      <HeroCarousel />
      <div id="catalog" className="catalog-toolbar scroll-mt-24 flex flex-col justify-between gap-4 sm:flex-row sm:items-end" data-track-section="search">
        <div><h2 className="catalog-section-title text-2xl font-bold tracking-tight text-slate-900 dark:text-white">{t("catalog.title")}</h2><p className="mt-1 text-sm text-slate-500">{language === "ru" ? "Найдите то, что нужно каждый день." : "Har kuni kerak bo‘ladigan buyumlarni toping."}</p></div>
        <div className="relative w-full sm:max-w-80">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="pointer-events-none absolute left-4 top-3.5 size-5 text-slate-500" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4 4"/></svg>
        <input
          aria-label={t("storefront.search")}
          className="min-h-11 w-full rounded-xl border border-slate-200 bg-white pl-12 pr-4 py-3 text-sm focus:border-brand focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500"
          onChange={(event) => updateParams({ q: event.target.value })}
          placeholder={t("common.search")}
          type="search"
          value={query.q}
        />
        </div>
      </div>

      {welcomeText && (
        <p className="catalog-welcome rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 dark:border-white/10 dark:bg-slate-900 dark:text-slate-100">
          {welcomeText}
        </p>
      )}

      {categoryTree.isError ? (
        <div className="px-4">
          <ErrorState
            message={isRateLimitedError(categoryTree.error) ? t("catalog.rate_limited") : undefined}
            onRetry={() => void categoryTree.refetch()}
          />
        </div>
      ) : childCategories.length > 0 ? (
        <section aria-label={t("catalog.categories")} className="catalog-categories mb-5" data-track-section="categories">
          <div className="category-rail grid grid-cols-1 gap-3 min-[380px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
            {childCategories.map((category) => (
              <CategoryTile
                category={category}
                key={category.id}
                onSelect={(nextCategory) => selectCategory(nextCategory.id)}
                selected={category.id === effectiveCategoryId}
              />
            ))}
          </div>
        </section>
      ) : null}


      <div className="catalog-controls" data-track-section="filters">
        <CategoryBreadcrumbs
          categories={categories}
          categoryId={effectiveCategoryId}
          onSelect={(categoryId) => selectCategory(categoryId)}
        />
        {/* On phones the filters fold behind one button so products start higher up. */}
        <button
          aria-controls="catalog-filters-panel"
          aria-expanded={filtersOpen}
          className="catalog-filters-toggle secondary-button"
          onClick={() => setFiltersOpen((open) => !open)}
          type="button"
        >
          <svg aria-hidden="true" className="size-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2" viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
          {t("catalog.filters_toggle")}
          {activeFilterCount > 0 && <span className="catalog-filters-count">{activeFilterCount}</span>}
        </button>
        <div className={`catalog-filters-panel${filtersOpen ? " is-open" : ""}`} id="catalog-filters-panel">
          <CatalogFilters
            onChange={updateFilters}
            onClear={() => updateParams({}, true)}
            showStockFilter={stockTrackingEnabled}
            values={{
              min_price: query.min_price,
              max_price: query.max_price,
              in_stock: catalogQuery.in_stock,
              sort: query.sort,
            }}
          />
        </div>
      </div>


      {featuredQuery.data && featuredQuery.data.length > 0 && (
        <section aria-labelledby="featured-products-heading" className="catalog-featured mb-7" data-track-section="featured">
          <h2 className="catalog-section-title mb-3 text-lg font-semibold text-slate-900 dark:text-white" id="featured-products-heading">
            {t("catalog.featured")}
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 sm:gap-4">
            {featuredQuery.data.map((product) => <ProductCard key={product.id} product={product} />)}
          </div>
        </section>
      )}

      <section aria-labelledby="all-products-heading" className="catalog-products" data-track-section="products">
        <h2 className="catalog-section-title mb-3 text-lg font-semibold text-slate-900 dark:text-white" id="all-products-heading">
          {t("catalog.all_products")}
        </h2>
        {catalog.isLoading ? (
          <div className="catalog-skeleton-grid grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 sm:gap-4" role="status">
            <span className="sr-only">{t("catalog.loading")}</span>
            {Array.from({ length: 8 }, (_, position) => (
              <div aria-hidden="true" className="product-card-skeleton" key={position}>
                <span className="product-card-skeleton-image" />
                <span className="product-card-skeleton-line" />
                <span className="product-card-skeleton-line is-short" />
              </div>
            ))}
          </div>
        ) : catalog.isError && catalog.products.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-10 text-center" role="alert">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {isRateLimitedError(catalog.error) ? t("catalog.rate_limited") : t("common.error")}
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
                  {isRateLimitedError(catalog.error) ? t("catalog.rate_limited") : t("common.error")}
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
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 sm:gap-4">
              {catalog.products.map((product) => <ProductCard key={product.id} product={product} />)}
            </div>
            {catalog.hasMore && (
              <button
                className="catalog-load-more mt-5 min-h-11 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-brand shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-60 dark:border-white/10 dark:bg-slate-900"
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
