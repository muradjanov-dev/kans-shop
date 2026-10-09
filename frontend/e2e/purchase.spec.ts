import { expect, test } from "./fixtures/purchaseApi";
import type { PurchaseApiFixture } from "./fixtures/purchaseApi";
import type { Page } from "@playwright/test";

type Language = "uz" | "ru";

const copy = {
  uz: {
    product: "Ruchka",
    catalog: "Kategoriyalar",
    cart: "Savat",
    orders: "Buyurtmalar",
    ordersTitle: "Mening buyurtmalarim",
    profile: "Profil",
    desktopNavigation: "Asosiy menyu",
    mobileNavigation: "Mobil menyu",
    signIn: "Kirish",
    loginCode: "Kirish kodi",
    pickup: "Olib ketish",
    cardPayment: "Kartaga o'tkazma",
    name: "Ismingiz",
    phone: "Telefon raqamingiz",
    address: "Manzil",
    add: "Savatga qo'shish",
    checkout: "Buyurtma berish",
    submit: "Buyurtmani tasdiqlash",
    success: "Buyurtmangiz qabul qilindi!",
    total: "Jami to'lov",
    receiptLabel: "Rasm yoki PDF chekni tanlang",
    receiptPending: "Chek yuborildi — to'lov tekshirilmoqda.",
    retry: "Qayta urinish",
    quoteChanged: "Buyurtma summasi yoki savat o'zgardi. Yangi summani tekshirib, qayta tasdiqlang.",
    confirmQuote: "Yangi summani tasdiqlash",
    updateRequired: "Buyurtmani davom ettirish uchun ilovani yangilang.",
    ordersEmpty: "Sizda hali buyurtmalar yo'q",
    uploadReceipt: "Chekni yuborish",
    signOut: "Chiqish",
    language: "uz",
  },
  ru: {
    product: "Ручка",
    catalog: "Категории",
    cart: "Корзина",
    orders: "Заказы",
    ordersTitle: "Мои заказы",
    profile: "Профиль",
    desktopNavigation: "Главное меню",
    mobileNavigation: "Мобильное меню",
    signIn: "Войти",
    loginCode: "Код входа",
    pickup: "Самовывоз",
    cardPayment: "Перевод на карту",
    name: "Ваше имя",
    phone: "Номер телефона",
    address: "Адрес",
    add: "В корзину",
    checkout: "Оформить заказ",
    submit: "Подтвердить заказ",
    success: "Ваш заказ принят!",
    total: "Итого к оплате",
    receiptLabel: "Выберите изображение чека или PDF",
    receiptPending: "Чек отправлен — ожидается проверка оплаты.",
    retry: "Повторить",
    quoteChanged: "Сумма или состав корзины изменились. Проверьте новую сумму и подтвердите заказ ещё раз.",
    confirmQuote: "Подтвердить новую сумму",
    updateRequired: "Обновите приложение, чтобы продолжить оформление заказа.",
    ordersEmpty: "У вас пока нет заказов",
    uploadReceipt: "Отправить чек",
    signOut: "Выйти",
    language: "ru",
  },
} satisfies Record<Language, Record<string, string>>;

const languages: Language[] = ["uz", "ru"];

