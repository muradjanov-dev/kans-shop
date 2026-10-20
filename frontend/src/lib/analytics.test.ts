import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  ENGAGED_INPUT_MS,
  SESSION_IDLE_MS,
  StorefrontAnalytics,
  productIdFromPath,
  type AnalyticsBatch,
} from "@/lib/analytics";

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string) {
    return this.values.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

function place(element: HTMLElement, top: number, height: number) {
  element.getBoundingClientRect = () => ({
    top,
    bottom: top + height,
    height,
    width: 300,
    left: 0,
    right: 300,
    x: 0,
    y: top,
    toJSON: () => ({}),
  });
}

describe("StorefrontAnalytics", () => {
  let clock = 1_700_000_000_000;
  let batches: AnalyticsBatch[];
  let accept: boolean;
  let storage: MemoryStorage;

  const make = () =>
    new StorefrontAnalytics({
      now: () => clock,
      storage,
      transport: {
        send: async (batch) => {
          batches.push(batch);
          return accept;
        },
      },
    });
  const sent = () => batches.flatMap((batch) => batch.events);

  beforeEach(() => {
    clock = 1_700_000_000_000;
    batches = [];
    accept = true;
    storage = new MemoryStorage();
    document.body.innerHTML = "";
    window.history.replaceState(null, "", "/");
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("reports pages, product views and the checkout start", async () => {
    const tracker = make();
    tracker.pageView("/");
    tracker.pageView("/");
    tracker.pageView("/product/42");
    tracker.pageView("/checkout");
    await tracker.flush();

    expect(sent().map((event) => [event.type, event.path, event.product_id])).toEqual([
      ["page_view", "/", undefined],
      ["page_view", "/product/42", 42],
      ["product_view", "/product/42", 42],
      ["page_view", "/checkout", undefined],
      ["checkout_start", "/checkout", undefined],
    ]);
    expect(productIdFromPath("/product/7/reviews")).toBe(7);
    expect(productIdFromPath("/products")).toBeUndefined();
  });

  it("counts engaged time per page and per visible section, and stops when idle", async () => {
    document.body.innerHTML = `
      <section data-track-section="hero"></section>
      <section data-track-section="products"></section>
      <section data-track-section="footer"></section>`;
    const [hero, products, footer] = Array.from(document.querySelectorAll<HTMLElement>("section"));
    place(hero!, 0, 400);
    place(products!, 400, 3000);
    place(footer!, 3400, 200);
    const tracker = make();
    tracker.pageView("/");

    for (let second = 0; second < 5; second += 1) {
      clock += 1000;
      tracker.tick();
    }
    clock += ENGAGED_INPUT_MS; // nobody touched the page: idle time is not engagement
    tracker.tick();
    await tracker.flush();

    const events = sent();
    const views = events.filter((event) => event.type === "section_view");
    expect(views.map((event) => [event.section, event.value])).toEqual([
      ["hero", 0],
      ["products", 1],
    ]);
    const pageTime = events.find((event) => event.type === "page_time");
    expect(pageTime?.value).toBe(5000);
    const sectionTimes = Object.fromEntries(
      events.filter((event) => event.type === "section_time").map((event) => [event.section, event.value]),
    );
    expect(sectionTimes).toEqual({ hero: 5000, products: 5000 });
  });

  it("records each product card impression once, but not the carousel or the open product", async () => {
    document.body.innerHTML = `
      <section data-track-section="hero"><div data-track-product="1"></div></section>
      <article data-track-product="2"></article>
      <article data-track-product="3"></article>`;
    const [carousel, seen, below] = Array.from(document.querySelectorAll<HTMLElement>("[data-track-product]"));
    place(carousel!, 0, 300);
    place(seen!, 300, 300);
    place(below!, 900, 300);
    const tracker = make();
    tracker.pageView("/");
    clock += 1000;
    tracker.tick();
    clock += 1000;
    tracker.tick();
    await tracker.flush();

    expect(sent().filter((event) => event.type === "product_impression").map((event) => event.product_id)).toEqual([2]);
  });

  it("describes clicks by purpose and never reads form values", async () => {
    document.body.innerHTML = `
      <header data-track-area="header"><a href="/cart">Savat (3)</a></header>
      <section data-track-section="products">
        <article data-track-product="9"><button data-track="card_add" aria-label="Savatga qo'shish">+</button></article>
      </section>
      <section data-track-section="hero"><button data-track="carousel_next">›</button></section>
      <input id="phone" value="+998901234567" />
      <div data-track-ignore><button>Secret</button></div>`;
    const tracker = make();
    tracker.start();
    tracker.pageView("/");
    // jsdom cannot navigate; the tracker listens in the capture phase, before this.
    const stay = (event: Event) => event.preventDefault();
    document.addEventListener("click", stay);
    document.querySelector<HTMLAnchorElement>("a")!.click();
    document.querySelector<HTMLButtonElement>("[data-track='card_add']")!.click();
    document.querySelector<HTMLButtonElement>("[data-track='carousel_next']")!.click();
    document.querySelector<HTMLInputElement>("#phone")!.click();
    document.querySelector<HTMLButtonElement>("[data-track-ignore] button")!.click();
    document.removeEventListener("click", stay);
    await tracker.flush();
    tracker.stop();

    const clicks = sent().filter((event) => event.type === "click" || event.type === "carousel");
    expect(clicks.map(({ type, section, target, label, product_id }) => ({ type, section, target, label, product_id }))).toEqual([
      { type: "click", section: "header", target: "link:/cart", label: "Savat (3)", product_id: undefined },
      { type: "click", section: "products", target: "card_add", label: "Savatga qo'shish", product_id: 9 },
      { type: "carousel", section: "hero", target: "next", label: undefined, product_id: undefined },
    ]);
    expect(JSON.stringify(batches)).not.toContain("998901234567");
  });

  it("ignores the admin panel", async () => {
    document.body.innerHTML = `<button data-track="danger">Delete</button>`;
    const tracker = make();
    tracker.start();
    tracker.pageView("/");
    await tracker.flush();
    batches = [];
    window.history.replaceState(null, "", "/admin/orders");
    document.querySelector("button")!.click();
    await tracker.flush();
    tracker.stop();

    expect(sent()).toEqual([]);
  });

  it("keeps the visitor, renews the session after 30 idle minutes and retries failed batches", async () => {
    const tracker = make();
    tracker.pageView("/");
    accept = false;
    await tracker.flush();
    accept = true;
    await tracker.flush();

    expect(batches).toHaveLength(2);
    expect(batches[1]!.events.map((event) => event.type)).toEqual(["page_view"]);
    const first = batches[1]!;
    expect(first.visitor_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(first.platform).toBe("web");

    clock += SESSION_IDLE_MS + 1000;
    tracker.track({ type: "click", target: "later" });
    await tracker.flush();
    const later = batches.at(-1)!;
    expect(later.visitor_id).toBe(first.visitor_id);
    expect(later.session_id).not.toBe(first.session_id);

    const reopened = make();
    reopened.track({ type: "click", target: "again" });
    await reopened.flush();
    expect(batches.at(-1)!.visitor_id).toBe(first.visitor_id);
    expect(batches.at(-1)!.session_id).toBe(later.session_id);
  });

  it("reports the deepest scroll once per page view", async () => {
    Object.defineProperty(document.documentElement, "scrollHeight", { configurable: true, value: 4000 });
    const tracker = make();
    tracker.pageView("/");
    Object.defineProperty(window, "scrollY", { configurable: true, value: 2200 });
    clock += 1000;
    tracker.tick();
    tracker.pageView("/cart");
    await tracker.flush();

    const scroll = sent().filter((event) => event.type === "scroll_depth");
    expect(scroll).toHaveLength(1);
    expect(scroll[0]).toMatchObject({ path: "/", target: "pv1", value: 75 });
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
  });
});
