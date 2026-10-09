import { useState } from "react";
import { Link } from "react-router-dom";
import { ProductCard } from "@/components/ProductCard";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useFavorites } from "@/hooks/customer";
import { useTranslate } from "@/lib/i18n";
import { useAuthStore } from "@/store/auth";

export function FavoritesPage() {
  const t = useTranslate();
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  const { openLogin } = useCustomerAuth();
  const [page, setPage] = useState(1);
  const favorites = useFavorites(page);
  const isAuthenticated = Boolean(accessToken && userId);

  return (
    <section aria-labelledby="favorites-title" className="mx-auto max-w-7xl p-4 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white" id="favorites-title">{t("account.favorites_title")}</h1>
        <Link className="inline-flex min-h-11 items-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium dark:border-white/10 dark:bg-slate-900" to="/profile">
          {t("nav.profile")}
        </Link>
      </div>

      {!isAuthenticated && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{t("account.sign_in_required")}</p>
          <button className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={openLogin} type="button">
            {t("auth.sign_in")}
          </button>
        </div>
      )}

      {isAuthenticated && favorites.isError && (
        <div className="flex items-center justify-between gap-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200" role="alert">
          <span>{t("favorite.load_error")}</span>
          <button className="min-h-11 px-2 font-semibold underline focus-visible:outline-2 focus-visible:outline-brand" onClick={() => void favorites.refetch()} type="button">
            {t("account.retry")}
          </button>
        </div>
      )}
      {isAuthenticated && favorites.isLoading && <p className="py-10 text-center text-sm text-slate-500" role="status">{t("common.loading")}</p>}
      {isAuthenticated && !favorites.isLoading && !favorites.isError && favorites.data?.items.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-white/15 dark:text-slate-400">{t("favorite.empty")}</p>
      )}
      {isAuthenticated && !favorites.isError && Boolean(favorites.data?.items.length) && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
            {favorites.data!.items.map((product) => <ProductCard key={product.id} product={product} />)}
          </div>
          {(favorites.data?.total_pages ?? 1) > 1 && (
            <nav aria-label={t("favorite.pagination")} className="mt-5 flex items-center justify-center gap-3">
              <button className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 dark:border-white/15" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} type="button">
                {t("common.back")}
              </button>
              <span className="text-sm text-slate-600 dark:text-slate-300">{page} / {favorites.data?.total_pages}</span>
              <button className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 dark:border-white/15" disabled={page >= (favorites.data?.total_pages ?? 1)} onClick={() => setPage((value) => value + 1)} type="button">
                {t("catalog.load_more")}
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
