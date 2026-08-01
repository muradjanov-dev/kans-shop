import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useProduct, useAddCartItem } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { QuantityStepper } from "@/components/QuantityStepper";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { formatPrice, localizedField } from "@/lib/format";
import { useAuthStore } from "@/store/auth";

export function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const productId = id ? Number(id) : undefined;
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const navigate = useNavigate();

  const { data: product, isLoading, isError, refetch } = useProduct(productId);
  const addCartItem = useAddCartItem();
  const [quantity, setQuantity] = useState(1);

  if (isLoading) return <Spinner />;
  if (isError || !product) return <ErrorState onRetry={() => refetch()} />;

  const name = localizedField(language, product, "name");
  const description = localizedField(language, product, "description");
  const image = product.images.find((img) => img.is_main) ?? product.images[0];
  const outOfStock = product.stock_qty <= 0;

  return (
    <div className="pb-24">
      <Link to="/" className="absolute left-4 top-4 z-10 rounded-full bg-white/90 px-3 py-1 text-sm font-medium text-brand shadow">
        ← {t("common.back")}
      </Link>
      <div className="flex aspect-square items-center justify-center bg-gray-50">
        {image?.url ? (
          <img src={image.url} alt={name} className="size-full object-cover" />
        ) : (
          <span className="text-6xl">📦</span>
        )}
      </div>
      <div className="flex flex-col gap-3 p-4">
        <h1 className="text-lg font-semibold text-gray-900">{name}</h1>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-gray-900">{formatPrice(product.price)}</span>
          <span className="text-sm text-gray-500">{t("common.som")}</span>
          {product.old_price && (
            <span className="text-sm text-gray-400 line-through">
              {formatPrice(product.old_price)}
            </span>
          )}
        </div>
        {product.min_order_qty > 1 && (
          <p className="text-xs text-gray-500">
            {t("product.min_order", { qty: product.min_order_qty })}
          </p>
        )}
        {description && <p className="text-sm text-gray-600">{description}</p>}
        <p className="text-xs text-gray-400">
          {t("product.sku")}: {product.sku}
        </p>
        {outOfStock && (
          <p className="text-sm font-medium text-red-500">{t("product.out_of_stock")}</p>
        )}
      </div>

      {!outOfStock && (
        <div className="fixed bottom-16 mx-auto flex w-full max-w-lg items-center gap-3 border-t border-gray-200 bg-white p-4">
          <QuantityStepper
            quantity={quantity}
            min={product.min_order_qty}
            onChange={setQuantity}
          />
          <button
            disabled={!isAuthenticated || addCartItem.isPending}
            onClick={() => {
              addCartItem.mutate(
                { productId: product.id, quantity },
                { onSuccess: () => navigate("/cart") },
              );
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
