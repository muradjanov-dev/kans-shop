import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminPageProps } from "@/admin/adminRoutes";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import {
  cancelAdminBroadcast,
  createAdminBroadcastDraft,
  getAdminBroadcastProgress,
  launchAdminBroadcast,
  previewAdminBroadcast,
  uploadAdminBroadcastPhoto,
  adminQueryKeys,
  useAdminBroadcastProgress,
} from "@/admin/adminQueries";
import { getAdminApiErrorCode } from "@/admin/api";
import type {
  AdminBroadcast,
  AdminBroadcastContent,
  AdminBroadcastDraftIn,
  AdminBroadcastPreview,
  AdminBroadcastPreviewIn,
  AdminBroadcastTarget,
} from "@/admin/adminTypes";
import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { AdminField, AdminPageFrame, AdminPanel, buttonClass, primaryButtonClass } from "@/admin/pages/AdminPageFrame";

const targets: AdminBroadcastTarget[] = ["all", "active", "buyers"];

export function BroadcastsPage({ route }: AdminPageProps) {
  const t = useTranslate();
  const { session } = useAdminAuth();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<AdminBroadcastContent>(emptyDraft());
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoInputKey, setPhotoInputKey] = useState(0);
  const [preview, setPreview] = useState<AdminBroadcastPreview | null>(null);
  const [broadcast, setBroadcast] = useState<AdminBroadcast | null>(null);
  const [progressId, setProgressId] = useState<number | null>(null);
  const [progressInput, setProgressInput] = useState("");
  const [resumeRequested, setResumeRequested] = useState(false);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [launchKey, setLaunchKey] = useState<string | null>(null);
  const launchKeyRef = useRef<string | null>(null);
  const [unknownLaunchOutcome, setUnknownLaunchOutcome] = useState(false);
  const [alreadyLaunched, setAlreadyLaunched] = useState(false);
  const [pageError, setPageError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const progress = useAdminBroadcastProgress(progressId);

  const invalidateProgress = (id: number) => queryClient.invalidateQueries({ queryKey: adminQueryKeys.broadcast(id) });
  const uploadPhoto = useMutation({
    mutationFn: (file: File) => uploadAdminBroadcastPhoto(file),
    onSuccess: ({ photo_storage_key: photoStorageKey }) => {
      setDraft((current) => ({ ...current, photo_storage_key: photoStorageKey, photo_file_id: null }));
      setPhotoFile(null);
      setPhotoInputKey((key) => key + 1);
      clearPreview();
      setPageError(null);
      setNotice(t("admin.broadcasts.photo_ready"));
    },
    onError: setPageError,
  });
  const makePreview = useMutation({
    mutationFn: (content: AdminBroadcastPreviewIn) => previewAdminBroadcast(content),
    onSuccess: (result) => {
      setPreview(result);
      setPageError(null);
      setNotice("");
      setLaunchKey(null);
      launchKeyRef.current = null;
    },
    onError: (error) => {
      setPreview(null);
      setPageError(error);
      setNotice("");
    },
  });
  const createDraft = useMutation({
    mutationFn: (body: AdminBroadcastDraftIn) => createAdminBroadcastDraft(body),
    onSuccess: (created) => {
      setBroadcast(created);
      setProgressId(null);
      setAlreadyLaunched(false);
      setLaunchKey(null);
      launchKeyRef.current = null;
      setPageError(null);
      setNotice("");
    },
    onError: (error) => {
      const code = getAdminApiErrorCode(error);
      if (isPreviewConflict(code)) setPreview(null);
      setPageError(error);
      setNotice("");
    },
  });
  const launch = useMutation({
    mutationFn: ({ id, fingerprint, count, idempotencyKey }: { id: number; fingerprint: string; count: number; idempotencyKey: string }) =>
      launchAdminBroadcast(id, { preview_fingerprint: fingerprint, preview_count: count, idempotency_key: idempotencyKey }),
    onSuccess: (launched) => {
      setBroadcast(launched);
      queryClient.setQueryData([...adminQueryKeys.broadcast(launched.id), session?.admin_id ?? "anonymous"], launched);
      setProgressId(launched.id);
      setResumeRequested(false);
      setConfirmationOpen(false);
      setUnknownLaunchOutcome(false);
      setAlreadyLaunched(false);
      setLaunchKey(null);
      launchKeyRef.current = null;
      setPageError(null);
      setNotice("");
      void invalidateProgress(launched.id);
    },
    onError: (error) => {
      const code = getAdminApiErrorCode(error);
      setPageError(error);
      setNotice("");
      if (isPreviewConflict(code)) {
        setPreview(null);
        setLaunchKey(null);
        launchKeyRef.current = null;
        setConfirmationOpen(false);
        setUnknownLaunchOutcome(false);
      } else if (code === "BROADCAST_ALREADY_LAUNCHED") {
        setPreview(null);
        setConfirmationOpen(false);
        setUnknownLaunchOutcome(false);
        setAlreadyLaunched(true);
      } else if (isUnknownOutcome(error)) {
        setUnknownLaunchOutcome(true);
      } else {
        setUnknownLaunchOutcome(false);
      }
    },
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelAdminBroadcast(id),
    onSuccess: (current) => {
      setBroadcast(current);
      queryClient.setQueryData([...adminQueryKeys.broadcast(current.id), session?.admin_id ?? "anonymous"], current);
      setProgressId(current.id);
      setPageError(null);
      setNotice(t("admin.broadcasts.cancelled_notice"));
      void invalidateProgress(current.id);
    },
    onError: setPageError,
  });
  const loadProgress = useMutation({
    mutationFn: (id: number) => getAdminBroadcastProgress(id),
    onSuccess: (loaded) => {
      const isDifferentBroadcast = broadcast?.id !== loaded.id;
      setBroadcast(loaded);
      queryClient.setQueryData([...adminQueryKeys.broadcast(loaded.id), session?.admin_id ?? "anonymous"], loaded);
      setProgressId(loaded.id);
      if (isDifferentBroadcast) {
        setDraft(contentFromBroadcast(loaded));
        setPreview(null);
        setLaunchKey(null);
        launchKeyRef.current = null;
        setAlreadyLaunched(false);
      }
      if (loaded.status !== "draft") {
        setLaunchKey(null);
        launchKeyRef.current = null;
        setUnknownLaunchOutcome(false);
        setAlreadyLaunched(false);
        setConfirmationOpen(false);
      }
      setResumeRequested(false);
      setPageError(null);
      setNotice("");
    },
    onError: setPageError,
  });

  useEffect(() => {
    if (!progress.data) return;
    setBroadcast((current) => current?.id === progress.data?.id ? progress.data : current);
    if (progress.data.status !== "draft") {
      setLaunchKey(null);
      launchKeyRef.current = null;
      setUnknownLaunchOutcome(false);
      setConfirmationOpen(false);
    }
    if (!resumeRequested) return;
    setDraft(contentFromBroadcast(progress.data));
    setPreview(null);
    setLaunchKey(null);
    launchKeyRef.current = null;
    setResumeRequested(false);
  }, [progress.data, resumeRequested]);

  const locked = broadcast !== null;
  const code = getAdminApiErrorCode(pageError);
  const previewReady = preview !== null && validContent(draft);
  const canReviewLaunch = broadcast?.status === "draft" && previewReady && !alreadyLaunched;
  const currentIsSending = broadcast?.status === "sending";

  function clearPreview() {
    setPreview(null);
    setLaunchKey(null);
    launchKeyRef.current = null;
  }

  function changeDraft<K extends keyof AdminBroadcastContent>(key: K, value: AdminBroadcastContent[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    clearPreview();
    setPageError(null);
    setNotice("");
  }

  function requestPreview() {
    if (!validContent(draft) || alreadyLaunched || unknownLaunchOutcome) return;
    setPageError(null);
    setNotice("");
    makePreview.mutate(contentPayload(draft));
  }

  function requestDraft() {
    if (!preview || !validContent(draft) || broadcast !== null) return;
    setPageError(null);
    setNotice("");
    createDraft.mutate({ ...contentPayload(draft), preview_fingerprint: preview.preview_fingerprint, preview_count: preview.preview_count });
  }

  function beginLaunch() {
    if (!broadcast || !preview || !previewReady || alreadyLaunched) return;
    setPageError(null);
    if (!launchKeyRef.current) setUnknownLaunchOutcome(false);
    setConfirmationOpen(true);
  }

  function submitLaunch() {
    if (!broadcast || !preview) return;
    const key = launchKeyRef.current ?? crypto.randomUUID();
    launchKeyRef.current = key;
    setLaunchKey(key);
    launch.mutate({ id: broadcast.id, fingerprint: preview.preview_fingerprint, count: preview.preview_count, idempotencyKey: key });
  }

  function refreshProgress() {
    const id = broadcast?.id ?? positiveId(progressInput);
    if (id !== null && id !== undefined) {
      if (!broadcast || id !== broadcast.id) setResumeRequested(true);
      loadProgress.mutate(id);
    }
  }

  function startNewDraft() {
    setBroadcast(null);
    setProgressId(null);
    setProgressInput("");
    setResumeRequested(false);
    setDraft(emptyDraft());
    setPhotoFile(null);
    setPhotoInputKey((key) => key + 1);
    setPreview(null);
    setConfirmationOpen(false);
    setLaunchKey(null);
    launchKeyRef.current = null;
    setUnknownLaunchOutcome(false);
    setAlreadyLaunched(false);
    setPageError(null);
    setNotice("");
    uploadPhoto.reset();
    makePreview.reset();
    createDraft.reset();
    launch.reset();
    cancel.reset();
  }

  const errorText = code === "BROADCAST_AUDIENCE_CHANGED" ? t("admin.broadcasts.audience_changed")
    : code === "BROADCAST_PREVIEW_CHANGED" ? t("admin.broadcasts.content_changed")
      : code === "BROADCAST_ALREADY_LAUNCHED" ? t("admin.broadcasts.already_launched")
        : code === "BROADCAST_NOT_FOUND" ? t("admin.broadcasts.not_found")
          : code === "BROADCAST_MEDIA_TOO_LARGE" ? t("admin.broadcasts.media_too_large")
            : code === "UNSUPPORTED_MEDIA_TYPE" ? t("admin.broadcasts.media_type")
              : code === "VALIDATION_ERROR" ? t("admin.broadcasts.validation")
                : null;

  return <AdminPageFrame route={route} description={t("admin.broadcasts.description")}>
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(17rem,0.85fr)]">
      <AdminPanel title={locked ? t("admin.broadcasts.item_title", { id: broadcast.id }) : t("admin.broadcasts.create_title")}>
        <div className="space-y-4">
          <AdminField label={t("admin.broadcasts.target")}>
            {(className) => <select className={className} disabled={locked || makePreview.isPending || createDraft.isPending} onChange={(event) => changeDraft("target", event.target.value as AdminBroadcastTarget)} value={draft.target}>
              {targets.map((target) => <option key={target} value={target}>{t(`admin.broadcasts.target.${target}` as TranslationKey)}</option>)}
            </select>}
          </AdminField>
          <AdminField label={t("admin.broadcasts.text")}>
            {(className) => <textarea className={`${className} min-h-32`} disabled={locked} onChange={(event) => changeDraft("text", event.target.value)} required value={draft.text} />}
          </AdminField>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <AdminField label={t("admin.broadcasts.button_text")}>
              {(className) => <input className={className} disabled={locked} onChange={(event) => changeDraft("button_text", event.target.value || null)} value={draft.button_text ?? ""} />}
            </AdminField>
            <AdminField label={t("admin.broadcasts.button_url")}>
              {(className) => <input className={className} disabled={locked} onChange={(event) => changeDraft("button_url", event.target.value || null)} pattern="https://.+" type="url" value={draft.button_url ?? ""} />}
            </AdminField>
          </div>
          <div className="flex min-w-0 flex-wrap items-end gap-3">
            <AdminField className="min-w-[14rem] flex-1" label={t("admin.broadcasts.photo")}>
              {(className) => <input accept="image/jpeg,image/png,image/webp" className={className} disabled={locked || uploadPhoto.isPending} key={photoInputKey} onChange={(event) => { setPhotoFile(event.target.files?.[0] ?? null); clearPreview(); setPageError(null); }} type="file" />}
            </AdminField>
            <button className={buttonClass} disabled={locked || !photoFile || uploadPhoto.isPending} onClick={() => { if (photoFile) uploadPhoto.mutate(photoFile); }} type="button">{uploadPhoto.isPending ? t("admin.common.loading") : t("admin.broadcasts.upload_photo")}</button>
          </div>
          {draft.photo_storage_key && <p className="text-sm text-emerald-700 dark:text-emerald-300" role="status">{t("admin.broadcasts.photo_ready")}</p>}

          <div className="flex min-w-0 flex-wrap gap-2">
            {!currentIsSending && <button className={buttonClass} disabled={alreadyLaunched || unknownLaunchOutcome || !validContent(draft) || photoFile !== null || makePreview.isPending || uploadPhoto.isPending} onClick={requestPreview} type="button">{makePreview.isPending ? t("admin.broadcasts.previewing") : t("admin.broadcasts.preview")}</button>}
            {!locked && <button className={primaryButtonClass} disabled={!previewReady || createDraft.isPending} onClick={requestDraft} type="button">{createDraft.isPending ? t("admin.broadcasts.creating_draft") : t("admin.broadcasts.create_draft")}</button>}
            {canReviewLaunch && <button className={primaryButtonClass} onClick={beginLaunch} type="button">{t("admin.broadcasts.review_launch")}</button>}
          </div>

          {preview && <p className="rounded-lg bg-indigo-50 p-3 text-sm font-medium text-indigo-950 dark:bg-indigo-400/10 dark:text-indigo-100" role="status">{t("admin.broadcasts.preview_count", { count: preview.preview_count })}</p>}
          {pageError != null && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{errorText ?? t("admin.common.action_error")}</p>}
          {notice && <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-300/10 dark:text-emerald-100" role="status">{notice}</p>}
        </div>
      </AdminPanel>

      <div className="space-y-4">
        {broadcast && <BroadcastProgress
          broadcast={broadcast}
          error={progress.isError ? progress.error : null}
          errorCode={progress.isError ? getAdminApiErrorCode(progress.error) : null}
          refreshing={progress.isFetching || loadProgress.isPending}
          cancelling={cancel.isPending}
          onRefresh={() => {
            setPageError(null);
            if (progressId === broadcast.id) void progress.refetch();
            else loadProgress.mutate(broadcast.id);
          }}
          onCancel={() => cancel.mutate(broadcast.id)}
        />}

        <AdminPanel title={t("admin.broadcasts.resume")}>
          <p className="mb-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{t("admin.broadcasts.resume_help")}</p>
          <div className="flex min-w-0 flex-wrap items-end gap-3">
            <AdminField className="min-w-[10rem] flex-1" label={t("admin.broadcasts.broadcast_id")}>
              {(className) => <input className={className} inputMode="numeric" onChange={(event) => setProgressInput(event.target.value.replace(/\D/g, ""))} value={progressInput} />}
            </AdminField>
            <button className={buttonClass} disabled={!positiveId(progressInput) || loadProgress.isPending} onClick={refreshProgress} type="button">{loadProgress.isPending ? t("admin.common.loading") : t("admin.broadcasts.load_progress")}</button>
          </div>
        </AdminPanel>

        {broadcast && broadcast.status !== "sending" && !unknownLaunchOutcome && launchKey === null && !launch.isPending && <button className={buttonClass} onClick={startNewDraft} type="button">{t("admin.broadcasts.start_new")}</button>}
      </div>
    </div>

    {confirmationOpen && preview && broadcast && <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/50 p-3 sm:p-6" role="presentation">
      <section aria-labelledby="broadcast-confirm-title" aria-modal="true" className="mx-auto my-12 max-w-lg rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-950 sm:p-7" role="dialog">
        <h2 className="text-xl font-semibold" id="broadcast-confirm-title">{t("admin.broadcasts.confirm_title")}</h2>
        <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">{t("admin.broadcasts.confirm_body", { count: preview.preview_count })}</p>
        {unknownLaunchOutcome && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-300/10 dark:text-amber-100" role="alert">{t("admin.broadcasts.unknown_outcome")}</p>}
        {pageError != null && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{errorText ?? t("admin.common.action_error")}</p>}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button className={buttonClass} disabled={launch.isPending} onClick={() => setConfirmationOpen(false)} type="button">{t("common.cancel")}</button>
          <button className={primaryButtonClass} disabled={launch.isPending} onClick={submitLaunch} type="button">{launch.isPending ? t("admin.common.loading") : unknownLaunchOutcome && launchKey ? t("admin.broadcasts.retry_launch") : t("admin.broadcasts.confirm_launch")}</button>
        </div>
      </section>
    </div>}
  </AdminPageFrame>;
}

function BroadcastProgress({ broadcast, error, errorCode, refreshing, cancelling, onRefresh, onCancel }: {
  broadcast: AdminBroadcast;
  error: unknown;
  errorCode: string | null;
  refreshing: boolean;
  cancelling: boolean;
  onRefresh: () => void;
  onCancel: () => void;
}) {
  const t = useTranslate();
  return <AdminPanel title={t("admin.broadcasts.progress")}>
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
      <p className="break-words font-semibold">{t("admin.broadcasts.item_title", { id: broadcast.id })}</p>
      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold dark:bg-white/10">{t(statusKey(broadcast.status))}</span>
    </div>
    <dl className="mt-4 grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3">
      <Count label={t("admin.broadcasts.sent")} value={broadcast.sent_count} />
      <Count label={t("admin.broadcasts.failed")} value={broadcast.failed_count} />
      <Count label={t("admin.broadcasts.pending")} value={broadcast.pending_count} />
      <Count label={t("admin.broadcasts.sending")} value={broadcast.sending_count} />
      <Count label={t("admin.broadcasts.cancelled")} value={broadcast.cancelled_count} />
    </dl>
    <div className="mt-4 flex flex-wrap gap-2">
      <button className={buttonClass} disabled={refreshing} onClick={onRefresh} type="button">{refreshing ? t("admin.common.loading") : t("admin.common.refresh")}</button>
      {broadcast.status === "sending" && <button className={buttonClass} disabled={cancelling} onClick={onCancel} type="button">{cancelling ? t("admin.common.loading") : t("admin.broadcasts.cancel")}</button>}
    </div>
    {error != null && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{errorCode === "BROADCAST_NOT_FOUND" ? t("admin.broadcasts.not_found") : t("admin.broadcasts.load_error")}</p>}
    {broadcast.launched_at && <p className="mt-3 text-xs text-slate-500">{broadcast.launched_at}</p>}
  </AdminPanel>;
}

function Count({ label, value }: { label: string; value: number }) {
  return <div className="min-w-0 rounded-lg border border-slate-200 p-3 dark:border-white/10"><dt className="break-words text-xs text-slate-500">{label}</dt><dd className="mt-1 text-lg font-semibold">{value}</dd></div>;
}

function emptyDraft(): AdminBroadcastContent {
  return { target: "all", text: "", photo_storage_key: null, photo_file_id: null, button_text: null, button_url: null };
}

function contentPayload(draft: AdminBroadcastContent): AdminBroadcastPreviewIn {
  return {
    target: draft.target,
    text: draft.text,
    photo_storage_key: draft.photo_storage_key,
    photo_file_id: draft.photo_file_id,
    button_text: draft.button_text?.trim() || null,
    button_url: draft.button_url?.trim() || null,
  };
}

function contentFromBroadcast(broadcast: AdminBroadcast): AdminBroadcastContent {
  return {
    target: broadcast.target,
    text: broadcast.text,
    photo_storage_key: broadcast.photo_storage_key,
    photo_file_id: broadcast.photo_file_id,
    button_text: broadcast.button_text,
    button_url: broadcast.button_url,
  };
}

function validContent(draft: AdminBroadcastContent): boolean {
  const hasButtonText = Boolean(draft.button_text?.trim());
  const hasButtonUrl = Boolean(draft.button_url?.trim());
  return Boolean(draft.text.trim()) && hasButtonText === hasButtonUrl && (!draft.button_url || /^https:\/\//i.test(draft.button_url));
}

function positiveId(value: string): number | null {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function statusKey(status: AdminBroadcast["status"]): TranslationKey {
  return `admin.broadcasts.status.${status}` as TranslationKey;
}

function isPreviewConflict(code: string | null): boolean {
  return code === "BROADCAST_AUDIENCE_CHANGED" || code === "BROADCAST_PREVIEW_CHANGED";
}

function isUnknownOutcome(error: unknown): boolean {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return status === undefined || status >= 500;
}
