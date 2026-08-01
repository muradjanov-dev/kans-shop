import { useTranslate } from "@/lib/i18n";

export function ErrorState({ onRetry }: { onRetry?: () => void }) {
  const t = useTranslate();
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center text-gray-500">
      <p>{t("common.error")}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white"
        >
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
