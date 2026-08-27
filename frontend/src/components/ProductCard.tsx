import { useState } from "react";
import { Link } from "react-router-dom";
import { useLanguageStore } from "@/store/language";
import { formatPrice, localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import { useAddCartItem } from "@/hooks/queries";
import { useAuthStore } from "@/store/auth";
import type { Product } from "@/types/api";

export function ProductCard({ product }: { product: Product }) {
  const language = useLanguageStore((state) => state.language);
  const t = useTranslate();
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const addCartItem = useAddCartItem();
  const [justAdded, setJustAdded] = useState(false);
  const name = localizedField(language, product, "name");
  const image = product.images.find((img) => img.is_main) ?? product.images[0];
  const outOfStock = product.stock_qty <= 0;

  return (
    <Link
      to={`/product/${product.id}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.04)] transition-all hover:-translate-y-1 hover:shadow-xl hover:shadow-brand/20 dark:border-white/10 dark:bg-[#131b2c]/60 dark:backdrop-blur-xl dark:hover:border-brand/40 dark:hover:shadow-[0_0_30px_rgba(99,102,241,0.2)]"
    >
      <div className="relative flex aspect-square items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 dark:from-brand/10 dark:to-transparent">
        {image?.url ? (
          <img src={image.url} alt={name} className="size-full object-cover" />
        ) : (
          <span className="text-3xl">📦</span>
        )}
        {!outOfStock && (
          <button
            type="button"
            disabled={!isAuthenticated || addCartItem.isPending}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              addCartItem.mutate(
                { productId: product.id, quantity: product.min_order_qty || 1 },
                {
                  onSuccess: () => {
                    setJustAdded(true);
                    setTimeout(() => setJustAdded(false), 1200);
                  },
                },
              );
            }}
            className="absolute bottom-2 right-2 flex size-9 items-center justify-center rounded-full bg-brand text-lg font-bold text-white shadow-md transition-transform active:scale-90 disabled:opacity-50"
          >
            {justAdded ? "✓" : "+"}
          </button>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <p className="line-clamp-2 text-sm font-medium text-gray-900 dark:text-gray-100">
          {name}
        </p>
        <div className="mt-auto flex items-baseline gap-1">
          <span className="text-base font-semibold text-gray-900 dark:text-white">
            {formatPrice(product.price)}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">{t("common.som")}</span>
        </div>
        {outOfStock && (
          <span className="text-xs font-medium text-red-500">{t("product.out_of_stock")}</span>
        )}
      </div>
    </Link>
  );
}
