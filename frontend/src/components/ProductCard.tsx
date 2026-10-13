import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useLanguageStore } from "@/store/language";
import { formatExactPrice, localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import { hasHigherOldPrice, productUnitTranslationKey } from "@/lib/productDisplay";
import { useCartActions } from "@/hooks/useCartActions";
import { FavoriteButton } from "@/components/storefront/FavoriteButton";
import type { Product } from "@/types/api";

export function ProductCard({ product }: { product: Product }) {
  const language = useLanguageStore((state) => state.language);
  const t = useTranslate();
  const { add, pending } = useCartActions();
  const location = useLocation();
  const [imageFailed, setImageFailed] = useState(false);
  const name = localizedField(language, product, "name");
  const image = product.images.find((candidate) => candidate.is_main && candidate.url?.trim())
    ?? product.images.find((candidate) => candidate.url?.trim());
  const outOfStock = product.stock_qty < Math.max(1, product.min_order_qty);
  const catalogReturnTo = `${location.pathname}${location.search}`;
  const detailState = { catalogReturnTo, catalogScrollY: window.scrollY };
  const rememberCatalogScroll = () =>
    sessionStorage.setItem("storefront-catalog-scroll-y", String(window.scrollY));

  useEffect(() => setImageFailed(false), [image?.id, image?.url]);

  return (
    <article className="product-card group flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-2.5 sm:p-3 dark:border-white/10 dark:bg-slate-900">
      <div className="product-card-image relative aspect-square overflow-hidden rounded-xl bg-[#EDF1E7] dark:bg-slate-800">
        <Link
          className="flex size-full items-center justify-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          onClick={rememberCatalogScroll}
          state={detailState}
          to={`/product/${product.id}`}
        >
          {image?.url && !imageFailed ? (
            <img
              alt={name}
              className="size-full object-contain"
              loading="lazy"
              onError={() => setImageFailed(true)}
              src={image.url.trim()}
            />
          ) : (
            <span
              aria-label={t("product.image_unavailable")}
              className="flex size-full items-center justify-center bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
              role="img"
            >
              <svg aria-hidden="true" viewBox="0 0 160 160" className="size-28" fill="none">
                <rect x="40" y="24" width="76" height="108" rx="9" fill="#D6E2D8" />
                <rect x="48" y="24" width="68" height="108" rx="7" fill="#FAFCF8" stroke="#A9BCAA" />
                <path d="M62 53h39M62 68h39M62 83h25" stroke="#A9BCAA" strokeWidth="3" strokeLinecap="round" />
                <path d="m105 103 26-58 8 4-26 58-9 10z" fill="#EE7938" />
              </svg>
            </span>
          )}
          {product.is_featured && (
            <span className="absolute left-2 top-2 rounded-md bg-white px-2 py-1 text-[11px] font-semibold text-[#153F32] dark:bg-slate-900 dark:text-white">
              {t("product.featured")}
            </span>
          )}
        </Link>
        <FavoriteButton
          className="absolute right-2 top-2 z-10"
          productId={product.id}
          productName={name}
        />
        {!outOfStock && (
          <button
            aria-label={t("product.add_to_cart")}
            className="product-card-add absolute bottom-2 right-2 flex min-h-11 min-w-11 items-center justify-center rounded-xl bg-brand text-lg font-bold text-white shadow-md transition-transform active:scale-95 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
            disabled={pending}
            onClick={() => add(product.id, Math.max(1, product.min_order_qty), catalogReturnTo)}
            type="button"
          >
            {pending ? "…" : "+"}
          </button>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1.5 px-1 pb-1 pt-3">
        <Link
          className="flex flex-1 flex-col gap-1.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          onClick={rememberCatalogScroll}
          state={detailState}
          to={`/product/${product.id}`}
        >
          <p className="line-clamp-2 min-h-10 text-sm font-semibold text-slate-900 dark:text-slate-100">
            {name}
          </p>
          <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
            <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
              {formatExactPrice(product.price)}
            </span>
            <span className="text-xs text-slate-500 dark:text-slate-400">{t("common.som")}</span>
            {hasHigherOldPrice(product.old_price, product.price) && (
              <span className="text-xs text-slate-400 line-through">{formatExactPrice(product.old_price!)}</span>
            )}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t("product.stock", {
              qty: product.stock_qty,
              unit: t(productUnitTranslationKey[product.unit]),
            })}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">{t("product.sku")}: {product.sku}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {t("product.min_order", { qty: product.min_order_qty })}
          </p>
        </Link>
        {outOfStock && (
          <span className="text-xs font-medium text-red-600 dark:text-red-300">{t("product.out_of_stock")}</span>
        )}
      </div>
    </article>
  );
}
