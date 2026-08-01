import { Link } from "react-router-dom";
import { useLanguageStore } from "@/store/language";
import { formatPrice, localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import type { Product } from "@/types/api";

export function ProductCard({ product }: { product: Product }) {
  const language = useLanguageStore((state) => state.language);
  const t = useTranslate();
  const name = localizedField(language, product, "name");
  const image = product.images.find((img) => img.is_main) ?? product.images[0];

  return (
    <Link
      to={`/product/${product.id}`}
      className="flex flex-col overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm"
    >
      <div className="flex aspect-square items-center justify-center bg-gray-50">
        {image?.url ? (
          <img src={image.url} alt={name} className="size-full object-cover" />
        ) : (
          <span className="text-3xl">📦</span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <p className="line-clamp-2 text-sm font-medium text-gray-900">{name}</p>
        <div className="mt-auto flex items-baseline gap-1">
          <span className="text-base font-semibold text-gray-900">
            {formatPrice(product.price)}
          </span>
          <span className="text-xs text-gray-500">{t("common.som")}</span>
        </div>
        {product.stock_qty <= 0 && (
          <span className="text-xs font-medium text-red-500">{t("product.out_of_stock")}</span>
        )}
      </div>
    </Link>
  );
}
