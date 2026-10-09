import { expect, test as purchaseTest, type ApiExtensionHandler, type PurchaseApiFixture } from "./purchaseApi";
import type { FixtureProduct } from "./purchaseApi";

export { expect };

type Language = "uz" | "ru";

export interface SyntheticAddress {
  id: number;
  label: string;
  address_text: string;
  address_comment: string | null;
  is_default: boolean;
}

interface SyntheticProfile {
  display_name: string;
  phone: string | null;
  language: Language;
}

interface SyntheticSupportSettings {
  support_username: string | null;
  shop_phone: string | null;
  work_hours: string | null;
  welcome_text_uz: string | null;
  welcome_text_ru: string | null;
}

const SVG_IMAGE_ONE = `data:image/svg+xml;base64,${Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240"><rect width="240" height="240" fill="#eeeafb"/><rect x="108" y="38" width="24" height="164" rx="12" fill="#7655dc"/><text x="120" y="226" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#40316e">Synthetic 1</text></svg>',
).toString("base64")}`;
const SVG_IMAGE_TWO = `data:image/svg+xml;base64,${Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240"><rect width="240" height="240" fill="#e9f3f2"/><rect x="104" y="42" width="32" height="154" rx="16" fill="#3b837c"/><text x="120" y="226" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#244d49">Synthetic 2</text></svg>',
).toString("base64")}`;

const syntheticProfile = (userId: number): SyntheticProfile => ({
  display_name: `Synthetic Buyer ${userId}`,
  phone: null,
  language: "uz",
});

function json(status: number, value: unknown) {
  return { status, json: value };
}

function unauthorized() {
  return json(401, { error: { code: "UNAUTHORIZED", message: "Synthetic login required", details: {} } });
}

function notFound() {
  return json(404, { error: { code: "NOT_FOUND", message: "Synthetic record not found", details: {} } });
}

function pageOf<T>(items: T[], page: number, limit: number) {
  const start = (page - 1) * limit;
  return {
    items: items.slice(start, start + limit),
    total: items.length,
    page,
    limit,
    total_pages: Math.max(1, Math.ceil(items.length / limit)),
  };
}

/**
 * Synthetic customer fixtures layered on the purchase fixture's request interceptor.
 * All values below exist only for browser acceptance tests; this fixture never contacts
 * a live API, Telegram account, customer record or order.
 */
export class StorefrontApiFixture {
  readonly product: FixtureProduct;
  private readonly profiles = new Map<number, SyntheticProfile>();
  private readonly addresses = new Map<number, SyntheticAddress[]>();
  private readonly favorites = new Map<number, Set<number>>();
  private readonly timelines = new Map<number, { ownerId: number; events: Array<{ status: string; occurred_at: string }> }>();
  private nextAddressId = 900;
  private supportSettings: SyntheticSupportSettings = {
    support_username: null,
    shop_phone: null,
    work_hours: null,
    welcome_text_uz: null,
    welcome_text_ru: null,
  };

  constructor(readonly purchaseApi: PurchaseApiFixture) {
    const product = purchaseApi.products[0];
    if (!product) throw new Error("The purchase fixture must provide a synthetic product.");
    product.name_uz = "Sinov mahsuloti — ruchka";
    product.name_ru = "Тестовый товар — ручка";
    product.description_uz = "Faqat avtomatlashtirilgan qabul testi uchun sun’iy mahsulot.";
    product.description_ru = "Синтетический товар только для автоматизированной приёмки.";
    product.sku = "SYNTH-001";
    product.price = "5000.00";
    product.old_price = null;
    product.stock_qty = 20;
    product.min_order_qty = 1;
    product.is_featured = false;
    product.images = [
      { id: 901, url: SVG_IMAGE_ONE, telegram_file_id: null, is_main: true, sort_order: 0 },
      { id: 902, url: SVG_IMAGE_TWO, telegram_file_id: null, is_main: false, sort_order: 1 },
    ];
    this.product = product;

    const category = purchaseApi.categories[0];
    if (category) {
      category.name_uz = "Sinov kategoriyasi";
      category.name_ru = "Тестовая категория";
      category.image_url = null;
    }

    purchaseApi.setApiExtension(this.handleRequest);
  }

  seedAddress(userId: number, address: Omit<SyntheticAddress, "id"> & { id?: number }): SyntheticAddress {
    const seeded = { ...address, id: address.id ?? this.nextAddressId++ };
    this.addresses.set(userId, [...(this.addresses.get(userId) ?? []), seeded]);
    return structuredClone(seeded);
  }

  seedFavorite(userId: number, productId = this.product.id): void {
    const saved = this.favorites.get(userId) ?? new Set<number>();
    saved.add(productId);
    this.favorites.set(userId, saved);
  }

  favoriteIdsFor(userId: number): number[] {
    return [...(this.favorites.get(userId) ?? [])].sort((left, right) => left - right);
  }

  seedTimeline(
    orderId: number,
    ownerId: number,
    events: Array<{ status: string; occurred_at: string }>,
  ): void {
    this.timelines.set(orderId, { ownerId, events: structuredClone(events) });
  }

  setConfiguredSupport(): void {
    this.supportSettings = {
      support_username: "synthetic_test_support",
      shop_phone: null,
      work_hours: null,
      welcome_text_uz: null,
      welcome_text_ru: null,
    };
  }

  setSupportSettings(settings: Partial<SyntheticSupportSettings>): void {
    this.supportSettings = { ...this.supportSettings, ...settings };
  }

