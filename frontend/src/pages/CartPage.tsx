import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useCart, useRemoveCartItem, useUpdateCartItem } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { QuantityStepper } from "@/components/QuantityStepper";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { formatPrice, localizedField } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";

export function CartPage() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  const isAuthenticated = Boolean(accessToken && userId);
  const { openLogin } = useCustomerAuth();
  const navigate = useNavigate();
  const [mutationError, setMutationError] = useState<"update" | "remove" | null>(null);

  useEffect(() => {
    setMutationError(null);
  }, [authEpoch, userId]);

  const { data: cart, isLoading, isError, refetch } = useCart(isAuthenticated);
  const updateItem = useUpdateCartItem();
  const removeItem = useRemoveCartItem();

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-gray-600 dark:text-gray-300">{t("cart.login_hint")}</p>
        <button className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white" onClick={openLogin} type="button">
          {t("auth.sign_in")}
        </button>
      </div>
    );
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
                        min={Math.max(1, item.product.min_order_qty)}
                        max={item.product.stock_qty}
                        disabled={
                          updateItem.isPending ||
                          removeItem.isPending ||
                          item.product.stock_qty < Math.max(1, item.product.min_order_qty)
                        }
                        onChange={(quantity) => {
                          const bounded = Math.min(
                            item.product.stock_qty,
                            Math.max(Math.max(1, item.product.min_order_qty), quantity),
                          );
                          setMutationError(null);
                          updateItem.mutate(
                            { productId: item.product_id, quantity: bounded },
                            {
                              onSuccess: () => {
                                const current = useAuthStore.getState();
                                if (current.authEpoch === authEpoch && current.userId === userId) {
                                  setMutationError(null);
                                }
                              },
                              onError: () => {
                                const current = useAuthStore.getState();
                                if (current.authEpoch === authEpoch && current.userId === userId) {
                                  setMutationError("update");
                                }
                              },
                            },
                          );
                        }}
                      />
                      <button
                        aria-label={`${t("cart.remove")} ${name}`}
                        className="rounded-md px-2 py-1 text-xs font-medium text-red-600 disabled:opacity-50"
                        disabled={updateItem.isPending || removeItem.isPending}
                        onClick={() => {
                          setMutationError(null);
                          removeItem.mutate(item.product_id, {
                            onSuccess: () => {
                              const current = useAuthStore.getState();
                              if (current.authEpoch === authEpoch && current.userId === userId) {
                                setMutationError(null);
                              }
                            },
                            onError: () => {
                              const current = useAuthStore.getState();
                              if (current.authEpoch === authEpoch && current.userId === userId) {
                                setMutationError("remove");
                              }
                            },
                          });
                        }}
                        type="button"
                      >
                        {t("cart.remove")}
                      </button>
                      <span className="text-sm font-semibold text-gray-900">
                        {formatPrice(Number(item.product.price) * item.quantity)} {t("common.som")}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {mutationError && (
            <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200" role="alert">
              {mutationError === "update" ? t("cart.update_error") : t("cart.remove_error")}
            </p>
          )}

          <div className="fixed bottom-24 mx-auto flex w-full max-w-lg flex-col gap-3 border-t border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#14161b]">
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
