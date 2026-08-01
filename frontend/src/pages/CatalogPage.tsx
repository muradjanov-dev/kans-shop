import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCategories, useCategoryProducts, useProductSearch } from "@/hooks/queries";
import { CategoryCard } from "@/components/CategoryCard";
import { ProductCard } from "@/components/ProductCard";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { localizedField } from "@/lib/format";
import type { Product } from "@/types/api";

export function CatalogPage() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const [searchParams] = useSearchParams();
  const categoryId = searchParams.get("category");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const categoriesQuery = useCategories();
  const productsQuery = useCategoryProducts(
    categoryId ? Number(categoryId) : undefined,
    page,
  );
  const searchQuery = useProductSearch(search, page);

  const activeCategory = categoriesQuery.data?.find((c) => c.id === Number(categoryId));
  const isSearching = search.trim().length > 0;

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center gap-2">
        {categoryId && (
          <Link to="/" className="text-sm font-medium text-brand">
            ← {t("common.back")}
          </Link>
        )}
      </div>

      <input
        value={search}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
        placeholder={t("common.search")}
        className="mb-4 w-full rounded-lg border border-gray-200 px-4 py-2.5 text-sm focus:border-brand focus:outline-none"
      />

      {isSearching ? (
        <ProductGrid
          isLoading={searchQuery.isLoading}
          isError={searchQuery.isError}
          onRetry={searchQuery.refetch}
          products={searchQuery.data?.items}
        />
      ) : categoryId ? (
        <>
          {activeCategory && (
            <h1 className="mb-3 text-lg font-semibold text-gray-900">
              {localizedField(language, activeCategory, "name")}
            </h1>
          )}
          <ProductGrid
            isLoading={productsQuery.isLoading}
            isError={productsQuery.isError}
            onRetry={productsQuery.refetch}
            products={productsQuery.data?.items}
            emptyLabel={t("catalog.no_products")}
          />
        </>
      ) : (
        <>
          <h1 className="mb-3 text-lg font-semibold text-gray-900">{t("catalog.title")}</h1>
          {categoriesQuery.isLoading && <Spinner />}
          {categoriesQuery.isError && <ErrorState onRetry={() => categoriesQuery.refetch()} />}
          {categoriesQuery.data && (
            <div className="grid grid-cols-2 gap-3">
              {categoriesQuery.data.map((category) => (
                <CategoryCard key={category.id} category={category} />
              ))}
            </div>
          )}
        </>
      )}
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
    return <p className="py-10 text-center text-sm text-gray-500">{emptyLabel ?? t("common.empty")}</p>;
  }
  return (
    <div className="grid grid-cols-2 gap-3">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
}
