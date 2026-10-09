import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useCustomerProfile, useUpdateCustomerProfile } from "@/hooks/customer";
import { isValidUzPhone, normalizeUzPhone } from "@/lib/phone";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { useAuthStore } from "@/store/auth";
import { useLanguageStore } from "@/store/language";
import type { Profile } from "@/types/api";

type ProfileDraft = { display_name: string; phone: string; language: Profile["language"] };

function toDraft(profile: Profile): ProfileDraft {
  return {
    display_name: profile.display_name,
    phone: profile.phone ?? "",
    language: profile.language,
  };
}

export function ProfilePage() {
  const t = useTranslate();
  const userId = useAuthStore((state) => state.userId);
  const accessToken = useAuthStore((state) => state.accessToken);
  const { openLogin, logout } = useCustomerAuth();
  const profile = useCustomerProfile();
  const updateProfile = useUpdateCustomerProfile();
  const [draft, setDraft] = useState<ProfileDraft | null>(null);
  const [validationError, setValidationError] = useState<TranslationKey | null>(null);
  const [saved, setSaved] = useState(false);
  const draftOwnerId = useRef<string | null>(null);
  const isAuthenticated = Boolean(accessToken && userId);

  useEffect(() => {
    if (userId && draftOwnerId.current && draftOwnerId.current !== userId) {
      draftOwnerId.current = null;
      setDraft(null);
      setValidationError(null);
      setSaved(false);
    }
  }, [userId]);

  useEffect(() => {
    if (userId && profile.data && draftOwnerId.current !== userId) {
      draftOwnerId.current = userId;
      setDraft(toDraft(profile.data));
      setValidationError(null);
      setSaved(false);
    }
  }, [profile.data, userId]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft) return;
    const name = draft.display_name.trim();
    const phone = draft.phone.trim();
    if (name.length < 1 || name.length > 128) {
      setValidationError("profile.validation.name");
      setSaved(false);
      return;
    }
    if (phone && !isValidUzPhone(phone)) {
      setValidationError("profile.validation.phone");
      setSaved(false);
      return;
    }
    if (!isAuthenticated) {
      openLogin();
      return;
    }

    setValidationError(null);
    setSaved(false);
    try {
      const updated = await updateProfile.mutateAsync({
        display_name: name,
        phone: phone ? normalizeUzPhone(phone) : null,
        language: draft.language,
      });
      setDraft(toDraft(updated));
      useLanguageStore.getState().setLanguage(updated.language);
      setSaved(true);
    } catch {
      // Keep the draft so a network, authorization or server failure can be retried.
    }
  }

  function clearAndLogout() {
    setDraft(null);
    draftOwnerId.current = null;
    setValidationError(null);
    setSaved(false);
    updateProfile.reset();
    logout();
  }

  return (
    <section aria-labelledby="profile-title" className="mx-auto max-w-3xl p-4 sm:p-6">
      <h1 className="mb-4 text-xl font-semibold text-slate-900 dark:text-white" id="profile-title">
        {t("account.profile_title")}
      </h1>
      <nav aria-label={t("account.navigation")} className="mb-5 flex flex-wrap gap-2">
        <Link className="inline-flex min-h-11 items-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium dark:border-white/10 dark:bg-slate-900" to="/favorites">
          {t("nav.favorites")}
        </Link>
        <Link className="inline-flex min-h-11 items-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium dark:border-white/10 dark:bg-slate-900" to="/profile/addresses">
          {t("nav.addresses")}
        </Link>
      </nav>

      {profile.isError && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200" role="alert">
          <span>{t("profile.load_error")}</span>
          <button className="min-h-11 px-2 font-semibold underline focus-visible:outline-2 focus-visible:outline-brand" onClick={() => void profile.refetch()} type="button">
            {t("account.retry")}
          </button>
        </div>
      )}

      {!isAuthenticated && !draft && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{t("account.sign_in_required")}</p>
          <button className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={openLogin} type="button">
            {t("auth.sign_in")}
          </button>
        </div>
      )}

      {isAuthenticated && profile.isLoading && !draft && (
        <p className="py-8 text-center text-sm text-slate-500" role="status">{t("common.loading")}</p>
      )}

      {draft && (
        <form className="flex max-w-xl flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900" onSubmit={(event) => void save(event)}>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("profile.name")}
            <input
              autoComplete="name"
              className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-white/5 dark:text-white"
              disabled={updateProfile.isPending}
              maxLength={128}
              onChange={(event) => { setDraft({ ...draft, display_name: event.target.value }); setSaved(false); }}
              required
              value={draft.display_name}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("profile.phone")}
            <input
              autoComplete="tel"
              className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-white/5 dark:text-white"
              disabled={updateProfile.isPending}
              inputMode="tel"
              maxLength={20}
              onChange={(event) => { setDraft({ ...draft, phone: event.target.value }); setSaved(false); }}
              value={draft.phone}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("profile.language")}
            <select
              className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15 dark:bg-slate-900 dark:text-white"
              disabled={updateProfile.isPending}
              onChange={(event) => { setDraft({ ...draft, language: event.target.value as Profile["language"] }); setSaved(false); }}
              value={draft.language}
            >
              <option value="uz">O‘zbekcha</option>
              <option value="ru">Русский</option>
            </select>
          </label>
          {validationError && <p className="text-sm text-red-700 dark:text-red-200" role="alert">{t(validationError)}</p>}
          {updateProfile.isError && <p className="text-sm text-red-700 dark:text-red-200" role="alert">{t("profile.save_error")}</p>}
          {saved && <p className="text-sm text-emerald-700 dark:text-emerald-300" role="status">{t("profile.save_success")}</p>}
          <div className="flex flex-wrap gap-2">
            <button className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50" disabled={updateProfile.isPending} type="submit">
              {t("profile.save")}
            </button>
            {isAuthenticated ? (
              <button className="min-h-11 rounded-lg border border-slate-300 px-5 font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15" onClick={clearAndLogout} type="button">
                {t("auth.logout")}
              </button>
            ) : (
              <button className="min-h-11 rounded-lg border border-slate-300 px-5 font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15" onClick={openLogin} type="button">
                {t("auth.sign_in")}
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
