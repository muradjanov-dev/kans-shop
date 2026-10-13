import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useCart, useRemoveCartItem, useUpdateCartItem } from "@/hooks/queries";
import { Spinner } from "@/components/Spinner";
import { ErrorState } from "@/components/ErrorState";
import { ProductImage } from "@/components/ProductImage";
import { QuantityStepper } from "@/components/QuantityStepper";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import { formatExactPrice, localizedField } from "@/lib/format";
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
  const [mutationError, setMutationError] = useState<
    "update" | "remove" | null
  >(null);

  useEffect(() => {
    setMutationError(null);
  }, [authEpoch, userId]);

  const { data: cart, isLoading, isError, refetch } = useCart(isAuthenticated);
  const updateItem = useUpdateCartItem();
  const removeItem = useRemoveCartItem();

  if (!isAuthenticated) {
    return (
      <div className="page-shell empty-state flex flex-col items-center gap-4">
        <p className="text-sm text-[var(--muted)] dark:text-gray-400">
          {t("cart.login_hint")}
        </p>
        <button
          className="primary-button focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          onClick={openLogin}
          type="button"
        >
          {t("auth.sign_in")}
        </button>
      </div>
    );
  }
  if (isLoading) return <Spinner />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  const items = cart?.items ?? [];

  return (
    <div className="page-shell page-shell-wide">
      <h1 className="page-title mb-7 dark:text-white">{t("cart.title")}</h1>

      {items.length === 0 ? (
        <div className="surface empty-state flex flex-col items-center gap-3 dark:border-white/10 dark:bg-slate-900">
          <p className="text-sm font-medium text-[var(--ink)] dark:text-white">
            {t("cart.empty")}
          </p>
          <p className="text-xs text-[var(--muted)] dark:text-gray-400">
            {t("cart.empty_hint")}
          </p>
          <Link
            to="/"
            className="primary-button mt-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {t("nav.catalog")}
          </Link>
        </div>
      ) : (
        <div className="grid items-start gap-7 lg:grid-cols-[1fr_320px]">
          <div>
            <div className="surface divide-y divide-[var(--line)] overflow-hidden dark:border-white/10 dark:bg-slate-900">
              {items.map((item) => {
                const name = localizedField(language, item.product, "name");
                return (
                  <div key={item.id} className="flex gap-4 p-4 sm:p-5">
                    <div className="size-20 shrink-0 overflow-hidden rounded-xl sm:size-24">
                      <ProductImage product={item.product} className="p-2" />
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-3">
                      <p className="line-clamp-2 text-sm font-semibold text-[var(--ink)] dark:text-white">
                        {name}
                      </p>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <QuantityStepper
                          quantity={item.quantity}
                          min={Math.max(1, item.product.min_order_qty)}
                          max={item.product.stock_qty}
                          disabled={
                            updateItem.isPending ||
                            removeItem.isPending ||
                            item.product.stock_qty <
                              Math.max(1, item.product.min_order_qty)
                          }
                          onChange={(quantity) => {
                            const bounded = Math.min(
                              item.product.stock_qty,
                              Math.max(
                                Math.max(1, item.product.min_order_qty),
                                quantity,
                              ),
                            );
                            setMutationError(null);
                            updateItem.mutate(
                              { productId: item.product_id, quantity: bounded },
                              {
                                onSuccess: () => {
                                  const current = useAuthStore.getState();
                                  if (
                                    current.authEpoch === authEpoch &&
                                    current.userId === userId
                                  ) {
                                    setMutationError(null);
                                  }
                                },
                                onError: () => {
                                  const current = useAuthStore.getState();
                                  if (
                                    current.authEpoch === authEpoch &&
                                    current.userId === userId
                                  ) {
                                    setMutationError("update");
                                  }
                                },
                              },
                            );
                          }}
                        />
                        <button
                          aria-label={`${t("cart.remove")} ${name}`}
                          className="min-h-11 min-w-11 rounded-md px-2 py-1 text-xs font-medium text-red-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
                          disabled={
                            updateItem.isPending || removeItem.isPending
                          }
                          onClick={() => {
                            setMutationError(null);
                            removeItem.mutate(item.product_id, {
                              onSuccess: () => {
                                const current = useAuthStore.getState();
                                if (
                                  current.authEpoch === authEpoch &&
                                  current.userId === userId
                                ) {
                                  setMutationError(null);
                                }
                              },
                              onError: () => {
                                const current = useAuthStore.getState();
                                if (
                                  current.authEpoch === authEpoch &&
                                  current.userId === userId
                                ) {
                                  setMutationError("remove");
                                }
                              },
                            });
                          }}
                          type="button"
                        >
                          {t("cart.remove")}
                        </button>
                        <span className="text-sm font-semibold text-[var(--ink)] dark:text-white">
                          {formatLineTotal(item.product.price, item.quantity)}{" "}
                          {t("common.som")}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {mutationError && (
              <p
                className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700"
                role="alert"
              >
                {mutationError === "update"
                  ? t("cart.update_error")
                  : t("cart.remove_error")}
              </p>
            )}
          </div>
          <div className="action-bar cart-summary w-full flex flex-col gap-4 lg:top-28 dark:border-white/10 dark:bg-slate-900">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--muted)] dark:text-gray-400">
                {t("cart.subtotal")}
              </span>
              <span className="font-semibold text-[var(--ink)] dark:text-white">
                {formatExactPrice(cart?.subtotal ?? "0")} {t("common.som")}
              </span>
            </div>
            <button
              onClick={() => navigate("/checkout")}
              className="primary-button focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {t("cart.checkout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function formatLineTotal(unitPrice: string, quantity: number): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(unitPrice.trim());
  if (!match || !Number.isSafeInteger(quantity) || quantity < 0) return "—";

  const whole = match[2] ?? "0";
  const fraction = match[3] ?? "";
  const scale = 10n ** BigInt(fraction.length);
  const totalMinor = BigInt(`${whole}${fraction}`) * BigInt(quantity);
  const totalWhole = totalMinor / scale;
  const totalFraction = (totalMinor % scale)
    .toString()
    .padStart(fraction.length, "0")
    .replace(/0+$/, "");
  const sign = match[1] === "-" && totalMinor > 0n ? "-" : "";
  const total = `${sign}${totalWhole}${totalFraction ? `.${totalFraction}` : ""}`;
  return formatExactPrice(total);
}
