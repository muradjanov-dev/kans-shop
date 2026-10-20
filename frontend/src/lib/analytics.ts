/**
 * First-party storefront analytics: what customers look at, for how long, how far they
 * scroll, what they click and which products interest them. Batches go to our own API
 * (`POST /analytics/events`) and feed the admin dashboard; nothing leaves the shop.
 *
 * Privacy: no form values are ever read. Clicks are described by the element's purpose
 * (`data-track`, its label or link path), and the admin panel itself is never tracked.
 *
 * Mark up the page instead of calling code where possible:
 *   data-track-section="hero"   time on screen and reach of a part of a page
 *   data-track-area="header"    names clicks in an always-visible part (no timing)
 *   data-track-product="42"     impressions, and the product behind a click
 *   data-track="hero_cta"       a stable name for a clickable element
 *   data-track-ignore           never record clicks inside this element
 */

import { API_BASE_URL } from "@/lib/api";
import { isTelegramWebApp, telegramStartParam } from "@/lib/telegram";
import { useAuthStore } from "@/store/auth";

export type AnalyticsEventType =
  | "page_view"
  | "page_time"
  | "section_view"
  | "section_time"
  | "scroll_depth"
  | "click"
  | "product_impression"
  | "product_view"
  | "add_to_cart"
  | "favorite_add"
  | "favorite_remove"
  | "search"
  | "filter"
  | "carousel"
  | "checkout_start"
  | "checkout_step"
  | "order_placed";

export interface AnalyticsEventInput {
  type: AnalyticsEventType;
  path?: string;
  section?: string;
  target?: string;
  label?: string;
  product_id?: number;
  value?: number;
}

export interface AnalyticsQueuedEvent extends AnalyticsEventInput {
  at: number;
}

export interface AnalyticsBatch {
  visitor_id: string;
  session_id: string;
  sent_at: number;
  platform: "telegram" | "web";
  device: "mobile" | "tablet" | "desktop";
  language: string | null;
  entry_path: string | null;
  referrer: string | null;
  source: string | null;
  events: AnalyticsQueuedEvent[];
}

export interface AnalyticsTransport {
  /** Resolves true when the batch is done with (stored, or rejected for good). */
  send(batch: AnalyticsBatch, options: { leaving: boolean }): Promise<boolean>;
}

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface AnalyticsOptions {
  transport: AnalyticsTransport;
  now?: () => number;
  storage?: StorageLike | null;
  win?: Window;
}

const VISITOR_KEY = "kans-analytics-visitor";
const SESSION_KEY = "kans-analytics-session";
export const SESSION_IDLE_MS = 30 * 60_000;
export const FLUSH_INTERVAL_MS = 20_000;
export const ENGAGED_INPUT_MS = 45_000;
const TICK_MS = 1000;
const EARLY_FLUSH_EVENTS = 40;
const MAX_BATCH_EVENTS = 100;
const MAX_BUFFERED_EVENTS = 400;
const MIN_TIMING_MS = 500;
const LABEL_LIMIT = 80;

const PRODUCT_PATH = /^\/product\/(\d+)(?:\/|$)/;

