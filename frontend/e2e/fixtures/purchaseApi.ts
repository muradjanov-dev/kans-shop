import { Buffer } from "node:buffer";
import { expect, test as baseTest, type Page, type Route } from "@playwright/test";
export { expect };

const TELEGRAM_BRIDGE_URL = "https://telegram.org/js/telegram-web-app.js";

export interface FixtureProduct {
  id: number;
  category_id: number;
  name_uz: string;
  name_ru: string;
  description_uz: string | null;
  description_ru: string | null;
  sku: string;
  price: string;
  old_price: string | null;
  stock_qty: number;
  unit: "dona";
  min_order_qty: number;
  is_active: boolean;
  is_featured: boolean;
  lot_url: string | null;
  views_count: number;
  sold_count: number;
  edit_version: number;
  images: Array<{
    id: number;
    url: string | null;
    telegram_file_id: string | null;
    is_main: boolean;
    sort_order: number;
  }>;
}

export interface CatalogPage<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface CapturedApiRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}

export interface FixtureReply {
  status?: number;
  json?: unknown;
  body?: string | Buffer;
  contentType?: string;
}

export type ApiExtensionHandler = (
  request: CapturedApiRequest,
) => FixtureReply | undefined | Promise<FixtureReply | undefined>;

interface FixtureCartItem {
  id: number;
  product_id: number;
  quantity: number;
  price_snapshot: string;
  product: FixtureProduct;
}

interface FixtureCart {
  items: FixtureCartItem[];
  subtotal: string;
  items_count: number;
}

interface FixtureOrder {
  id: number;
  order_number: string;
  status: "new";
  order_type: "delivery" | "pickup" | "preorder";
  customer_name: string;
  customer_phone: string;
  address: string | null;
  address_comment: string | null;
  comment: string | null;
  subtotal: string;
  delivery_fee: string;
  discount: string;
  total: string;
  payment_method: "cash" | "card_transfer";
  payment_status: "pending" | "receipt_uploaded" | "paid";
  payment_instructions: { card_number: string; card_holder: string } | null;
  receipt_version: number;
  has_receipt: boolean;
  receipt_url: null;
  cancel_reason: null;
  created_at: string;
  confirmed_at: null;
  completed_at: null;
  items: Array<{
    id: number;
    product_id: number;
    product_name_snapshot: string;
    product_sku_snapshot: string;
    price: string;
    quantity: number;
    total: string;
  }>;
}

interface TelegramSession {
  initData: string;
  user: { id: number; first_name: string; language_code: "uz" | "ru" };
}

const product: FixtureProduct = {
  id: 2,
  category_id: 1,
  name_uz: "Ruchka",
  name_ru: "Ручка",
  description_uz: "Ko‘k siyohli ruchka",
  description_ru: "Ручка с синими чернилами",
  sku: "PEN-002",
  price: "5000.00",
  old_price: null,
  stock_qty: 20,
  unit: "dona",
  min_order_qty: 1,
  is_active: true,
  is_featured: true,
  lot_url: null,
  views_count: 0,
  sold_count: 0,
  edit_version: 0,
  images: [],
};

const category = {
  id: 1,
  parent_id: null,
  name_uz: "Yozuv qurollari",
  name_ru: "Письменные принадлежности",
  slug: "stationery",
  description_uz: null,
  description_ru: null,
  image_url: null,
  sort_order: 0,
  edit_version: 0,
  is_active: true,
  products_count: 1,
};

function pageOf<T>(items: T[], page = 1, limit = 12): CatalogPage<T> {
  return {
    items,
    total: items.length,
    page,
    limit,
    total_pages: items.length ? 1 : 0,
  };
}

function emptyCart(): FixtureCart {
  return { items: [], subtotal: "0.00", items_count: 0 };
}

function cartOf(items: FixtureCartItem[]): FixtureCart {
  const subtotal = items.reduce(
    (sum, item) => sum + Number(item.product.price) * item.quantity,
    0,
  );
  return {
    items: structuredClone(items),
    subtotal: subtotal.toFixed(2),
    items_count: items.reduce((sum, item) => sum + item.quantity, 0),
  };
}

