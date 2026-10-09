import { useCallback, useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQueries } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CatalogQuery, Category, Page, Product } from "@/types/api";

const CATALOG_PAGE_SIZE = 24;

export function normalizeCatalogQuery(query: CatalogQuery): CatalogQuery {
  return {
    q: query.q.trim(),
    category: query.category && query.category > 0 ? query.category : null,
    min_price: normalizeDecimal(query.min_price),
    max_price: normalizeDecimal(query.max_price),
    in_stock: query.in_stock,
    sort: query.sort,
    page: Math.max(1, Math.floor(query.page) || 1),
  };
}

function normalizeDecimal(value: string): string {
  const trimmed = value.trim();
  const match = /^(-?)(\d+)(?:\.(\d*))?$/.exec(trimmed);
  if (!match) return trimmed;

  const sign = match[1] ?? "";
  const whole = (match[2] ?? "0").replace(/^0+(?=\d)/, "");
  const fraction = (match[3] ?? "").replace(/0+$/, "");
  if (whole === "0" && !fraction) return "0";
  return `${sign}${whole}${fraction ? `.${fraction}` : ""}`;
}

export function useCatalog(query: CatalogQuery) {
  const normalized = useMemo(() => normalizeCatalogQuery(query), [
    query.q,
    query.category,
    query.min_price,
    query.max_price,
    query.in_stock,
    query.sort,
    query.page,
  ]);
  // Keep the normalized filters in the cache key; the URL page is the infinite-query cursor.
  const filters = useMemo(() => ({ ...normalized, page: 1 }), [normalized]);

  const catalog = useInfiniteQuery({
    queryKey: ["catalog", filters],
    initialPageParam: 1,
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await api.get<Page<Product>>("/catalog/products", {
        params: {
          ...(filters.q ? { q: filters.q } : {}),
          ...(filters.category ? { category_id: filters.category } : {}),
          ...(filters.min_price ? { min_price: filters.min_price } : {}),
          ...(filters.max_price ? { max_price: filters.max_price } : {}),
          in_stock: filters.in_stock,
          sort: filters.sort,
          page: pageParam,
          limit: CATALOG_PAGE_SIZE,
        },
        signal,
      });
      if (
        !data ||
        !Array.isArray(data.items) ||
        !Number.isFinite(data.page) ||
        !Number.isFinite(data.total_pages)
      ) {
        throw new Error("Catalog response did not match the paginated products contract");
      }
      return data;
    },
    getNextPageParam: (lastPage) =>
      lastPage.page < lastPage.total_pages ? lastPage.page + 1 : undefined,
  });

  useEffect(() => {
    if (
      normalized.page > (catalog.data?.pages.length ?? 0) &&
      catalog.hasNextPage &&
      !catalog.isFetchingNextPage &&
      !catalog.isError
    ) {
      void catalog.fetchNextPage();
    }
  }, [
    normalized.page,
    catalog.data?.pages.length,
    catalog.hasNextPage,
    catalog.isFetchingNextPage,
    catalog.isError,
    catalog.fetchNextPage,
  ]);

  const knownTotalPages = catalog.data?.pages.at(-1)?.total_pages;
  const visiblePageCount = knownTotalPages
    ? Math.min(normalized.page, knownTotalPages)
    : normalized.page;
  const pages = catalog.data?.pages.slice(0, visiblePageCount) ?? [];
  const currentPage = pages.at(-1);
  const hasMore = Boolean(currentPage && visiblePageCount < currentPage.total_pages);
  const products = useMemo(() => {
    const unique = new Map<number, Product>();
    for (const page of pages) {
      for (const product of page.items) {
        if (!unique.has(product.id)) unique.set(product.id, product);
      }
    }
    return [...unique.values()];
  }, [pages]);

  async function loadMore(): Promise<boolean> {
    if (!hasMore || catalog.isFetchingNextPage) return false;
    if ((catalog.data?.pages.length ?? 0) > normalized.page) return true;
    const result = await catalog.fetchNextPage();
    return !result.isError && (result.data?.pages.length ?? 0) > normalized.page;
  }

  return {
    pages,
    products,
    loadMore,
    isLoading: !catalog.isError && (catalog.isLoading || pages.length < visiblePageCount),
    isFetchingNextPage: catalog.isFetchingNextPage,
    isError: catalog.isError,
    error: catalog.error,
    hasMore,
    retry: catalog.refetch,
  };
}

export function useCategoryTree() {
  const [parentIds, setParentIds] = useState<Array<number | null>>([null]);
  const combine = useCallback((results: Array<{
    data: Category[] | undefined;
    isLoading: boolean;
    isError: boolean;
    refetch: () => Promise<unknown>;
  }>) => {
    const categoriesById = new Map<number, Category>();
    for (const result of results) {
      for (const category of result.data ?? []) categoriesById.set(category.id, category);
    }
    return {
      categories: [...categoriesById.values()].sort(
        (left, right) => left.sort_order - right.sort_order || left.id - right.id,
      ),
      isLoading: results.some((result) => result.isLoading) ||
        [...categoriesById.keys()].some((id) => !parentIds.includes(id)),
      isError: results.some((result) => result.isError),
      refetch: () => Promise.all(results.map((result) => result.refetch())),
    };
  }, [parentIds]);

  const categoryTree = useQueries({
    queries: parentIds.map((parentId) => ({
      queryKey: ["categories", parentId],
      queryFn: async ({ signal }) => {
        const { data } = await api.get<Category[]>("/catalog/categories", {
          params: parentId === null ? undefined : { parent_id: parentId },
          signal,
        });
        return data;
      },
    })),
    combine,
  });

  useEffect(() => {
    setParentIds((current) => {
      const next = [null, ...categoryTree.categories.map((category) => category.id)];
      if (next.length === current.length && next.every((id, index) => id === current[index])) {
        return current;
      }
      return next;
    });
  }, [categoryTree.categories]);

  return categoryTree;
}
