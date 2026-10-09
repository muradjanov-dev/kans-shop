import { useTranslate } from "@/lib/i18n";

export function ErrorState({ onRetry, message }: { onRetry?: () => void; message?: string }) {
  const t = useTranslate();
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center text-gray-500">
      <p>{message ?? t("common.error")}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="min-h-11 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}