for (const language of languages) {
  test(`browser login to cash order: ${language}`, async ({ page, purchaseApi }) => {
    const text = copy[language];
    await openPublicCatalog(page, language, purchaseApi);
    await page.getByRole("link", { name: new RegExp(text.product) }).first().click();
    await expect(page.getByRole("heading", { name: text.product })).toBeVisible();

    await page.getByRole("button", { name: text.add, exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: /Kans Shop|Войдите в Kans Shop/ })).toBeVisible();
    await submitLoginCode(page, text, "12345678");

    await expect(page).toHaveURL(/\/cart$/);
    await expect(page.getByRole("heading", { name: text.cart })).toBeVisible();
    await expect(page.getByText(text.product, { exact: true })).toBeVisible();
    await expect(page.locator("header a[href='/cart']")).toContainText("1");

    await openCheckout(page, text);
    await fillCheckout(page, text, { address: "Toshkent, test ko'chasi 1" });
    await page.getByRole("button", { name: text.submit, exact: true }).click();
    await expect(page.getByText(text.success)).toBeVisible();
    const checkout = purchaseApi.capturedCheckoutRequests[0];
    expect(checkout?.body).toMatchObject({
      purchase_contract_version: 1,
      payment_method: "cash",
      order_type: "delivery",
      customer_phone: "+998901234567",
      address: "Toshkent, test ko'chasi 1",
    });
    expect(checkout?.headers["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/i);
    await expect(page.locator("main p").filter({ hasText: /KANS-E2E-/ })).toBeVisible();
    await expectNoBrowserNetworkEscapes(page, purchaseApi);
  });

  test(`mini app cart to manual receipt: ${language}`, async ({ page, purchaseApi }) => {
    const text = copy[language];
    purchaseApi.setTelegramSession({
      initData: "synthetic-signed-init-data",
      user: { id: 8000000000000042, first_name: "Mini App Buyer", language_code: language },
    });
    await openPublicCatalog(page, language, purchaseApi);
    expect(purchaseApi.requestsFor("POST", "/auth/telegram").length).toBeGreaterThan(0);
    expect(purchaseApi.requestsFor("POST", "/auth/telegram").every((request) =>
      JSON.stringify(request.body) === JSON.stringify({ init_data: "synthetic-signed-init-data" }),
    )).toBe(true);

    await page.getByRole("link", { name: new RegExp(text.product) }).first().click();
    await expect(page.getByRole("heading", { name: text.product })).toBeVisible();
    await page.getByRole("button", { name: text.add, exact: true }).click();
    await expect(page).toHaveURL(/\/cart$/);
    await page.getByRole("button", { name: text.checkout, exact: true }).click();
    await expect(page.getByRole("heading", { name: /Buyurtma berish|Оформление заказа/ })).toBeVisible();
    await page.getByRole("button", { name: text.pickup, exact: true }).click();
    await page.getByRole("button", { name: text.cardPayment, exact: true }).click();
    await fillCheckout(page, text);
    await page.getByRole("button", { name: text.submit, exact: true }).click();

    await expect(page.getByText(/8600 0000 0000 0000/)).toBeVisible();
    const receipt = page.getByLabel(text.receiptLabel);
    await receipt.setInputFiles({
      name: "synthetic-receipt.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==",
        "base64",
      ),
    });
    const orderNumber = page.locator("main p").filter({ hasText: /KANS-E2E-/ });
    await page.getByRole("button", { name: text.uploadReceipt, exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: text.receiptPending })).toBeVisible();
    expect(purchaseApi.requestsFor("POST", "/orders/100/receipt")).toHaveLength(1);
    await expect(orderNumber).toBeVisible();
    await expectNoBrowserNetworkEscapes(page, purchaseApi);
  });

  test(`lost add and checkout responses reuse keys: ${language}`, async ({ page, purchaseApi }) => {
    const text = copy[language];
    await openPublicCatalog(page, language, purchaseApi);
    await page.getByRole("link", { name: new RegExp(text.product) }).first().click();
    await expect(page.getByRole("heading", { name: text.product })).toBeVisible();
    purchaseApi.failNextAddAfterCommit = true;
    await page.getByRole("button", { name: text.add, exact: true }).click();
    await submitLoginCode(page, text, "12345678");

    await expect(page.getByRole("alert").filter({ hasText: /savat|корзин/i })).toBeVisible();
    await page.getByRole("button", { name: text.retry, exact: true }).click();
    await expect(page).toHaveURL(/\/cart$/);
    expect(purchaseApi.capturedAddKeys).toHaveLength(2);
    expect(purchaseApi.capturedAddKeys[0]).toBe(purchaseApi.capturedAddKeys[1]);
    await expect(page.locator("header a[href='/cart']")).toContainText("1");

    await openCheckout(page, text);
    await fillCheckout(page, text, { address: "Toshkent, test ko'chasi 2" });
    purchaseApi.failNextCheckoutAfterCommit = true;
    await page.getByRole("button", { name: text.submit, exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: /javob|Ответ.*заказ/ })).toBeVisible();
    await page.getByRole("button", { name: text.retry, exact: true }).click();
    await expect(page.getByText(text.success)).toBeVisible();

    const requests = purchaseApi.capturedCheckoutRequests;
    expect(requests).toHaveLength(2);
    expect(requests[0]?.headers["idempotency-key"]).toBe(requests[1]?.headers["idempotency-key"]);
    expect(requests[0]?.body).toMatchObject({ purchase_contract_version: 1 });
    await expectNoBrowserNetworkEscapes(page, purchaseApi);
  });

  test(`quote change requires confirmation: ${language}`, async ({ page, purchaseApi }) => {
    const text = copy[language];
    await addFromProductWithLogin(page, text, purchaseApi);
    await openCheckout(page, text);
    await page.getByRole("button", { name: text.pickup, exact: true }).click();
    await fillCheckout(page, text);
    const displayedTotal = page.getByText(text.total, { exact: true }).locator("..").locator("span").nth(1);
    await expect(displayedTotal).toHaveText(/5\s?000/);
    purchaseApi.changeQuoteOnNextCheckout = true;
    await page.getByRole("button", { name: text.submit, exact: true }).click();

    await expect(page.getByRole("alert").filter({ hasText: text.quoteChanged })).toBeVisible();
    await expect(page.getByRole("button", { name: text.confirmQuote, exact: true })).toBeVisible();
    await expect(displayedTotal).toHaveText(/6\s?500/);
    expect(purchaseApi.capturedCheckoutRequests).toHaveLength(1);
    const first = purchaseApi.capturedCheckoutRequests[0];
    expect(first?.body).toMatchObject({ purchase_contract_version: 1 });
    expect((first?.body as { expected_total: string }).expected_total).toBe("5000.00");

    await page.getByRole("button", { name: text.confirmQuote, exact: true }).click();
    await expect(page.getByText(text.success)).toBeVisible();
    const [retried] = purchaseApi.capturedCheckoutRequests.slice(1);
    expect(purchaseApi.capturedCheckoutRequests).toHaveLength(2);
    expect((first?.body as { expected_quote: string }).expected_quote)
      .not.toBe((retried?.body as { expected_quote: string }).expected_quote);
    expect((retried?.body as { expected_total: string }).expected_total).toBe("6500.00");
    expect(first?.headers["idempotency-key"]).not.toBe(retried?.headers["idempotency-key"]);
    await expectNoBrowserNetworkEscapes(page, purchaseApi);
  });

  test(`sign out hides previous account: ${language}`, async ({ page, purchaseApi }) => {
    const text = copy[language];
    purchaseApi.seedCart(42, { quantity: 2 });
    purchaseApi.seedOrder(42, { id: 42, order_number: "KANS-OLD-USER-42" });
    await openPublicCatalog(page, language, purchaseApi);
    await navigationLink(page, text, "orders").click();
    await page.locator("main").getByRole("button", { name: text.signIn, exact: true }).click();
    await submitLoginCode(page, text, "12345678");
    await expect(page.getByText("KANS-OLD-USER-42", { exact: false })).toBeVisible();
    await expect(page.locator("header a[href='/cart']")).toContainText("2");

    await navigationLink(page, text, "profile").click();
    await page.locator("main").getByRole("button", { name: text.signOut, exact: true }).click();
    await expect(page.locator("main").getByRole("button", { name: text.signIn, exact: true })).toBeVisible();
    await page.locator("main").getByRole("button", { name: text.signIn, exact: true }).click();
    await submitLoginCode(page, text, "87654321");
    await navigationLink(page, text, "orders").click();
    await expect(page.getByRole("heading", { name: text.ordersTitle })).toBeVisible();
    await expect(page.getByText(text.ordersEmpty)).toBeVisible();
    await expect(page.getByText("KANS-OLD-USER-42", { exact: false })).toHaveCount(0);
    expect(purchaseApi.requestsFor("GET", "/orders/history").map((request) => purchaseApi.userIdForRequest(request)))
      .toContain(42);
    expect(purchaseApi.requestsFor("GET", "/orders/history").map((request) => purchaseApi.userIdForRequest(request)))
      .toContain(99);
    await expectNoBrowserNetworkEscapes(page, purchaseApi);
  });

  test(`legacy cached checkout requests reload: ${language}`, async ({ page, purchaseApi }) => {
    const text = copy[language];
    await addFromProductWithLogin(page, text, purchaseApi);
    await openCheckout(page, text);
    await page.getByRole("button", { name: text.pickup, exact: true }).click();
    await page.getByRole("button", { name: text.cardPayment, exact: true }).click();
    await fillCheckout(page, text);

    const legacyResult = await page.evaluate(async () => {
      const state = JSON.parse(localStorage.getItem("kans-shop-auth") ?? "{}") as {
        state?: { accessToken?: string };
      };
      const response = await fetch("/api/v1/orders", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${state.state?.accessToken ?? ""}`,
        },
        body: JSON.stringify({
          order_type: "pickup",
          customer_name: "Legacy Browser",
          customer_phone: "+998901234567",
          payment_method: "card_transfer",
        }),
      });
      return { status: response.status, body: await response.json() };
    });
    expect(legacyResult.status).toBe(409);
    expect(legacyResult.body).toMatchObject({ error: { code: "CLIENT_UPDATE_REQUIRED" } });
    const legacyRequest = purchaseApi.capturedCheckoutRequests[0];
    expect(legacyRequest?.body).not.toHaveProperty("purchase_contract_version");
    expect(legacyRequest?.headers["idempotency-key"]).toBeUndefined();

    purchaseApi.requireClientUpdateOnNextCheckout = true;
    await page.getByRole("button", { name: text.submit, exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: text.updateRequired })).toBeVisible();
    await expect(page.getByText(text.success)).toHaveCount(0);
    await expectNoBrowserNetworkEscapes(page, purchaseApi);
  });
}

async function openPublicCatalog(
  page: Page,
  language: Language,
  purchaseApi: PurchaseApiFixture,
): Promise<void> {
  await page.addInitScript((locale) => {
    localStorage.setItem("kans-shop-language", JSON.stringify({
      state: { language: locale, hasUserPreference: true },
      version: 0,
    }));
  }, language);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: copy[language].catalog })).toBeVisible();
  await expect(page.getByText(copy[language].product, { exact: true }).first()).toBeVisible();
  await expect.poll(() => purchaseApi.telegramBridgeRequests).toBeGreaterThan(0);
  const pageEnvelope = await page.evaluate(async (query) => {
    const response = await fetch(
      `/api/v1/catalog/products?q=${encodeURIComponent(query)}&category_id=1&page=1&limit=12`,
    );
    return response.json();
  }, copy[language].product);
  expect(pageEnvelope).toMatchObject({
    items: [{ id: 2 }],
    total: 1,
    page: 1,
    limit: 12,
    total_pages: 1,
  });
}

async function submitLoginCode(
  page: Page,
  text: typeof copy[Language],
  code: string,
): Promise<void> {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(text.loginCode).fill(code);
  await dialog.getByRole("button", { name: text.signIn, exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function addFromProductWithLogin(
  page: Page,
  text: typeof copy[Language],
  purchaseApi: PurchaseApiFixture,
): Promise<void> {
  await openPublicCatalog(page, text.language as Language, purchaseApi);
  await page.getByRole("link", { name: new RegExp(text.product) }).first().click();
  await expect(page.getByRole("heading", { name: text.product })).toBeVisible();
  await page.getByRole("button", { name: text.add, exact: true }).click();
  await submitLoginCode(page, text, "12345678");
  await expect(page).toHaveURL(/\/cart$/);
  await expect(page.getByText(text.product, { exact: true })).toBeVisible();
}

async function openCheckout(
  page: Page,
  text: typeof copy[Language],
): Promise<void> {
  await page.getByRole("button", { name: text.checkout, exact: true }).click();
  await expect(page.getByRole("heading", { name: /Buyurtma berish|Оформление заказа/ })).toBeVisible();
}

async function fillCheckout(
  page: Page,
  text: typeof copy[Language],
  options: { address?: string } = {},
): Promise<void> {
  await page.getByLabel(text.name).fill("Journey Buyer");
  await page.getByLabel(text.phone).fill("+998901234567");
  if (options.address) await page.getByLabel(text.address, { exact: true }).fill(options.address);
  await expect(page.getByRole("button", { name: text.submit, exact: true })).toBeEnabled();
}

function navigationLink(
  page: Page,
  text: typeof copy[Language],
  destination: "profile" | "orders",
) {
  const isMobile = page.viewportSize()?.width === 390;
  const navigation = isMobile
    ? page.getByRole("navigation", { name: text.mobileNavigation })
    : page.getByRole("navigation", { name: text.desktopNavigation });
  return navigation.getByRole("link", { name: text[destination], exact: true });
}

async function expectNoBrowserNetworkEscapes(
  page: Page,
  purchaseApi: PurchaseApiFixture,
): Promise<void> {
  expect(purchaseApi.unhandledApiRequests).toEqual([]);
  expect(purchaseApi.unexpectedExternalRequests).toEqual([]);
  expect(purchaseApi.telegramBridgeRequests).toBeGreaterThan(0);
  await expect(page.locator("body")).toBeVisible();
}
