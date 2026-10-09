import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ErrorState } from "@/components/ErrorState";
import { QuantityStepper } from "@/components/QuantityStepper";
import { ProductGallery } from "@/components/storefront/ProductGallery";
import { useProduct } from "@/hooks/queries";
import { useCartActions } from "@/hooks/useCartActions";
import { formatExactPrice, localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import type { ProductUnit } from "@/types/api";

const unitTranslationKey: Record<ProductUnit, "product.unit.dona" | "product.unit.quti" | "product.unit.paket" | "product.unit.komplekt"> = {
  dona: "product.unit.dona",
  quti: "product.unit.quti",
  paket: "product.unit.paket",
  komplekt: "product.unit.komplekt",
};

function hasHigherOldPrice(oldPrice: string | null, price: string): boolean {
  if (!oldPrice) return false;
  const parse = (value: string): { whole: string; fraction: string } | null => {
    const match = /^(\d+)(?:\.(\d+))?$/.exec(value.trim());
    if (!match) return null;
    return {
      whole: (match[1] ?? "0").replace(/^0+(?=\d)/, ""),
      fraction: match[2] ?? "",
    };
  };
  const current = parse(price);
  const previous = parse(oldPrice);
  if (!current || !previous) return false;
  const scale = Math.max(current.fraction.length, previous.fraction.length);
  const currentValue = BigInt(`${current.whole}${current.fraction.padEnd(scale, "0")}`);
  const previousValue = BigInt(`${previous.whole}${previous.fraction.padEnd(scale, "0")}`);
  return previousValue > currentValue;
}

function savedCatalogUrl(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/product/")
  ) return "/";
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

  if (isLoading) return <div role="status"><SpinnerText /></div>;
  if (isError || !product) return <ErrorState onRetry={() => void refetch()} />;

  const locationState = location.state as {
    catalogReturnTo?: unknown;
    catalogScrollY?: unknown;
  } | null;
  const returnTo = savedCatalogUrl(locationState?.catalogReturnTo);
  const storedScrollY = Number(sessionStorage.getItem("storefront-catalog-scroll-y"));
  const hasSavedCatalogLocation = typeof locationState?.catalogReturnTo === "string";
  const stateScrollY = typeof locationState?.catalogScrollY === "number"
    ? locationState.catalogScrollY
    : 0;
  const scrollY = hasSavedCatalogLocation
    ? Number.isFinite(storedScrollY) ? storedScrollY : stateScrollY
    : 0;
  const name = localizedField(language, product, "name");
  const description = localizedField(language, product, "description");
  const minimumQuantity = Math.max(1, product.min_order_qty);
  const maximumQuantity = Math.max(0, product.stock_qty);
  const boundedQuantity = Math.min(maximumQuantity, Math.max(minimumQuantity, quantity));
  const outOfStock = maximumQuantity < minimumQuantity;

  return (
    <div className="pb-24 md:pb-8">
      <Link
        className="mb-3 ml-4 mt-4 inline-flex min-h-11 items-center rounded-full bg-white/90 px-3 text-sm font-medium text-brand shadow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:bg-slate-900"
        state={{ restoreCatalogScrollY: scrollY }}
        to={returnTo}
      >
        ← {t("common.back")}
      </Link>
      <div className="grid gap-5 md:grid-cols-2 md:items-start md:gap-8">
        <div className="px-4 md:px-0">
          <ProductGallery images={product.images} name={name} />
        </div>
        <div className="flex flex-col gap-3 px-4 md:px-0">
          {product.is_featured && (
            <span className="w-fit rounded-full bg-violet-100 px-3 py-1 text-xs font-semibold text-violet-900 dark:bg-violet-400/20 dark:text-violet-100">
              {t("product.featured")}
            </span>
          )}
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{name}</h1>
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-2xl font-bold text-slate-900 dark:text-white">
              {formatExactPrice(product.price)}
            </span>
            <span className="text-sm text-slate-500 dark:text-slate-400">{t("common.som")}</span>
            {hasHigherOldPrice(product.old_price, product.price) && (
              <span className="text-sm text-slate-400 line-through">
                {formatExactPrice(product.old_price!)}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t("product.stock", {
              qty: product.stock_qty,
              unit: t(unitTranslationKey[product.unit]),
            })}
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t("product.sku")}: {product.sku}
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t("product.min_order", { qty: product.min_order_qty })}
          </p>
          {description && (
            <p className="whitespace-pre-line text-sm leading-6 text-slate-600 dark:text-slate-300">
              {description}
            </p>
          )}
          {outOfStock && (
            <p className="text-sm font-medium text-red-600 dark:text-red-300" role="status">
              {t("product.out_of_stock")}
            </p>
          )}
          {!outOfStock && (
            <div className="fixed bottom-0 left-0 right-0 z-40 mx-auto flex w-full max-w-md items-center gap-3 border-t border-slate-200 bg-white p-4 pb-safe dark:border-white/10 dark:bg-slate-950 md:static md:mt-4 md:max-w-none md:border-0 md:bg-transparent md:p-0 md:dark:bg-transparent">
              <QuantityStepper
                disabled={pending}
                max={maximumQuantity}
                min={minimumQuantity}
                onChange={(nextQuantity) => {
                  setQuantity(Math.min(maximumQuantity, Math.max(minimumQuantity, nextQuantity)));
                }}
                quantity={boundedQuantity}
              />
              <button
                aria-busy={pending}
                className="min-h-11 flex-1 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-wait disabled:opacity-60"
                disabled={pending}
                onClick={() => add(product.id, boundedQuantity, `${location.pathname}${location.search}`)}
                type="button"
              >
                {pending ? t("product.adding_to_cart") : t("product.add_to_cart")}
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
  return <p className="py-10 text-center text-sm text-slate-500">{t("common.loading")}</p>;
}
