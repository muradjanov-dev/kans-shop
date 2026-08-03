import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useCategories, useCategoryProducts, useProductSearch } from "@/hooks/queries";
import { ProductCard } from "@/components/ProductCard";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { localizedField } from "@/lib/format";
import type { Category, Product } from "@/types/api";

export function CatalogPage() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const [searchParams, setSearchParams] = useSearchParams();
  const categoryParam = searchParams.get("category");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const categoriesQuery = useCategories();
  const categories = categoriesQuery.data ?? [];
  const activeCategoryId = categoryParam ? Number(categoryParam) : categories[0]?.id;

  const productsQuery = useCategoryProducts(activeCategoryId, page);
  const searchQuery = useProductSearch(search, page);
  const isSearching = search.trim().length > 0;

  function selectCategory(category: Category) {
    setPage(1);
    setSearchParams(category.id === categories[0]?.id ? {} : { category: String(category.id) });
  }

  return (
    <div className="pb-2">
      <div className="p-4 pb-3">
        <h1 className="mb-3 text-xl font-bold text-gray-900 dark:text-white">
          {t("catalog.title")}
        </h1>
        <input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder={t("common.search")}
          className="w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm shadow-sm focus:border-brand focus:outline-none dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-gray-500"
        />
      </div>

      {!isSearching && (
        <>
          {categoriesQuery.isError && (
            <div className="px-4">
              <ErrorState onRetry={() => categoriesQuery.refetch()} />
            </div>
          )}
          {categories.length > 0 && (
            <div className="flex gap-2 overflow-x-auto px-4 pb-4 [scrollbar-width:none]">
              {categories.map((category) => {
                const isActive = category.id === activeCategoryId;
                return (
                  <button
                    key={category.id}
                    type="button"
                    onClick={() => selectCategory(category)}
                    className={`flex shrink-0 items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
                      isActive
                        ? "bg-brand text-white shadow-md shadow-brand/30"
                        : "bg-white text-gray-600 shadow-sm dark:bg-white/5 dark:text-gray-300"
                    }`}
                  >
                    <span>🗂️</span>
                    {localizedField(language, category, "name")}
                  </button>
                );
              })}
            </div>
          )}
        </>
      )}

      <div className="px-4">
        {isSearching ? (
          <ProductGrid
            isLoading={searchQuery.isLoading}
            isError={searchQuery.isError}
            onRetry={searchQuery.refetch}
            products={searchQuery.data?.items}
          />
        ) : (
          <ProductGrid
            isLoading={categoriesQuery.isLoading || productsQuery.isLoading}
            isError={productsQuery.isError}
            onRetry={productsQuery.refetch}
            products={productsQuery.data?.items}
            emptyLabel={
              categories.length === 0 ? t("common.empty") : t("catalog.no_products")
            }
          />
        )}
      </div>
    </div>
  );
}

function ProductGrid({
  isLoading,
  isError,
  onRetry,
  products,
  emptyLabel,
}: {
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  products?: Product[];
  emptyLabel?: string;
}) {
  const t = useTranslate();
  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState onRetry={onRetry} />;
  if (!products || products.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-gray-500 dark:text-gray-400">
        {emptyLabel ?? t("common.empty")}
      </p>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}
