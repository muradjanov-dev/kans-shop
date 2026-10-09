import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useProduct } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { QuantityStepper } from "@/components/QuantityStepper";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { formatPrice, localizedField } from "@/lib/format";
import { useCartActions } from "@/hooks/useCartActions";

export function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const productId = id ? Number(id) : undefined;
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const { add, pending } = useCartActions();
  const location = useLocation();

  const { data: product, isLoading, isError, refetch } = useProduct(productId);
  const [quantity, setQuantity] = useState(1);

  if (isLoading) return <Spinner />;
  if (isError || !product) return <ErrorState onRetry={() => refetch()} />;

  const name = localizedField(language, product, "name");
  const description = localizedField(language, product, "description");
  const image = product.images.find((img) => img.is_main) ?? product.images[0];
  const minimumQuantity = Math.max(1, product.min_order_qty);
  const maximumQuantity = product.stock_qty;
  const boundedQuantity = Math.min(maximumQuantity, Math.max(minimumQuantity, quantity));
  const outOfStock = maximumQuantity < minimumQuantity;

  return (
    <div className="pb-24">
      <Link to="/" className="ml-4 mt-4 mb-3 inline-flex rounded-full bg-white/90 px-3 py-1 text-sm font-medium text-brand shadow dark:bg-black/60">
        ← {t("common.back")}
      </Link>
      <div className="flex aspect-square items-center justify-center bg-gray-50 dark:bg-white/5">
        {image?.url ? (
          <img src={image.url} alt={name} className="size-full object-cover" />
        ) : (
          <span className="text-6xl">📦</span>
        )}
      </div>
      <div className="flex flex-col gap-3 p-4">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-white">{name}</h1>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatPrice(product.price)}
          </span>
          <span className="text-sm text-gray-500 dark:text-gray-400">{t("common.som")}</span>
          {product.old_price && (
            <span className="text-sm text-gray-400 line-through">
              {formatPrice(product.old_price)}
            </span>
          )}
        </div>
        {product.min_order_qty > 1 && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t("product.min_order", { qty: product.min_order_qty })}
          </p>
        )}
        {description && (
          <p className="text-sm text-gray-600 dark:text-gray-300">{description}</p>
        )}
        <p className="text-xs text-gray-400">
          {t("product.sku")}: {product.sku}
        </p>
        {outOfStock && (
          <p className="text-sm font-medium text-red-500">{t("product.out_of_stock")}</p>
        )}
      </div>

      {!outOfStock && (
        <div className="fixed bottom-0 left-0 right-0 z-40 mx-auto flex w-full max-w-md items-center gap-3 border-t border-gray-200 bg-white p-4 pb-safe dark:border-white/10 dark:bg-[#131b2c]">
          <QuantityStepper
            quantity={boundedQuantity}
            min={minimumQuantity}
            max={maximumQuantity}
            onChange={(nextQuantity) => {
              setQuantity(Math.min(maximumQuantity, Math.max(minimumQuantity, nextQuantity)));
            }}
          />
          <button
            disabled={pending}
            onClick={() => {
              add(product.id, boundedQuantity, `${location.pathname}${location.search}`);
            }}
            className="flex-1 rounded-lg bg-brand py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {t("product.add_to_cart")}
          </button>
        </div>
      )}
    </div>
  );
}
