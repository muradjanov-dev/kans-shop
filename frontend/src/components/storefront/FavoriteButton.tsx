import { useAuthStore } from "@/store/auth";
import { useCustomerAuthActions } from "@/features/customer-auth/CustomerAuthProvider";
import { useFavoriteState } from "@/hooks/customer";
import { useTranslate } from "@/lib/i18n";

export function FavoriteButton({
  productId,
  productName,
  className = "",
}: {
  productId: number;
  productName?: string;
  className?: string;
}) {
  const t = useTranslate();
  const userId = useAuthStore((state) => state.userId);
  const { addFavorite } = useCustomerAuthActions();
  const favorite = useFavoriteState(productId);
  const isFavorite = userId ? favorite.isFavorite : false;
  const label = productName
    ? `${t(isFavorite ? "favorite.remove" : "favorite.add")}: ${productName}`
    : t(isFavorite ? "favorite.remove" : "favorite.add");

  return (
    <button
      aria-busy={Boolean(userId && (favorite.isLoading || favorite.isMutationPending))}
      aria-label={favorite.isError && userId ? t("favorite.retry") : label}
      aria-pressed={isFavorite}
      className={`flex min-h-11 min-w-11 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-xl leading-none text-rose-600 shadow-sm transition-colors hover:bg-rose-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-wait disabled:opacity-60 dark:border-white/15 dark:bg-slate-900/95 dark:text-rose-300 dark:hover:bg-rose-950/40 ${className}`}
      disabled={Boolean(userId && (favorite.isLoading || favorite.isMutationPending))}
      onClick={() => {
        if (!userId) addFavorite(productId);
        else if (favorite.isError) void favorite.refetch();
        else favorite.toggle();
      }}
      type="button"
    >
      <span aria-hidden="true">{isFavorite ? "♥" : "♡"}</span>
    </button>
  );
}