function accessToken(userId: number): string {
  const payload = Buffer.from(
    JSON.stringify({ sub: String(userId), telegram_id: 8_000_000_000_000_000 + userId }),
  ).toString("base64url");
  return `synthetic.${payload}.synthetic`;
}

function tokenPair(userId: number) {
  return {
    access_token: accessToken(userId),
    refresh_token: `synthetic-refresh-${userId}`,
    token_type: "bearer",
    is_admin: false,
  };
}

function jsonBody(route: Route): unknown {
  try {
    return route.request().postDataJSON();
  } catch {
    return undefined;
  }
}

function errorReply(code: string, message: string, status: number): FixtureReply {
  return { status, json: { error: { code, message, details: {} } } };
}

/**
 * Browser-only purchase API fixture. It returns complete Page<T> envelopes for both the
 * established catalog routes and the newer `/catalog/products?q=&category_id=` contract.
 * All routes are synthetic: only the dedicated backend HTTP journey exercises PostgreSQL.
 */
export class PurchaseApiFixture {
  readonly requests: CapturedApiRequest[] = [];
  readonly unexpectedExternalRequests: string[] = [];
  readonly unhandledApiRequests: string[] = [];
  readonly products = [structuredClone(product)];
  readonly categories = [structuredClone(category)];
  telegramBridgeRequests = 0;
  failNextAddAfterCommit = false;
  failNextCheckoutAfterCommit = false;
  changeQuoteOnNextCheckout = false;
  requireClientUpdateOnNextCheckout = false;

  private readonly origin: string;
  private telegramSession: TelegramSession | null = null;
  private extension: ApiExtensionHandler | null = null;
  private readonly carts = new Map<number, FixtureCart>();
  private readonly ordersByUser = new Map<number, FixtureOrder[]>();
  private readonly ordersById = new Map<number, FixtureOrder>();
  private readonly addMutations = new Map<string, FixtureCart>();
  private readonly ordersByCheckoutKey = new Map<string, FixtureOrder>();
  private quoteRevision = 1;
  private nextOrderId = 100;

  constructor(private readonly page: Page, baseURL: string) {
    this.origin = new URL(baseURL).origin;
  }

  setTelegramSession(user: TelegramSession | null): void {
    this.telegramSession = user ? structuredClone(user) : null;
  }

  setApiExtension(handler: ApiExtensionHandler | null): void {
    this.extension = handler;
  }

  seedCart(userId: number, item: { quantity: number } | null): void {
    this.carts.set(userId, item
      ? cartOf([{
          id: 20 + userId,
          product_id: product.id,
          quantity: item.quantity,
          price_snapshot: product.price,
          product: structuredClone(product),
        }])
      : emptyCart());
  }

  seedOrder(
    userId: number,
    order: Partial<Pick<FixtureOrder, "id" | "order_number" | "payment_method">> = {},
  ): FixtureOrder {
    const seeded = this.makeOrder(userId, {
      order_type: "pickup",
      customer_name: "Existing Buyer",
      customer_phone: "+998901234567",
      payment_method: "cash",
      expected_total: "5000.00",
    }, order.id ?? this.nextOrderId++, order.order_number ?? "KANS-EXISTING-0001");
    if (order.payment_method) seeded.payment_method = order.payment_method;
    this.ordersById.set(seeded.id, seeded);
    this.ordersByUser.set(userId, [...(this.ordersByUser.get(userId) ?? []), seeded]);
    return structuredClone(seeded);
  }

  requestsFor(method: string, path: string): CapturedApiRequest[] {
    return this.requests.filter(
      (request) => request.method === method.toUpperCase() && request.path === path,
    );
  }

  userIdForRequest(request: CapturedApiRequest): number | null {
    return this.userIdFromRequest(request.headers.authorization);
  }

  get capturedAddKeys(): string[] {
    return this.requestsFor("POST", "/cart/items")
      .map((request) => request.headers["idempotency-key"] ?? "");
  }

  get capturedCheckoutRequests(): CapturedApiRequest[] {
    return this.requestsFor("POST", "/orders");
  }

