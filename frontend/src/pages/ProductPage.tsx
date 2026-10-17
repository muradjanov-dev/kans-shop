import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ErrorState } from "@/components/ErrorState";
import { QuantityStepper } from "@/components/QuantityStepper";
import { ProductGallery } from "@/components/storefront/ProductGallery";
import { FavoriteButton } from "@/components/storefront/FavoriteButton";
import { useProduct } from "@/hooks/queries";
import { useCartActions } from "@/hooks/useCartActions";
import { formatExactPrice, localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import {
  hasHigherOldPrice,
  productUnitTranslationKey,
} from "@/lib/productDisplay";
import { useLanguageStore } from "@/store/language";

function savedCatalogUrl(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/product/")
  )
    return "/";
  return value;
}

export function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const productId = id ? Number(id) : undefined;
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const { add, pending } = useCartActions();
  const location = useLocation();
  const { data: product, isLoading, isError, refetch } = useProduct(productId);
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (product) setQuantity(Math.max(1, product.min_order_qty));
  }, [productId, product?.min_order_qty]);

  if (isLoading)
    return (
      <div role="status">
        <SpinnerText />
      </div>
    );
  if (isError || !product) return <ErrorState onRetry={() => void refetch()} />;

  const locationState = location.state as {
    catalogReturnTo?: unknown;
    catalogScrollY?: unknown;
  } | null;
  const returnTo = savedCatalogUrl(locationState?.catalogReturnTo);
  const storedScrollY = Number(
    sessionStorage.getItem("storefront-catalog-scroll-y"),
  );
  const hasSavedCatalogLocation =
    typeof locationState?.catalogReturnTo === "string";
  const stateScrollY =
    typeof locationState?.catalogScrollY === "number"
      ? locationState.catalogScrollY
      : 0;
  const scrollY = hasSavedCatalogLocation
    ? Number.isFinite(storedScrollY)
      ? storedScrollY
      : stateScrollY
    : 0;
  const name = localizedField(language, product, "name");
  const description = localizedField(language, product, "description");
  const minimumQuantity = Math.max(1, product.min_order_qty);
  const stockTracked = product.stock_tracking_enabled !== false;
  const maximumQuantity = stockTracked ? Math.max(0, product.stock_qty ?? 0) : undefined;
  const boundedQuantity = maximumQuantity === undefined
    ? Math.max(minimumQuantity, quantity)
    : Math.min(maximumQuantity, Math.max(minimumQuantity, quantity));
  const outOfStock = maximumQuantity !== undefined && maximumQuantity < minimumQuantity;

  return (
    <div className="product-page page-shell page-shell-wide">
      <Link
        className="product-back mb-6 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:text-white"
        state={{ restoreCatalogScrollY: scrollY }}
        to={returnTo}
      >
        ← {t("common.back")}
      </Link>
      <div className="product-detail-grid grid gap-7 md:grid-cols-2 md:items-start md:gap-12">
        <div className="product-detail-gallery overflow-hidden rounded-3xl border border-[var(--line)] bg-[var(--soft)] p-3 sm:p-5 dark:bg-slate-800 dark:border-white/10">
          <ProductGallery images={product.images} name={name} />
        </div>
        <div className="product-detail-info flex flex-col gap-5 md:py-4">
          {product.is_featured && (
            <span className="w-fit rounded-full bg-[var(--orange)]/15 px-3 py-1.5 text-xs font-semibold text-[#93451E]">
              {t("product.featured")}
            </span>
          )}
          <div className="flex items-start justify-between gap-3">
            <h1 className="page-title dark:text-white">{name}</h1>
            <FavoriteButton productId={product.id} productName={name} />
          </div>
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-brand dark:text-white">
              {formatExactPrice(product.price)}
            </span>
            <span className="text-sm text-[var(--muted)] dark:text-gray-400">
              {t("common.som")}
            </span>
            {hasHigherOldPrice(product.old_price, product.price) && (
              <span className="text-sm text-slate-400 line-through">
                {formatExactPrice(product.old_price!)}
              </span>
            )}
          </div>
          {stockTracked && (
            <p className="text-sm text-[var(--muted)] dark:text-gray-400">
              {t("product.stock", {
                qty: product.stock_qty ?? 0,
                unit: t(productUnitTranslationKey[product.unit]),
              })}
            </p>
          )}
          <p className="text-sm text-[var(--muted)] dark:text-gray-400">
            {t("product.sku")}: {product.sku}
          </p>
          <p className="text-sm text-[var(--muted)] dark:text-gray-400">
            {t("product.min_order", { qty: product.min_order_qty })}
          </p>
          {description && (
            <p className="whitespace-pre-line text-sm leading-6 text-[var(--muted)] dark:text-gray-400">
              {description}
            </p>
          )}
          {outOfStock && (
            <p className="text-sm font-medium text-red-600" role="status">
              {t("product.out_of_stock")}
            </p>
          )}
          {!outOfStock && (
            <div className="product-purchase mt-3 flex w-full flex-wrap items-center gap-3 border-t border-[var(--line)] pt-6 dark:border-white/10">
              <QuantityStepper
                disabled={pending}
                max={maximumQuantity}
                min={minimumQuantity}
                onChange={(nextQuantity) => {
                  const bounded = Math.max(minimumQuantity, nextQuantity);
                  setQuantity(maximumQuantity === undefined
                    ? bounded
                    : Math.min(maximumQuantity, bounded));
                }}
                quantity={boundedQuantity}
              />
              <button
                aria-busy={pending}
                className="primary-button min-w-40 flex-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-wait disabled:opacity-60"
                disabled={pending}
                onClick={() =>
                  add(
                    product.id,
                    boundedQuantity,
                    `${location.pathname}${location.search}`,
                  )
                }
                type="button"
              >
                {pending
                  ? t("product.adding_to_cart")
                  : t("product.add_to_cart")}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SpinnerText() {
  const t = useTranslate();
  return (
    <p className="py-10 text-center text-sm text-[var(--muted)] dark:text-gray-400">
      {t("common.loading")}
    </p>
  );
}