function randomId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
  const bytes = new Uint8Array(16);
  if (cryptoApi?.getRandomValues) cryptoApi.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function safeStorage(win: Window): StorageLike | null {
  try {
    const storage = win.localStorage;
    const probe = "kans-analytics-probe";
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}

function cleanText(value: string | null | undefined, limit = LABEL_LIMIT): string | undefined {
  const text = (value ?? "").replace(/\s+/g, " ").trim();
  return text ? text.slice(0, limit) : undefined;
}

export function productIdFromPath(path: string): number | undefined {
  const match = PRODUCT_PATH.exec(path);
  const id = match ? Number(match[1]) : NaN;
  return Number.isSafeInteger(id) && id > 0 ? id : undefined;
}

function deviceKind(win: Window): AnalyticsBatch["device"] {
  const width = Math.min(win.innerWidth || Infinity, win.screen?.width || Infinity);
  let coarse = false;
  try {
    coarse = win.matchMedia?.("(pointer: coarse)").matches ?? false;
  } catch {
    coarse = false;
  }
  if (width < 768) return "mobile";
  if (width < 1100 && coarse) return "tablet";
  return "desktop";
}

function externalReferrer(win: Window): string | null {
  try {
    const referrer = win.document.referrer;
    if (!referrer) return null;
    return new URL(referrer).host === win.location.host ? null : referrer.slice(0, 500);
  } catch {
    return null;
  }
}

function campaignSource(win: Window): string | null {
  try {
    const params = new URLSearchParams(win.location.search);
    const value = telegramStartParam() || params.get("utm_source") || params.get("source") || params.get("ref");
    return value ? value.slice(0, 64) : null;
  } catch {
    return null;
  }
}

interface PageState {
  path: string;
  seq: number;
  productId?: number;
  pendingMs: number;
  maxScroll: number;
  reportedScroll: number;
  seenSections: Set<string>;
  sectionMs: Map<string, number>;
  impressions: Set<number>;
}

/** The tracker. One per tab; the singleton helpers below own it in the browser. */
export class StorefrontAnalytics {
  private readonly transport: AnalyticsTransport;
  private readonly now: () => number;
  private readonly storage: StorageLike | null;
  private readonly win: Window;
  private queue: AnalyticsQueuedEvent[] = [];
  private page: PageState | null = null;
  private pageSeq = 0;
  private sessionId: string | null = null;
  private visitorId: string | null = null;
  private lastActivity = 0;
  private lastInput = 0;
  private lastTick = 0;
  private entryPath: string | null = null;
  private referrer: string | null = null;
  private source: string | null = null;
  private started = false;
  private paused = false;
  private flushing: Promise<void> | null = null;
  private tickTimer: number | null = null;
  private flushTimer: number | null = null;
  private readonly cleanups: Array<() => void> = [];

  constructor(options: AnalyticsOptions) {
    this.transport = options.transport;
    this.now = options.now ?? Date.now;
    this.win = options.win ?? window;
    this.storage = options.storage === undefined ? safeStorage(this.win) : options.storage;
    this.lastTick = this.now();
    this.lastInput = this.lastTick;
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.paused = false;
    const now = this.now();
    this.lastInput = now;
    this.lastTick = now;
    this.referrer = externalReferrer(this.win);
    this.source = campaignSource(this.win);
    const doc = this.win.document;
    const listen = (target: EventTarget, type: string, handler: EventListener, options?: AddEventListenerOptions) => {
      target.addEventListener(type, handler, options);
      this.cleanups.push(() => target.removeEventListener(type, handler, options));
    };
    const markInput = () => {
      this.lastInput = this.now();
    };
    listen(doc, "click", (event) => this.onClick(event), { capture: true, passive: true });
    for (const type of ["pointerdown", "keydown", "touchstart", "wheel"]) {
      listen(this.win, type, markInput, { capture: true, passive: true });
    }
    listen(this.win, "scroll", () => {
      markInput();
      this.measureScroll();
    }, { passive: true });
    listen(doc, "visibilitychange", () => {
      if (doc.visibilityState === "hidden") this.leave();
      else this.lastTick = this.now();
    });
    listen(this.win, "pagehide", () => this.leave());
    this.tickTimer = this.win.setInterval(() => this.tick(), TICK_MS);
    this.flushTimer = this.win.setInterval(() => void this.flush(), FLUSH_INTERVAL_MS);
  }

  stop(): void {
    this.leave();
    for (const cleanup of this.cleanups.splice(0)) cleanup();
    if (this.tickTimer !== null) this.win.clearInterval(this.tickTimer);
    if (this.flushTimer !== null) this.win.clearInterval(this.flushTimer);
    this.tickTimer = null;
    this.flushTimer = null;
    this.started = false;
  }

  /** The storefront went away (route left the shop, or the tab is closing). */
  pause(): void {
    this.endPage();
    this.paused = true;
    void this.flush({ leaving: true });
  }

  resume(): void {
    this.paused = false;
    this.lastTick = this.now();
  }

  pageView(pathname: string): void {
    if (this.paused) this.resume();
    if (this.page?.path === pathname) return;
    this.endPage();
    this.pageSeq += 1;
    const productId = productIdFromPath(pathname);
    this.page = {
      path: pathname,
      seq: this.pageSeq,
      productId,
      pendingMs: 0,
      maxScroll: 0,
      reportedScroll: 0,
      seenSections: new Set(),
      sectionMs: new Map(),
      impressions: new Set(),
    };
    this.entryPath ??= pathname;
    this.lastInput = this.now();
    this.track({ type: "page_view", path: pathname, product_id: productId });
    if (productId) this.track({ type: "product_view", path: pathname, product_id: productId });
    if (pathname === "/checkout") this.track({ type: "checkout_start", path: pathname });
  }

  track(event: AnalyticsEventInput): void {
    if (this.paused) return;
    const now = this.now();
    this.touchSession(now);
    this.queue.push({
      ...event,
      path: event.path ?? this.page?.path,
      label: cleanText(event.label, 160),
      at: now,
    });
    if (this.queue.length > MAX_BUFFERED_EVENTS) this.queue.splice(0, this.queue.length - MAX_BUFFERED_EVENTS);
    if (this.queue.length >= EARLY_FLUSH_EVENTS) void this.flush();
  }

  /** Moves time measured so far into events; called before every send. */
  collect(): void {
    const page = this.page;
    if (!page) return;
    if (page.pendingMs >= MIN_TIMING_MS) {
      this.queue.push({ type: "page_time", path: page.path, product_id: page.productId, value: Math.round(page.pendingMs), at: this.now() });
      page.pendingMs = 0;
    }
    for (const [section, milliseconds] of page.sectionMs) {
      if (milliseconds < MIN_TIMING_MS) continue;
      this.queue.push({ type: "section_time", path: page.path, section, value: Math.round(milliseconds), at: this.now() });
      page.sectionMs.set(section, 0);
    }
  }

  async flush(options: { leaving?: boolean } = {}): Promise<void> {
    const leaving = Boolean(options.leaving);
    if (this.flushing && !leaving) return this.flushing;
    this.collect();
    if (leaving) this.reportScroll();
    if (!this.queue.length) return;
    const events = this.queue.splice(0, MAX_BATCH_EVENTS);
    const batch = this.batch(events);
    const sending = (async () => {
      let done = false;
      try {
        done = await this.transport.send(batch, { leaving });
      } catch {
        done = false;
      }
      // A failed batch goes back to the front of the queue, unless the page is going away.
      if (!done && !leaving) this.queue.unshift(...events.slice(0, Math.max(MAX_BUFFERED_EVENTS - this.queue.length, 0)));
    })();
    const settled: Promise<void> = sending.finally(() => {
      if (this.flushing === settled) this.flushing = null;
    });
    this.flushing = settled;
    return settled;
  }

  /** Visible for tests: one second of the engagement clock. */
  tick(): void {
    const now = this.now();
    const elapsed = Math.min(Math.max(now - this.lastTick, 0), TICK_MS * 2);
    this.lastTick = now;
    const page = this.page;
    if (!page || this.paused || this.isAdminRoute()) return;
    const doc = this.win.document;
    if (doc.visibilityState === "hidden") return;
    this.measureScroll();
    const engaged = now - this.lastInput < ENGAGED_INPUT_MS;
    if (engaged) {
      page.pendingMs += elapsed;
      this.touchSession(now);
    }
    const viewport = this.win.innerHeight || doc.documentElement.clientHeight || 0;
    if (viewport <= 0) return;
    const sections = Array.from(doc.querySelectorAll<HTMLElement>("[data-track-section]"));
    sections.forEach((element, position) => {
      const name = cleanText(element.dataset.trackSection, 48);
      if (!name || !isVisible(element, viewport, 0.5)) return;
      if (!page.seenSections.has(name)) {
        page.seenSections.add(name);
        this.track({ type: "section_view", path: page.path, section: name, value: position });
      }
      if (engaged) page.sectionMs.set(name, (page.sectionMs.get(name) ?? 0) + elapsed);
    });
    for (const element of Array.from(doc.querySelectorAll<HTMLElement>("[data-track-product]"))) {
      const productId = Number(element.dataset.trackProduct);
      if (!Number.isSafeInteger(productId) || productId <= 0 || page.impressions.has(productId)) continue;
      // An impression is a product seen in a list: not the carousel, not its own page.
      if (productId === page.productId || element.closest("[data-track-section='hero']")) continue;
      if (!isVisible(element, viewport, 0.6)) continue;
      page.impressions.add(productId);
      this.track({ type: "product_impression", path: page.path, product_id: productId, section: sectionOf(element) });
    }
  }

  private leave(): void {
    if (this.isAdminRoute()) return;
    void this.flush({ leaving: true });
  }

  private endPage(): void {
    const page = this.page;
    if (!page) return;
    this.collect();
    this.reportScroll();
    this.page = null;
  }

  private reportScroll(): void {
    const page = this.page;
    if (!page || page.maxScroll <= page.reportedScroll) return;
    page.reportedScroll = page.maxScroll;
    // One page view may report several times (tab hidden, then left); the page view number
    // lets the dashboard keep only the deepest report of each.
    this.queue.push({ type: "scroll_depth", path: page.path, target: `pv${page.seq}`, value: page.maxScroll, at: this.now() });
  }

  private measureScroll(): void {
    const page = this.page;
    if (!page) return;
    const doc = this.win.document.documentElement;
    const height = Math.max(doc.scrollHeight, this.win.document.body?.scrollHeight ?? 0);
    if (height <= 0) return;
    const reached = ((this.win.scrollY || doc.scrollTop || 0) + (this.win.innerHeight || doc.clientHeight)) / height;
    page.maxScroll = Math.max(page.maxScroll, Math.min(100, Math.round(reached * 100)));
  }

  private onClick(event: Event): void {
    if (this.paused || this.isAdminRoute()) return;
    const origin = event.target instanceof Element ? event.target : null;
    const element = origin?.closest<HTMLElement>("[data-track],a[href],button,[role='button'],summary");
    if (!element || element.closest("[data-track-ignore]")) return;
    const explicit = element.dataset.track;
    const productId = Number(element.closest<HTMLElement>("[data-track-product]")?.dataset.trackProduct);
    const product_id = Number.isSafeInteger(productId) && productId > 0 ? productId : undefined;
    const section = sectionOf(element);
    if (explicit?.startsWith("carousel_")) {
      this.track({ type: "carousel", target: explicit.slice("carousel_".length), section, product_id });
      return;
    }
    this.track({
      type: "click",
      section,
      target: explicit ?? describeTarget(element),
      label: cleanText(element.dataset.trackLabel ?? element.getAttribute("aria-label") ?? element.textContent),
      product_id,
    });
  }

  private isAdminRoute(): boolean {
    const path = this.win.location.pathname;
    return path === "/admin" || path.startsWith("/admin/");
  }

  private touchSession(now: number): void {
    if (!this.visitorId) {
      this.visitorId = this.storage?.getItem(VISITOR_KEY) ?? null;
      if (!this.visitorId) {
        this.visitorId = randomId();
        this.storage?.setItem(VISITOR_KEY, this.visitorId);
      }
    }
    if (!this.sessionId) {
      try {
        const saved = JSON.parse(this.storage?.getItem(SESSION_KEY) ?? "null") as { id?: unknown; last?: unknown } | null;
        if (typeof saved?.id === "string" && typeof saved.last === "number" && now - saved.last < SESSION_IDLE_MS) {
          this.sessionId = saved.id;
          this.lastActivity = saved.last;
        }
      } catch {
        this.sessionId = null;
      }
    }
    if (!this.sessionId || now - this.lastActivity >= SESSION_IDLE_MS) {
      this.sessionId = randomId();
      this.entryPath = this.page?.path ?? this.entryPath;
    }
    this.lastActivity = now;
    this.storage?.setItem(SESSION_KEY, JSON.stringify({ id: this.sessionId, last: now }));
  }

  private batch(events: AnalyticsQueuedEvent[]): AnalyticsBatch {
    this.touchSession(this.now());
    return {
      visitor_id: this.visitorId!,
      session_id: this.sessionId!,
      sent_at: this.now(),
      platform: isTelegramWebApp() ? "telegram" : "web",
      device: deviceKind(this.win),
      language: this.win.document.documentElement.lang || null,
      entry_path: this.entryPath,
      referrer: this.referrer,
      source: this.source,
      events,
    };
  }
}

/** The page part a click happened in: a timed section, or a fixed area such as the header. */
function sectionOf(element: Element): string | undefined {
  const area = element.closest<HTMLElement>("[data-track-section],[data-track-area]");
  return cleanText(area?.dataset.trackSection ?? area?.dataset.trackArea, 48);
}

function isVisible(element: HTMLElement, viewport: number, share: number): boolean {
  const rect = element.getBoundingClientRect();
  if (rect.height <= 0 || rect.width <= 0) return false;
  const visible = Math.min(rect.bottom, viewport) - Math.max(rect.top, 0);
  return visible > 0 && visible >= Math.min(rect.height * share, viewport * 0.35);
}

function describeTarget(element: HTMLElement): string {
  if (element instanceof HTMLAnchorElement) {
    try {
      const url = new URL(element.href, window.location.href);
      if (url.origin !== window.location.origin) return `external:${url.host}`.slice(0, 96);
      return `link:${url.pathname.replace(/\/\d+(?=\/|$)/g, "/:id")}`.slice(0, 96);
    } catch {
      return "link";
    }
  }
  return element.tagName.toLowerCase() === "summary" ? "summary" : "button";
}

/** Sends a batch to the API; signed-in customers are attributed through their token. */
export function fetchTransport(): AnalyticsTransport {
  return {
    async send(batch, { leaving }) {
      const body = JSON.stringify(batch);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const token = useAuthStore.getState().accessToken;
      if (token) headers.Authorization = `Bearer ${token}`;
      try {
        const response = await fetch(`${API_BASE_URL}/analytics/events`, {
          method: "POST",
          headers,
          body,
          credentials: "omit",
          keepalive: leaving && body.length < 60_000,
        });
        // Retry later when throttled or the server failed; drop batches it refused.
        return response.ok || (response.status < 500 && response.status !== 429);
      } catch {
        return false;
      }
    },
  };
}

let tracker: StorefrontAnalytics | null = null;

/** Starts the browser tracker once (never in unit tests or outside a browser). */
export function startAnalytics(): StorefrontAnalytics | null {
  if (tracker) {
    tracker.resume();
    return tracker;
  }
  if (typeof window === "undefined" || import.meta.env.MODE === "test") return null;
  tracker = new StorefrontAnalytics({ transport: fetchTransport() });
  tracker.start();
  return tracker;
}

export function trackPage(pathname: string): void {
  tracker?.pageView(pathname);
}

export function track(event: AnalyticsEventInput): void {
  tracker?.track(event);
}