  async install(): Promise<void> {
    await this.page.context().route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.href === TELEGRAM_BRIDGE_URL) {
        this.telegramBridgeRequests += 1;
        const session = this.telegramSession;
        const app = session
          ? { initData: session.initData, initDataUnsafe: { user: session.user }, ready() {}, expand() {} }
          : { initData: "", initDataUnsafe: {}, ready() {}, expand() {} };
        await route.fulfill({
          status: 200,
          contentType: "application/javascript",
          body: `window.Telegram = { WebApp: ${JSON.stringify(app)} };`,
        });
        return;
      }

      if (url.origin !== this.origin) {
        this.unexpectedExternalRequests.push(url.href);
        await route.abort("blockedbyclient");
        return;
      }

      if (url.pathname.startsWith("/api/v1/")) {
        await this.handleApi(route, url);
        return;
      }

      await route.continue();
    });
  }

  private async handleApi(route: Route, url: URL): Promise<void> {
    const request = route.request();
    const headers = await request.allHeaders();
    const captured: CapturedApiRequest = {
      method: request.method().toUpperCase(),
      path: `${url.pathname.replace(/^\/api\/v1/, "")}${url.search}`,
      headers,
      body: jsonBody(route),
    };
    this.requests.push(captured);

    const extensionReply = await this.extension?.(captured);
    if (extensionReply) {
      await this.fulfill(route, extensionReply);
      return;
    }

    const path = url.pathname.replace(/^\/api\/v1/, "");
    const userId = this.userIdFromRequest(headers.authorization);
    const method = captured.method;
    const body = captured.body as Record<string, unknown> | undefined;

    if (method === "GET" && path === "/catalog/categories") {
      await this.fulfill(route, { json: this.categories });
      return;
    }
    if (method === "GET" && path === "/catalog/featured") {
      await this.fulfill(route, { json: this.products });
      return;
    }
    if (method === "GET" && path === "/catalog/search") {
      await this.fulfill(route, { json: this.productPage(url.searchParams.get("q"), null, url) });
      return;
    }
    if (method === "GET" && path === "/catalog/products") {
      await this.fulfill(route, {
        json: this.productPage(url.searchParams.get("q"), url.searchParams.get("category_id"), url),
      });
      return;
    }
    const categoryProducts = /^\/catalog\/categories\/(\d+)\/products$/.exec(path);
    if (method === "GET" && categoryProducts) {
      await this.fulfill(route, {
        json: this.productPage(null, categoryProducts[1] ?? null, url),
      });
      return;
    }
    const productDetail = /^\/catalog\/products\/(\d+)$/.exec(path);
    if (method === "GET" && productDetail) {
      const found = this.products.find((candidate) => candidate.id === Number(productDetail[1]));
      await this.fulfill(route, found
        ? { json: found }
        : errorReply("NOT_FOUND", "Product not found", 404));
      return;
    }
    if (method === "GET" && path === "/settings/public") {
      await this.fulfill(route, { json: this.publicSettings() });
      return;
    }
    if (method === "POST" && path === "/auth/telegram") {
      await this.fulfill(route, { json: tokenPair(42) });
      return;
    }
    if (method === "POST" && path === "/auth/customer/code") {
      const code = body?.code;
      const accountId = code === "87654321" ? 99 : 42;
      await this.fulfill(route, { json: tokenPair(accountId) });
      return;
    }
    if (method === "POST" && path === "/auth/refresh") {
      const token = String(body?.refresh_token ?? "");
      const id = Number(token.split("-").at(-1)) || 42;
      await this.fulfill(route, { json: tokenPair(id) });
      return;
    }
    if (method === "GET" && path === "/cart") {
      if (userId === null) {
        await this.fulfill(route, errorReply("UNAUTHORIZED", "Login required", 401));
        return;
      }
      await this.fulfill(route, { json: this.cartFor(userId) });
      return;
    }
    if (method === "POST" && path === "/cart/items") {
      if (userId === null || !body) {
        await this.fulfill(route, errorReply("UNAUTHORIZED", "Login required", 401));
        return;
      }
      const mutationKey = headers["idempotency-key"] ?? "";
      const mutationId = `${userId}:${mutationKey}`;
      const prior = this.addMutations.get(mutationId);
      if (prior) {
        await this.fulfill(route, { status: 201, json: prior });
        return;
      }
      const productId = Number(body.product_id);
      const quantity = Number(body.quantity);
      const current = this.cartFor(userId);
      const existing = current.items.find((item) => item.product_id === productId);
      const nextItems = existing
        ? current.items.map((item) => item.product_id === productId
          ? { ...item, quantity: item.quantity + quantity }
          : item)
        : [...current.items, {
            id: 20 + userId,
            product_id: productId,
            quantity,
            price_snapshot: this.productById(productId)?.price ?? product.price,
            product: structuredClone(this.productById(productId) ?? product),
          }];
      const result = cartOf(nextItems);
      this.carts.set(userId, result);
      this.addMutations.set(mutationId, structuredClone(result));
      if (this.failNextAddAfterCommit) {
        this.failNextAddAfterCommit = false;
        await this.fulfill(route, errorReply("TEMPORARY_FAILURE", "Response was lost", 500));
        return;
      }
      await this.fulfill(route, { status: 201, json: result });
      return;
    }
    if (method === "POST" && path === "/orders/quote") {
      if (userId === null || !body) {
        await this.fulfill(route, errorReply("UNAUTHORIZED", "Login required", 401));
        return;
      }
      await this.fulfill(route, { json: this.quoteFor(userId, body) });
      return;
    }
    if (method === "POST" && path === "/orders") {
      if (userId === null || !body) {
        await this.fulfill(route, errorReply("UNAUTHORIZED", "Login required", 401));
        return;
      }
      if (body.payment_method === "card_transfer" && body.purchase_contract_version === undefined) {
        await this.fulfill(route, errorReply(
          "CLIENT_UPDATE_REQUIRED",
          "Reload the checkout to review the current card payment instructions.",
          409,
        ));
        return;
      }
      if (this.requireClientUpdateOnNextCheckout) {
        this.requireClientUpdateOnNextCheckout = false;
        await this.fulfill(route, errorReply(
          "CLIENT_UPDATE_REQUIRED",
          "Reload the checkout to review the current card payment instructions.",
          409,
        ));
        return;
      }
      const checkoutKey = headers["idempotency-key"] ?? "";
      const key = `${userId}:${checkoutKey}`;
      const prior = this.ordersByCheckoutKey.get(key);
      if (prior) {
        await this.fulfill(route, { status: 200, json: prior });
        return;
      }
      if (this.changeQuoteOnNextCheckout) {
        this.changeQuoteOnNextCheckout = false;
        this.quoteRevision += 1;
        await this.fulfill(route, errorReply("QUOTE_CHANGED", "The cart quote changed.", 409));
        return;
      }
      const created = this.makeOrder(userId, body, this.nextOrderId++);
      this.ordersByCheckoutKey.set(key, structuredClone(created));
      this.ordersById.set(created.id, structuredClone(created));
      this.ordersByUser.set(userId, [...(this.ordersByUser.get(userId) ?? []), created]);
      this.carts.set(userId, emptyCart());
      if (this.failNextCheckoutAfterCommit) {
        this.failNextCheckoutAfterCommit = false;
        await this.fulfill(route, errorReply("TEMPORARY_FAILURE", "Response was lost", 500));
        return;
      }
      await this.fulfill(route, { status: 201, json: created });
      return;
    }
    if (method === "GET" && path === "/orders") {
      await this.fulfill(route, { json: userId === null ? [] : this.ordersByUser.get(userId) ?? [] });
      return;
    }
    const receiptUpload = /^\/orders\/(\d+)\/receipt$/.exec(path);
    if (receiptUpload && method === "POST") {
      const order = this.ordersById.get(Number(receiptUpload[1]));
      if (!order || order === undefined || userId === null) {
        await this.fulfill(route, errorReply("NOT_FOUND", "Order not found", 404));
        return;
      }
      const ownerId = this.orderOwnerId(order.id);
      if (ownerId !== userId) {
        await this.fulfill(route, errorReply("FORBIDDEN", "Not your order", 403));
        return;
      }
      const updated = { ...order, payment_status: "receipt_uploaded" as const, receipt_version: order.receipt_version + 1, has_receipt: true };
      this.updateOrder(updated);
      await this.fulfill(route, { json: updated });
      return;
    }
    const orderReceipt = /^\/orders\/(\d+)\/receipt$/.exec(path);
    if (orderReceipt && method === "GET") {
      const id = Number(orderReceipt[1]);
      const order = this.ordersById.get(id);
      if (!order || userId === null || this.orderOwnerId(id) !== userId || !order.has_receipt) {
        await this.fulfill(route, errorReply("FORBIDDEN", "Receipt access denied", 403));
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        headers: { "cache-control": "private, no-store" },
        body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==", "base64"),
      });
      return;
    }
    const orderDetail = /^\/orders\/(\d+)$/.exec(path);
    if (orderDetail && method === "GET") {
      const id = Number(orderDetail[1]);
      const order = this.ordersById.get(id);
      await this.fulfill(route, order && userId !== null && this.orderOwnerId(id) === userId
        ? { json: order }
        : errorReply("FORBIDDEN", "Not your order", 403));
      return;
    }
    if (method === "GET" && path === "/profile") {
      await this.fulfill(route, {
        json: { display_name: `Buyer ${userId ?? 0}`, phone: null, language: "uz" },
      });
      return;
    }
    if (method === "PATCH" && path === "/profile") {
      await this.fulfill(route, {
        json: { display_name: String(body?.display_name ?? `Buyer ${userId ?? 0}`), phone: body?.phone ?? null, language: body?.language ?? "uz" },
      });
      return;
    }
    if (method === "GET" && path === "/addresses") {
      await this.fulfill(route, { json: [] });
      return;
    }
    if (method === "GET" && path === "/favorites") {
      await this.fulfill(route, { json: pageOf([]) });
      return;
    }
    const favoriteState = /^\/favorites\/(\d+)$/.exec(path);
    if (favoriteState && method === "GET") {
      await this.fulfill(route, { json: { is_favorite: false } });
      return;
    }
    if (favoriteState && (method === "PUT" || method === "DELETE")) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }

    this.unhandledApiRequests.push(`${method} ${captured.path}`);
    await this.fulfill(route, errorReply("UNHANDLED_FIXTURE_ROUTE", "No synthetic response is configured.", 501));
  }

  private productPage(query: string | null, categoryId: string | null, url: URL): CatalogPage<FixtureProduct> {
    const normalizedQuery = query?.trim().toLowerCase() ?? "";
    const items = this.products.filter((candidate) => {
      if (categoryId && Number(categoryId) !== candidate.category_id) return false;
      if (!normalizedQuery) return true;
      return [candidate.name_uz, candidate.name_ru, candidate.sku]
        .some((value) => value.toLowerCase().includes(normalizedQuery));
    });
    return pageOf(items, Number(url.searchParams.get("page") ?? "1"), Number(url.searchParams.get("limit") ?? "12"));
  }

  private publicSettings() {
    return {
      delivery_fee: 0,
      free_delivery_from: 0,
      min_order_amount: 0,
      work_hours: null,
      card_number: "8600 0000 0000 0000",
      card_holder: "TEST MERCHANT",
      support_username: null,
      shop_phone: null,
      is_shop_open: true,
      welcome_text_uz: null,
      welcome_text_ru: null,
      enabled_payment_providers: [],
      checkout_type_readiness: { delivery: true, pickup: true, preorder: true },
      payment_method_readiness: { cash: true, card_transfer: true, click: false, payme: false, paynet: false },
    };
  }

  private quoteFor(userId: number, body: Record<string, unknown>) {
    const cart = this.cartFor(userId);
    const subtotal = cart.subtotal;
    const deliveryFee = body.order_type === "delivery" ? "15000.00" : "0.00";
    const total = (Number(subtotal) + Number(deliveryFee)).toFixed(2);
    return {
      subtotal,
      delivery_fee: deliveryFee,
      total,
      payment_methods: body.order_type === "preorder" ? [] : ["cash", "card_transfer"],
      ready: cart.items.length > 0,
      reasons: cart.items.length > 0 ? [] : ["empty_cart"],
      quote_fingerprint: `synthetic-quote-${this.quoteRevision}-${body.order_type}-${body.payment_method}-${subtotal}-${cart.items.map((item) => `${item.product_id}:${item.quantity}`).join(",")}`,
    };
  }

  private makeOrder(
    userId: number,
    body: Record<string, unknown>,
    id: number,
    orderNumber = `KANS-E2E-${String(id).padStart(6, "0")}`,
  ): FixtureOrder {
    const cart = this.cartFor(userId);
    const orderType = body.order_type === "preorder" ? "preorder" : body.order_type === "pickup" ? "pickup" : "delivery";
    const method = body.payment_method === "card_transfer" ? "card_transfer" : "cash";
    const total = String(body.expected_total ?? cart.subtotal);
    return {
      id,
      order_number: orderNumber,
      status: "new",
      order_type: orderType,
      customer_name: String(body.customer_name ?? "Journey Buyer"),
      customer_phone: String(body.customer_phone ?? "+998901234567"),
      address: typeof body.address === "string" ? body.address : null,
      address_comment: typeof body.address_comment === "string" ? body.address_comment : null,
      comment: typeof body.comment === "string" ? body.comment : null,
      subtotal: cart.subtotal,
      delivery_fee: orderType === "delivery" ? "15000.00" : "0.00",
      discount: "0.00",
      total,
      payment_method: method,
      payment_status: "pending",
      payment_instructions: method === "card_transfer"
        ? { card_number: "8600 0000 0000 0000", card_holder: "TEST MERCHANT" }
        : null,
      receipt_version: 0,
      has_receipt: false,
      receipt_url: null,
      cancel_reason: null,
      created_at: new Date().toISOString(),
      confirmed_at: null,
      completed_at: null,
      items: cart.items.map((item, index) => ({
        id: 500 + index,
        product_id: item.product_id,
        product_name_snapshot: item.product.name_uz,
        product_sku_snapshot: item.product.sku,
        price: item.product.price,
        quantity: item.quantity,
        total: (Number(item.product.price) * item.quantity).toFixed(2),
      })),
    };
  }

  private updateOrder(order: FixtureOrder): void {
    this.ordersById.set(order.id, structuredClone(order));
    for (const [userId, orders] of this.ordersByUser) {
      const index = orders.findIndex((candidate) => candidate.id === order.id);
      if (index >= 0) {
        const next = [...orders];
        next[index] = structuredClone(order);
        this.ordersByUser.set(userId, next);
      }
    }
    for (const [key, existing] of this.ordersByCheckoutKey) {
      if (existing.id === order.id) this.ordersByCheckoutKey.set(key, structuredClone(order));
    }
  }

  private cartFor(userId: number): FixtureCart {
    return structuredClone(this.carts.get(userId) ?? emptyCart());
  }

  private productById(id: number): FixtureProduct | undefined {
    return this.products.find((candidate) => candidate.id === id);
  }

  private orderOwnerId(orderId: number): number | null {
    for (const [userId, orders] of this.ordersByUser) {
      if (orders.some((order) => order.id === orderId)) return userId;
    }
    return null;
  }

  private userIdFromRequest(authorization: string | undefined): number | null {
    const bearer = authorization?.startsWith("Bearer ") ? authorization.slice(7) : null;
    const payload = bearer?.split(".")[1];
    if (!payload) return null;
    try {
      return Number(JSON.parse(Buffer.from(payload, "base64url").toString("utf8")).sub);
    } catch {
      return null;
    }
  }

  private async fulfill(route: Route, reply: FixtureReply): Promise<void> {
    if (reply.json !== undefined) {
      await route.fulfill({
        status: reply.status ?? 200,
        contentType: reply.contentType ?? "application/json",
        body: JSON.stringify(reply.json),
      });
      return;
    }
    await route.fulfill({
      status: reply.status ?? 200,
      contentType: reply.contentType,
      body: reply.body ?? "",
    });
  }
}

export const test = baseTest.extend<{ purchaseApi: PurchaseApiFixture }>({
  purchaseApi: async ({ page }, use, testInfo) => {
    const baseURL = String(testInfo.project.use.baseURL ?? "http://127.0.0.1:5173");
    const fixture = new PurchaseApiFixture(page, baseURL);
    await fixture.install();
    await use(fixture);
  },
});
