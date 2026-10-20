import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import { adminApi, getAdminApiErrorCode } from "@/admin/api";
import { useTranslate } from "@/lib/i18n";

const IDENTIFIER_STORAGE_KEY = "kans-admin-login-identifier";

type SendState = "idle" | "sending" | "sent" | "error" | "rate_limited";

function readStoredIdentifier(): string {
  try {
    return localStorage.getItem(IDENTIFIER_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function storeIdentifier(value: string | null): void {
  try {
    if (value) localStorage.setItem(IDENTIFIER_STORAGE_KEY, value);
    else localStorage.removeItem(IDENTIFIER_STORAGE_KEY);
  } catch {
    // Private mode or blocked storage: the page still works, it just will not remember.
  }
}

function formatRemaining(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function AdminLoginPage() {
  const { login, loginErrorCode, clearLoginError, notice, retrySessionCheck } = useAdminAuth();
  const t = useTranslate();
  const [identifier, setIdentifier] = useState(readStoredIdentifier);
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [sendState, setSendState] = useState<SendState>("idle");
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const codeInput = useRef<HTMLInputElement>(null);
  const autoSent = useRef(false);

  const sendCode = useCallback(async (value: string) => {
    const normalized = value.trim();
    if (normalized.length < 2) return;
    setSendState("sending");
    clearLoginError();
    try {
      const result = await adminApi.requestCode(normalized);
      storeIdentifier(normalized);
      setExpiresAt(Date.now() + result.expires_in * 1000);
      setNow(Date.now());
      setCode("");
      setSendState("sent");
      codeInput.current?.focus();
    } catch (error) {
      setSendState(getAdminApiErrorCode(error) === "RATE_LIMITED" ? "rate_limited" : "error");
    }
  }, [clearLoginError]);

  // A remembered admin gets a fresh code as soon as the login page opens: one less step.
  useEffect(() => {
    if (autoSent.current) return;
    autoSent.current = true;
    const remembered = readStoredIdentifier();
    if (remembered) void sendCode(remembered);
  }, [sendCode]);

  useEffect(() => {
    if (expiresAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [expiresAt]);

  const remaining = expiresAt === null ? null : expiresAt - now;
  const expired = remaining !== null && remaining <= 0;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = code.trim();
    if (!/^[0-9]{6}$/.test(normalized)) return;
    setPending(true);
    try {
      await login(normalized);
    } catch {
      // The provider keeps an accessible error code for the login form.
    } finally {
      setPending(false);
    }
  }

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText("/admin_login");
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function retrySession() {
    setRetrying(true);
    await retrySessionCheck();
    setRetrying(false);
  }

  function changeAccount() {
    storeIdentifier(null);
    setIdentifier("");
    setExpiresAt(null);
    setSendState("idle");
  }

  const loginError = loginErrorCode === "INVALID_OR_EXPIRED_CODE"
    ? t("admin.invalid_code")
    : loginErrorCode === "RATE_LIMITED"
      ? t("admin.rate_limited")
      : loginErrorCode
        ? t("admin.login_error")
        : null;

  return (
    <main className="flex min-h-screen w-full items-center justify-center p-4 sm:p-6">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-white/10 dark:bg-slate-950 sm:p-7" aria-labelledby="admin-login-title">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600">Kans Shop</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white" id="admin-login-title">{t("admin.login_title")}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{t("admin.login.instructions")}</p>

        <form
          className="mt-5 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void sendCode(identifier);
          }}
        >
          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200" htmlFor="admin-identifier">
            {t("admin.login.identifier_label")}
            <input
              autoComplete="username"
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-white/15 dark:bg-slate-900 dark:text-white"
              disabled={sendState === "sending"}
              id="admin-identifier"
              maxLength={64}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="917456291 / @username"
              value={identifier}
            />
          </label>
          {sendState !== "sent" && (
            <button className="min-h-11 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={sendState === "sending" || identifier.trim().length < 2} type="submit">
              {sendState === "sending" ? t("admin.login.sending") : t("admin.login.send_code")}
            </button>
          )}
        </form>

        <div aria-live="polite" className="mt-3 text-sm">
          {sendState === "sent" && !expired && remaining !== null && (
            <p className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-emerald-50 p-3 text-emerald-900 dark:bg-emerald-300/10 dark:text-emerald-100" role="status">
              <span>{t("admin.login.code_sent")}</span>
              <span className="font-semibold tabular-nums">{t("admin.login.expires_in", { time: formatRemaining(remaining) })}</span>
            </p>
          )}
          {sendState === "sent" && expired && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-amber-50 p-3 text-amber-900 dark:bg-amber-300/10 dark:text-amber-100" role="alert">
              <span>{t("admin.login.expired")}</span>
              <button className="min-h-11 rounded-lg bg-indigo-600 px-3 py-2 font-semibold text-white hover:bg-indigo-700" onClick={() => void sendCode(identifier)} type="button">
                {t("admin.login.resend")}
              </button>
            </div>
          )}
          {sendState === "error" && <p className="rounded-lg bg-red-50 p-3 text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{t("admin.login.request_error")}</p>}
          {sendState === "rate_limited" && <p className="rounded-lg bg-red-50 p-3 text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{t("admin.rate_limited")}</p>}
          {sendState === "sent" && (
            <button className="mt-2 min-h-11 text-sm font-medium text-indigo-700 underline underline-offset-2 dark:text-indigo-300" onClick={changeAccount} type="button">
              {t("admin.login.change_account")}
            </button>
          )}
        </div>

        <form className="mt-4 flex flex-col gap-3" onSubmit={(event) => void submit(event)}>
          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200" htmlFor="admin-code">
            {t("admin.code_label")}
            <input
              autoComplete="one-time-code"
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base tracking-[0.3em] text-slate-900 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-white/15 dark:bg-slate-900 dark:text-white"
              disabled={pending}
              id="admin-code"
              inputMode="numeric"
              maxLength={6}
              onChange={(event) => {
                setCode(event.target.value.replace(/\D/g, ""));
                clearLoginError();
              }}
              pattern="[0-9]{6}"
              ref={codeInput}
              value={code}
            />
          </label>
          {notice === "session-expired" && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-300/10 dark:text-amber-100" role="alert">{t("admin.session_expired")}</p>}
          {notice === "unavailable" && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">
              <span>{t("admin.session_unavailable")}</span>
              <button className="underline underline-offset-2" disabled={retrying} onClick={() => void retrySession()} type="button">{retrying ? t("admin.checking") : t("common.retry")}</button>
            </div>
          )}
          {loginError && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-300/10 dark:text-red-100" role="alert">{loginError}</p>}
          <button className="min-h-11 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={pending || code.length !== 6} type="submit">
            {pending ? t("admin.signing_in") : t("admin.login")}
          </button>
        </form>

        <div className="mt-5 border-t border-slate-100 pt-4 dark:border-white/10">
          <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">{t("admin.login.manual_hint")}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <a className="inline-flex min-h-11 items-center rounded-lg border border-indigo-200 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 dark:border-indigo-300/30 dark:text-indigo-200 dark:hover:bg-indigo-300/10" href="https://t.me/kansshopbot" rel="noreferrer" target="_blank">
              {t("admin.open_bot")}
            </a>
            <code className="rounded bg-slate-50 px-2 py-1.5 text-sm text-slate-800 dark:bg-white/5 dark:text-slate-100">/admin_login</code>
            <button className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 dark:border-white/15 dark:text-slate-200" onClick={() => void copyCommand()} type="button">
              {copied ? t("admin.copied") : t("admin.copy_command")}
            </button>
          </div>
          <p aria-live="polite" className="sr-only">{copied ? t("admin.copied") : ""}</p>
        </div>
      </section>
    </main>
  );
}