  private readonly handleRequest: ApiExtensionHandler = (request) => {
    const url = new URL(request.path, "http://fixture.invalid");
    const { pathname } = url;
    const userId = this.purchaseApi.userIdForRequest(request);
    const body = request.body && typeof request.body === "object"
      ? request.body as Record<string, unknown>
      : {};

    if (request.method === "GET" && pathname === "/settings/public") {
      return json(200, {
        delivery_fee: null,
        free_delivery_from: null,
        min_order_amount: null,
        work_hours: this.supportSettings.work_hours,
        card_number: null,
        card_holder: null,
        support_username: this.supportSettings.support_username,
        shop_phone: this.supportSettings.shop_phone,
        is_shop_open: null,
        welcome_text_uz: this.supportSettings.welcome_text_uz,
        welcome_text_ru: this.supportSettings.welcome_text_ru,
        enabled_payment_providers: [],
      });
    }

    if (request.method === "GET" && pathname === "/catalog/featured") {
      return json(200, this.purchaseApi.products.filter((product) => product.is_featured));
    }

    if (pathname === "/profile" && request.method === "GET") {
      if (userId === null) return unauthorized();
      const profile = this.profiles.get(userId) ?? syntheticProfile(userId);
      this.profiles.set(userId, profile);
      return json(200, profile);
    }
    if (pathname === "/profile" && request.method === "PATCH") {
      if (userId === null) return unauthorized();
      const current = this.profiles.get(userId) ?? syntheticProfile(userId);
      const updated: SyntheticProfile = {
        display_name: typeof body.display_name === "string" ? body.display_name : current.display_name,
        phone: typeof body.phone === "string" ? body.phone : body.phone === null ? null : current.phone,
        language: body.language === "ru" ? "ru" : body.language === "uz" ? "uz" : current.language,
      };
      this.profiles.set(userId, updated);
      return json(200, updated);
    }

    if (pathname === "/addresses" && request.method === "GET") {
      if (userId === null) return unauthorized();
      return json(200, structuredClone(this.addresses.get(userId) ?? []));
    }
    if (pathname === "/addresses" && request.method === "POST") {
      if (userId === null) return unauthorized();
      const current = this.addresses.get(userId) ?? [];
      const created: SyntheticAddress = {
        id: this.nextAddressId++,
        label: String(body.label ?? "Synthetic address"),
        address_text: String(body.address_text ?? ""),
        address_comment: typeof body.address_comment === "string" ? body.address_comment : null,
        is_default: current.length === 0,
      };
      this.addresses.set(userId, [...current, created]);
      return json(201, created);
    }

    const addressDefault = /^\/addresses\/(\d+)\/default$/.exec(pathname);
    if (addressDefault && request.method === "PUT") {
      if (userId === null) return unauthorized();
      const addressId = Number(addressDefault[1]);
      const current = this.addresses.get(userId) ?? [];
      if (!current.some((address) => address.id === addressId)) return notFound();
      const updated = current.map((address) => ({ ...address, is_default: address.id === addressId }));
      this.addresses.set(userId, updated);
      return json(200, updated.find((address) => address.id === addressId));
    }

    const address = /^\/addresses\/(\d+)$/.exec(pathname);
    if (address && ["PATCH", "DELETE"].includes(request.method)) {
      if (userId === null) return unauthorized();
      const addressId = Number(address[1]);
      const current = this.addresses.get(userId) ?? [];
      const found = current.find((candidate) => candidate.id === addressId);
      if (!found) return notFound();
      if (request.method === "DELETE") {
        this.addresses.set(userId, current.filter((candidate) => candidate.id !== addressId));
        return { status: 204, body: "" };
      }
      const updated: SyntheticAddress = {
        ...found,
        label: typeof body.label === "string" ? body.label : found.label,
        address_text: typeof body.address_text === "string" ? body.address_text : found.address_text,
        address_comment: typeof body.address_comment === "string" ? body.address_comment : body.address_comment === null ? null : found.address_comment,
      };
      this.addresses.set(userId, current.map((candidate) => candidate.id === addressId ? updated : candidate));
      return json(200, updated);
    }

    const timeline = /^\/orders\/(\d+)\/timeline$/.exec(pathname);
    if (timeline && request.method === "GET") {
      const orderId = Number(timeline[1]);
      const seeded = this.timelines.get(orderId);
      if (!seeded) return undefined;
      if (userId === null || userId !== seeded.ownerId) return notFound();
      return json(200, seeded.events);
    }

    if (pathname === "/favorites" && request.method === "GET") {
      if (userId === null) return unauthorized();
      const pageNumber = Math.max(1, Number(url.searchParams.get("page") ?? 1));
      const limit = Math.max(1, Number(url.searchParams.get("limit") ?? 24));
      const products = [...(this.favorites.get(userId) ?? [])]
        .map((productId) => this.purchaseApi.products.find((productItem) => productItem.id === productId))
        .filter((productItem): productItem is FixtureProduct => Boolean(productItem));
      return json(200, pageOf(products, pageNumber, limit));
    }

    const favorite = /^\/favorites\/(\d+)$/.exec(pathname);
    if (favorite && request.method === "GET") {
      if (userId === null) return unauthorized();
      return json(200, { is_favorite: this.favorites.get(userId)?.has(Number(favorite[1])) ?? false });
    }
    if (favorite && ["PUT", "DELETE"].includes(request.method)) {
      if (userId === null) return unauthorized();
      const saved = this.favorites.get(userId) ?? new Set<number>();
      const productId = Number(favorite[1]);
      if (request.method === "PUT") saved.add(productId);
      else saved.delete(productId);
      this.favorites.set(userId, saved);
      return { status: 204, body: "" };
    }

    return undefined;
  };
}

export const test = purchaseTest.extend<{ storefrontApi: StorefrontApiFixture }>({
  storefrontApi: async ({ purchaseApi }, use) => {
    const fixture = new StorefrontApiFixture(purchaseApi);
    await use(fixture);
  },
});
