import { useEffect, useState, type FormEvent } from "react";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import type { Address } from "@/types/api";
import type { AddressInput } from "@/hooks/customer";

interface AddressDraft {
  label: string;
  address_text: string;
  address_comment: string;
}

function toDraft(address: Address | null): AddressDraft {
  return {
    label: address?.label ?? "",
    address_text: address?.address_text ?? "",
    address_comment: address?.address_comment ?? "",
  };
}

export function AddressFormDialog({
  address,
  onCancel,
  onSubmit,
}: {
  address: Address | null;
  onCancel: () => void;
  onSubmit: (address: AddressInput) => Promise<void>;
}) {
  const t = useTranslate();
  const [draft, setDraft] = useState<AddressDraft>(() => toDraft(address));
  const [validationError, setValidationError] = useState<TranslationKey | null>(null);
  const [submitError, setSubmitError] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const isEditing = address !== null;

  useEffect(() => {
    setDraft(toDraft(address));
    setValidationError(null);
    setSubmitError(false);
  }, [address?.id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const label = draft.label.trim();
    const addressText = draft.address_text.trim();
    const comment = draft.address_comment.trim();
    if (label.length < 1 || label.length > 60) {
      setValidationError("addresses.validation.label");
      return;
    }
    if (addressText.length < 1 || addressText.length > 1000) {
      setValidationError("addresses.validation.address_text");
      return;
    }
    if (comment.length > 500) {
      setValidationError("addresses.validation.address_comment");
      return;
    }

    setValidationError(null);
    setSubmitError(false);
    setIsSaving(true);
    try {
      await onSubmit({
        label,
        address_text: addressText,
        address_comment: comment || null,
      });
      onCancel();
    } catch {
      setSubmitError(true);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/50 p-3 sm:items-center" role="presentation">
      <section
        aria-labelledby="address-form-title"
        aria-modal="true"
        className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-900"
        role="dialog"
      >
        <h2 className="mb-4 text-lg font-semibold text-slate-900 dark:text-white" id="address-form-title">
          {t(isEditing ? "addresses.edit_title" : "addresses.create_title")}
        </h2>
        <form className="flex flex-col gap-3" onSubmit={(event) => void save(event)}>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("addresses.label")}
            <input
              autoComplete="off"
              className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-white/5 dark:text-white"
              disabled={isSaving}
              maxLength={60}
              onChange={(event) => { setDraft({ ...draft, label: event.target.value }); setValidationError(null); setSubmitError(false); }}
              value={draft.label}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("addresses.address_text")}
            <textarea
              autoComplete="street-address"
              className="min-h-24 rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-white/5 dark:text-white"
              disabled={isSaving}
              maxLength={1000}
              onChange={(event) => { setDraft({ ...draft, address_text: event.target.value }); setValidationError(null); setSubmitError(false); }}
              rows={3}
              value={draft.address_text}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("addresses.address_comment")}
            <textarea
              className="min-h-20 rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-white/5 dark:text-white"
              disabled={isSaving}
              maxLength={500}
              onChange={(event) => { setDraft({ ...draft, address_comment: event.target.value }); setValidationError(null); setSubmitError(false); }}
              rows={2}
              value={draft.address_comment}
            />
          </label>
          {validationError && <p className="text-sm text-red-700 dark:text-red-200" role="alert">{t(validationError)}</p>}
          {submitError && <p className="text-sm text-red-700 dark:text-red-200" role="alert">{t("addresses.action_error")}</p>}
          <div className="flex gap-2 pt-1">
            <button className="min-h-11 flex-1 rounded-lg bg-brand px-4 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50" disabled={isSaving} type="submit">
              {t("addresses.save")}
            </button>
            <button className="min-h-11 rounded-lg border border-slate-300 px-4 font-semibold text-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:text-slate-200" disabled={isSaving} onClick={onCancel} type="button">
              {t("addresses.cancel")}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
