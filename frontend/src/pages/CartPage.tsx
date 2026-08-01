import { Link, useNavigate } from "react-router-dom";
import { useCart, useRemoveCartItem, useUpdateCartItem } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { QuantityStepper } from "@/components/QuantityStepper";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { formatPrice, localizedField } from "@/lib/format";
import { useAuthStore } from "@/store/auth";

export function CartPage() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const isAuthenticated = Boolean(useAuthStore((state) => state.accessToken));
  const navigate = useNavigate();

  const { data: cart, isLoading, isError, refetch } = useCart(isAuthenticated);
  const updateItem = useUpdateCartItem();
  const removeItem = useRemoveCartItem();

  if (!isAuthenticated) {
    return <p className="p-6 text-center text-sm text-gray-500">{t("orders.open_telegram")}</p>;
  }
  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  const items = cart?.items ?? [];

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold text-gray-900">{t("cart.title")}</h1>

      {items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-16 text-center">
          <p className="text-sm font-medium text-gray-700">{t("cart.empty")}</p>
          <p className="text-xs text-gray-500">{t("cart.empty_hint")}</p>
          <Link to="/" className="mt-3 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white">
            {t("nav.catalog")}
          </Link>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {items.map((item) => {
              const name = localizedField(language, item.product, "name");
              return (
                <div key={item.id} className="flex gap-3 rounded-xl border border-gray-100 p-3">
                  <div className="flex size-16 shrink-0 items-center justify-center rounded-lg bg-gray-50">
                    {item.product.images[0]?.url ? (
                      <img
                        src={item.product.images[0].url}
                        alt={name}
                        className="size-full rounded-lg object-cover"
                      />
                    ) : (
                      <span className="text-2xl">📦</span>
                    )}
                  </div>
                  <div className="flex flex-1 flex-col gap-2">
                    <p className="line-clamp-2 text-sm font-medium text-gray-900">{name}</p>
                    <div className="flex items-center justify-between">
                      <QuantityStepper
                        quantity={item.quantity}
                        min={item.product.min_order_qty}
                        disabled={updateItem.isPending || removeItem.isPending}
                        onChange={(quantity) => {
                          if (quantity <= 0) {
                            removeItem.mutate(item.product_id);
                          } else {
                            updateItem.mutate({ productId: item.product_id, quantity });
                          }
                        }}
                      />
                      <span className="text-sm font-semibold text-gray-900">
                        {formatPrice(Number(item.price_snapshot) * item.quantity)} {t("common.som")}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="fixed bottom-16 mx-auto flex w-full max-w-lg flex-col gap-3 border-t border-gray-200 bg-white p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">{t("cart.subtotal")}</span>
              <span className="font-semibold text-gray-900">
                {formatPrice(cart?.subtotal ?? 0)} {t("common.som")}
              </span>
            </div>
            <button
              onClick={() => navigate("/checkout")}
              className="rounded-lg bg-brand py-2.5 text-sm font-semibold text-white"
            >
              {t("cart.checkout")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
