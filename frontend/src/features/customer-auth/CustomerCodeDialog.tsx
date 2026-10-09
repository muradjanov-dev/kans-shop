import { useState, type FormEvent } from "react";
import { useTranslate } from "@/lib/i18n";

interface CustomerCodeDialogProps {
  open: boolean;
  pending: boolean;
  errorCode: string | null;
  onSubmit: (code: string) => void;
  onCancel: () => void;
  onCodeChange: () => void;
}

export function CustomerCodeDialog({
  open,
  pending,
  errorCode,
  onSubmit,
  onCancel,
  onCodeChange,
}: CustomerCodeDialogProps) {
  const t = useTranslate();
  const [code, setCode] = useState("");

  if (!open) return null;

  const errorMessage = errorCode === "INVALID_OR_EXPIRED_CODE"
    ? t("auth.code_invalid")
    : errorCode === "RATE_LIMITED"
      ? t("auth.code_rate_limited")
      : errorCode
        ? t("auth.login_error")
        : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = code.trim();
    if (normalized) onSubmit(normalized);
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-end justify-center bg-black/50 p-3 sm:items-center">
      <section
        aria-labelledby="customer-code-title"
        aria-modal="true"
        className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl dark:bg-[#141b2b]"
        role="dialog"
      >
        <h2 id="customer-code-title" className="text-lg font-semibold text-gray-900 dark:text-white">
          {t("auth.login_title")}
        </h2>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          {t("auth.login_instructions")}
        </p>
        <a
          className="mt-3 inline-flex rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white"
          href="https://t.me/kansshopbot?start=web_login"
          rel="noreferrer"
          target="_blank"
        >
          {t("auth.open_telegram")}
        </a>
        <form className="mt-4 flex flex-col gap-3" onSubmit={handleSubmit}>
          <label className="flex flex-col gap-1 text-sm font-medium text-gray-700 dark:text-gray-200">
            {t("auth.code_label")}
            <input
              autoComplete="one-time-code"
              autoFocus
              disabled={pending}
              inputMode="text"
              onChange={(event) => {
                setCode(event.target.value);
                onCodeChange();
              }}
              value={code}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-base text-gray-900 outline-none focus:border-brand dark:border-white/15 dark:bg-white/5 dark:text-white"
            />
          </label>
          {errorMessage && (
            <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200" role="alert">
              {errorMessage}
            </p>
          )}
          <div className="flex gap-2">
            <button
              className="flex-1 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              disabled={pending || !code.trim()}
              type="submit"
            >
              {pending ? t("auth.signing_in") : t("auth.submit_code")}
            </button>
            <button
              className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-semibold text-gray-700 dark:border-white/15 dark:text-gray-200"
              disabled={pending}
              onClick={onCancel}
              type="button"
            >
              {t("common.cancel")}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
