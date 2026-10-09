import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { expect, test, type StorefrontApiFixture } from "./fixtures/storefrontApi";
import type { PurchaseApiFixture } from "./fixtures/purchaseApi";
import type { Page, TestInfo } from "@playwright/test";

type Language = "uz" | "ru";
type Theme = "light" | "dark";

const copy = {
  uz: {
    product: "Sinov mahsuloti — ruchka",
    description: "Faqat avtomatlashtirilgan qabul testi uchun sun’iy mahsulot.",
    catalog: "Kategoriyalar",
    navCatalog: "Katalog",
    allProducts: "Barcha mahsulotlar",
    cart: "Savat",
    checkoutFromCart: "Buyurtma berish",
    orders: "Buyurtmalar",
    ordersTitle: "Mening buyurtmalarim",
    profile: "Profil",
    profileTitle: "Hisobingiz",
    profileName: "Ism familiya",
    favorites: "Sevimlilar",
    addresses: "Manzillar",
    desktopNavigation: "Asosiy menyu",
    mobileNavigation: "Mobil menyu",
    accountNavigation: "Hisob bo‘limlari",
    signIn: "Kirish",
    signOut: "Chiqish",
    loginCode: "Kirish kodi",
    pickup: "Olib ketish",
    name: "Ismingiz",
    phone: "Telefon raqamingiz",
    address: "Manzil",
    addressComment: "Manzilga izoh",
    addressBookComment: "Qo‘shimcha izoh",
    savedAddress: "Saqlangan manzil",
    addressLabel: "Manzil nomi",
    addressText: "Manzil matni",
    editAddress: "Tahrirlash",
    saveAddress: "Saqlash",
    addFavorite: "Sevimlilarga qo‘shish",
    removeFavorite: "Sevimlilardan olib tashlash",
    addToCart: "Savatga qo‘shish",
    sku: "Artikul: SYNTH-001",
    stock: "Qoldiq: 20 dona",
    minimum: "Minimal buyurtma: 1",
    gallery: "Mahsulot rasmlari",
    secondImage: "Rasmni tanlash 2",
    language: "Til",
    themeButtonLight: "Qorong‘i mavzuni yoqish",
    themeButtonDark: "Yorug‘ mavzuni yoqish",
    featured: "Tavsiya etilgan",
    back: "Orqaga",
    search: "Mahsulotlarni qidirish",
    minPrice: "Minimal narx",
    maxPrice: "Maksimal narx",
    inStock: "Faqat mavjud",
    sort: "Saralash",
    sortNewest: "Yangi",
    total: "Jami to'lov",
    submit: "Buyurtmani tasdiqlash",
    addressSnapshot: "Buyurtma manzili",
    success: "Buyurtmangiz qabul qilindi!",
    orderNumber: "SYNTH-ORDER-77",
    timeline: "Buyurtma bosqichlari",
    timelineNav: "Buyurtma vaqt jadvali",
    newStatus: "Yangi",
    supportRegion: "Do'kon bilan aloqa va ma'lumot",
    supportLink: "Telegram yordami",
    testAddressLabel: "Synthetic home",
    originalAddress: "Synthetic Street 1, Apt 2",
    originalAddressComment: "Synthetic entry note",
    updatedAddress: "Synthetic Street 99, Apt 8",
    updatedAddressComment: "Synthetic updated entry note",
  },
  ru: {
    product: "Тестовый товар — ручка",
    description: "Синтетический товар только для автоматизированной приёмки.",
    catalog: "Категории",
    navCatalog: "Каталог",
    allProducts: "Все товары",
    cart: "Корзина",
    checkoutFromCart: "Оформить заказ",
    orders: "Заказы",
    ordersTitle: "Мои заказы",
    profile: "Профиль",
    profileTitle: "Ваш профиль",
    profileName: "Имя и фамилия",
    favorites: "Избранное",
    addresses: "Адреса",
    desktopNavigation: "Главное меню",
    mobileNavigation: "Мобильное меню",
    accountNavigation: "Разделы аккаунта",
    signIn: "Войти",
    signOut: "Выйти",
    loginCode: "Код входа",
    pickup: "Самовывоз",
    name: "Ваше имя",
    phone: "Номер телефона",
    address: "Адрес",
    addressComment: "Комментарий к адресу",
    addressBookComment: "Дополнительный комментарий",
    savedAddress: "Сохранённый адрес",
    addressLabel: "Название адреса",
    addressText: "Текст адреса",
    editAddress: "Изменить",
    saveAddress: "Сохранить",
    addFavorite: "Добавить в избранное",
    removeFavorite: "Удалить из избранного",
    addToCart: "В корзину",
    sku: "Артикул: SYNTH-001",
    stock: "Остаток: 20 шт.",
    minimum: "Мин. заказ: 1",
    gallery: "Изображения товара",
    secondImage: "Выбрать изображение 2",
    language: "Язык",
    themeButtonLight: "Включить тёмную тему",
    themeButtonDark: "Включить светлую тему",
    featured: "Рекомендуем",
    back: "Назад",
    search: "Поиск товаров",
    minPrice: "Минимальная цена",
    maxPrice: "Максимальная цена",
    inStock: "В наличии",
    sort: "Сортировка",
    sortNewest: "Сначала новые",
    total: "Итого к оплате",
    submit: "Подтвердить заказ",
    addressSnapshot: "Адрес заказа",
    success: "Ваш заказ принят!",
    orderNumber: "SYNTH-ORDER-77",
    timeline: "Этапы заказа",
    timelineNav: "Хронология заказа",
    newStatus: "Новый",
    supportRegion: "Контакты и информация магазина",
    supportLink: "Поддержка в Telegram",
    testAddressLabel: "Synthetic home",
    originalAddress: "Synthetic Street 1, Apt 2",
    originalAddressComment: "Synthetic entry note",
    updatedAddress: "Synthetic Street 99, Apt 8",
    updatedAddressComment: "Synthetic updated entry note",
  },
} satisfies Record<Language, Record<string, string>>;

const languages: Language[] = ["uz", "ru"];
const themes: Theme[] = ["light", "dark"];

for (const language of languages) {
  for (const theme of themes) {
    test.describe(`${language} · ${theme}`, () => {
      const text = copy[language];

      test("guest_catalog_to_favorite_login", async ({ page, purchaseApi, storefrontApi }, testInfo) => {
        await openCatalog(page, language, theme, storefrontApi);
        await assertStorefrontNavigation(page, text);
        await assertTouchTargets(page);
        await captureVisualReview(page, testInfo, language, theme);
        await assertKeyboardFocus(page, text);

        await openProduct(page, text);
        await expectProductDetails(page, text);
        const favorite = page.getByRole("button", {
          name: `${text.addFavorite}: ${text.product}`,
          exact: true,
        });
        await favorite.click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await expect(page.getByRole("dialog").getByLabel(text.loginCode)).toBeVisible();
        expect(purchaseApi.requestsFor("PUT", `/favorites/${storefrontApi.product.id}`)).toHaveLength(0);

        await submitLoginCode(page, text, "12345678");
        await expect(page.getByRole("button", {
          name: `${text.removeFavorite}: ${text.product}`,
          exact: true,
        })).toHaveAttribute("aria-pressed", "true");
        expect(purchaseApi.requestsFor("PUT", `/favorites/${storefrontApi.product.id}`)).toHaveLength(1);

        await page.locator("main").getByRole("link", { name: text.back, exact: false }).click();
        const navigation = await storefrontNavigation(page, text);
        await navigation.getByRole("link", { name: text.profile, exact: true }).click();
        await page.getByRole("navigation", { name: text.accountNavigation })
          .getByRole("link", { name: text.favorites, exact: true }).click();
        await expect(page.getByRole("heading", { name: text.favorites })).toBeVisible();
        await expect(page.getByText(text.product, { exact: true }).first()).toBeVisible();
        expect(storefrontApi.favoriteIdsFor(42)).toContain(storefrontApi.product.id);
        await expectNoNetworkEscapes(page, purchaseApi);
      });

      test("filter_product_back_restores_query", async ({ page, purchaseApi, storefrontApi }) => {
        await openCatalog(page, language, theme, storefrontApi);
        const search = page.locator("main").getByRole("searchbox", { name: text.search });
        await search.fill(text.product);
        await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe(text.product);
        await page.getByRole("textbox", { name: text.minPrice }).fill("4000");
        await page.getByRole("textbox", { name: text.maxPrice }).fill("6000");
        const stockFilter = page.getByRole("checkbox", { name: text.inStock });
        await stockFilter.click();
        await expect(stockFilter).toBeChecked();
        await page.getByRole("combobox", { name: text.sort }).selectOption("newest");
        await expect.poll(() => new URL(page.url()).searchParams.get("min_price")).toBe("4000");
        await expect.poll(() => new URL(page.url()).searchParams.get("sort")).toBe("newest");
        await expect(page.locator("article").filter({ hasText: text.product }).first()).toBeVisible();

        const catalogRequest = await waitForCatalogRequest(purchaseApi, text.product, {
          min_price: "4000",
          max_price: "6000",
          in_stock: "true",
          sort: "newest",
        });
        const requestUrl = new URL(catalogRequest.path, "http://fixture.invalid");
        expect(requestUrl.searchParams.get("q")).toBe(text.product);
        expect(requestUrl.searchParams.get("min_price")).toBe("4000");
        expect(requestUrl.searchParams.get("max_price")).toBe("6000");
        expect(requestUrl.searchParams.get("in_stock")).toBe("true");
        expect(requestUrl.searchParams.get("sort")).toBe("newest");

        await openProduct(page, text);
        await expectProductDetails(page, text);
        await page.locator("main").getByRole("link", { name: text.back, exact: false }).click();
        const restored = new URL(page.url());
        expect(restored.pathname).toBe("/");
        expect(restored.searchParams.get("q")).toBe(text.product);
        expect(restored.searchParams.get("min_price")).toBe("4000");
        expect(restored.searchParams.get("max_price")).toBe("6000");
        expect(restored.searchParams.get("in_stock")).toBe("true");
        expect(restored.searchParams.get("sort")).toBe("newest");
        await expect(page.locator("main").getByRole("searchbox", { name: text.search })).toHaveValue(text.product);
        await expectNoNetworkEscapes(page, purchaseApi);
      });

      test("profile_address_snapshot_stays_confirmed", async ({ page, purchaseApi, storefrontApi }) => {
        purchaseApi.seedCart(42, { quantity: 1 });
        storefrontApi.seedAddress(42, {
          id: 901,
          label: text.testAddressLabel,
          address_text: text.originalAddress,
          address_comment: text.originalAddressComment,
          is_default: true,
        });
        await openCatalog(page, language, theme, storefrontApi);
        await loginFromHeader(page, text, "12345678");
        await assertStorefrontNavigation(page, text);
        await navigationLink(page, text, "profile").click();
        await expect(page.getByRole("heading", { name: text.profileTitle })).toBeVisible();
        await expect(page.getByLabel(text.profileName)).toHaveValue("Synthetic Buyer 42");
        await page.getByRole("navigation", { name: text.accountNavigation })
          .getByRole("link", { name: text.addresses, exact: true }).click();
        await expect(page.getByRole("heading", { name: text.addresses })).toBeVisible();
        await navigationLink(page, text, "cart").click();
        await expect(page.getByRole("heading", { name: text.cart })).toBeVisible();
        await page.getByRole("button", { name: text.checkoutFromCart, exact: true }).click();
        await expect(page.getByRole("heading", { name: /buyurtma berish|оформление заказа/i })).toBeVisible();

        await page.getByLabel(text.savedAddress).selectOption("901");
        const addressField = page.getByLabel(text.address, { exact: true });
        const addressCommentField = page.getByLabel(text.addressComment, { exact: true });
        await expect(addressField).toHaveValue(text.originalAddress);
        await expect(addressCommentField).toHaveValue(text.originalAddressComment);

        const addressTab = await page.context().newPage();
        await addressTab.goto("/profile/addresses");
        await expect(addressTab.getByRole("heading", { name: text.addresses })).toBeVisible();
        await addressTab.getByRole("button", {
          name: new RegExp(`${escapeRegExp(text.editAddress)}: ${escapeRegExp(text.testAddressLabel)}`),
        }).click();
        const dialog = addressTab.getByRole("dialog");
        await dialog.getByLabel(text.addressText).fill(text.updatedAddress);
        await dialog.getByLabel(text.addressBookComment).fill(text.updatedAddressComment);
        await dialog.getByRole("button", { name: text.saveAddress, exact: true }).click();
        await expect(addressTab.getByText(text.updatedAddress, { exact: true })).toBeVisible();
        await addressTab.close();

        await expect(addressField).toHaveValue(text.originalAddress);
        await expect(addressCommentField).toHaveValue(text.originalAddressComment);
        await page.getByLabel(text.name).fill("Synthetic Checkout Buyer");
        await page.getByLabel(text.phone).fill("+998901234567");
        await page.getByRole("button", { name: text.submit, exact: true }).click();
        await expect(page.getByText(text.success)).toBeVisible();

        const [checkoutRequest] = purchaseApi.capturedCheckoutRequests;
        expect(checkoutRequest?.body).toMatchObject({
          address: text.originalAddress,
          address_comment: text.originalAddressComment,
        });
        expect(checkoutRequest?.body).not.toHaveProperty("address_id");
        await page.getByRole("link", { name: /KANS-E2E-/ }).click();
        await expect(page.locator("address")).toContainText(text.originalAddress);
        await expect(page.locator("address")).not.toContainText(text.updatedAddress);
        expect(purchaseApi.userIdForRequest(checkoutRequest!)).toBe(42);
        await expectNoNetworkEscapes(page, purchaseApi);
      });

      test("favorite_syncs_after_login", async ({ page, purchaseApi, storefrontApi }) => {
        await openCatalog(page, language, theme, storefrontApi);
        await loginFromHeader(page, text, "12345678");
        const favorite = page.getByRole("button", {
          name: `${text.addFavorite}: ${text.product}`,
          exact: true,
        }).first();
        await expect(favorite).toHaveAttribute("aria-pressed", "false");
        await favorite.click();
        await expect(page.getByRole("button", {
          name: `${text.removeFavorite}: ${text.product}`,
          exact: true,
        }).first()).toHaveAttribute("aria-pressed", "true");
        expect(purchaseApi.requestsFor("PUT", `/favorites/${storefrontApi.product.id}`)).toHaveLength(1);

        const navigation = await storefrontNavigation(page, text);
        await navigation.getByRole("link", { name: text.profile, exact: true }).click();
        await page.getByRole("navigation", { name: text.accountNavigation })
          .getByRole("link", { name: text.favorites, exact: true }).click();
        await expect(page.getByText(text.product, { exact: true }).first()).toBeVisible();
        expect(storefrontApi.favoriteIdsFor(42)).toEqual([storefrontApi.product.id]);

        await page.locator("main").getByRole("link", { name: text.profile, exact: true }).click();
        await page.locator("main").getByRole("button", { name: text.signOut, exact: true }).click();
        await page.getByRole("navigation", { name: text.accountNavigation })
          .getByRole("link", { name: text.favorites, exact: true }).click();
        await expect(page.locator("header").getByRole("button", { name: text.signIn, exact: true })).toBeVisible();
        await loginFromHeader(page, text, "87654321");
        await expect(page.getByText(text.product, { exact: true })).toHaveCount(0);
        await expect(page.getByText(language === "uz" ? "Hozircha sevimlilar yo‘q." : "В избранном пока ничего нет.")).toBeVisible();

        const favoriteReads = purchaseApi.requestsFor("GET", "/favorites")
          .map((request) => purchaseApi.userIdForRequest(request));
        expect(favoriteReads).toContain(42);
        expect(favoriteReads).toContain(99);
        expect(storefrontApi.favoriteIdsFor(99)).toEqual([]);
        await expectNoNetworkEscapes(page, purchaseApi);
      });

      test("order_timeline_and_support_use_server_data", async ({ page, purchaseApi, storefrontApi }) => {
        storefrontApi.setConfiguredSupport();
        const order = purchaseApi.seedOrder(42, { id: 77, order_number: "SYNTH-ORDER-77" });
        storefrontApi.seedTimeline(order.id, 42, [{ status: "new", occurred_at: "2020-01-02T03:04:00Z" }]);
        await openCatalog(page, language, theme, storefrontApi);
        await loginFromHeader(page, text, "12345678");
        await navigationLink(page, text, "orders").click();
        await expect(page.getByRole("heading", { name: text.ordersTitle })).toBeVisible();
        const orderLink = page.getByRole("link", { name: /SYNTH-ORDER-77/ });
        await expect(orderLink).toBeVisible();
        await orderLink.click();

        await expect(page.getByRole("heading", { name: /SYNTH-ORDER-77/ })).toBeVisible();
        const timeline = page.getByRole("list", { name: text.timelineNav });
        await expect(timeline.getByText(text.newStatus, { exact: true })).toBeVisible();
        await expect(timeline.locator("time[datetime='2020-01-02T03:04:00Z']")).toBeVisible();
        await expect(timeline.getByText(/admin|internal|комментар/i)).toHaveCount(0);
        const support = page.getByRole("region", { name: text.supportRegion });
        await expect(support.getByRole("link", { name: text.supportLink })).toHaveAttribute(
          "href",
          "https://t.me/synthetic_test_support",
        );
        expect(purchaseApi.requestsFor("GET", "/orders/77/timeline")).toHaveLength(1);

        storefrontApi.setSupportSettings({ support_username: null, shop_phone: null, work_hours: null });
        await page.reload();
        await expect(page.getByRole("heading", { name: /SYNTH-ORDER-77/ })).toBeVisible();
        await expect(page.getByRole("link", { name: text.supportLink })).toHaveCount(0);
        await expect(page.getByRole("region", { name: text.supportRegion })).toHaveCount(0);
        await expectNoNetworkEscapes(page, purchaseApi);
      });
    });
  }
}

async function openCatalog(
  page: Page,
  language: Language,
  theme: Theme,
  fixture: StorefrontApiFixture,
): Promise<void> {
  await page.addInitScript(({ savedLanguage, savedTheme }) => {
    localStorage.setItem("kans-shop-language", JSON.stringify({
      state: { language: savedLanguage, hasUserPreference: true },
      version: 0,
    }));
    localStorage.setItem("kans-shop-theme", JSON.stringify({
      state: { theme: savedTheme, hasUserPreference: true },
      version: 0,
    }));
  }, { savedLanguage: language, savedTheme: theme });
  await page.goto("/");
  const text = copy[language];
  await expect(page.getByRole("heading", { name: text.catalog })).toBeVisible();
  await expect(page.getByRole("heading", { name: text.allProducts })).toBeVisible();
  await expect(page.getByText(text.product, { exact: true }).first()).toBeVisible();
  expect(await page.locator("html").evaluate((element) => element.classList.contains("dark"))).toBe(theme === "dark");
  expect(fixture.product.is_featured).toBe(false);
  await expect(page.getByRole("heading", { name: text.featured })).toHaveCount(0);
}

async function openProduct(page: Page, text: typeof copy[Language]): Promise<void> {
  await page.locator("article").filter({ hasText: text.product }).first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: text.product })).toBeVisible();
}

async function expectProductDetails(page: Page, text: typeof copy[Language]): Promise<void> {
  await expect(page.getByText(text.description, { exact: true })).toBeVisible();
  await expect(page.getByText("5 000", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(text.sku, { exact: true })).toBeVisible();
  await expect(page.getByText(text.stock, { exact: true })).toBeVisible();
  await expect(page.getByText(text.minimum, { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: text.gallery })).toBeVisible();
  const gallery = page.getByRole("region", { name: text.gallery }).first();
  await expect(gallery.locator("img")).toHaveCount(3);
  const initialImage = await gallery.locator("img").first().getAttribute("src");
  const secondImage = gallery.getByRole("button", { name: text.secondImage });
  await secondImage.click();
  await expect(secondImage).toHaveAttribute("aria-pressed", "true");
  expect(await gallery.locator("img").first().getAttribute("src")).not.toBe(initialImage);
  await expect(page.getByText(text.featured, { exact: true })).toHaveCount(0);
  await expect(page.locator("del")).toHaveCount(0);
}

async function submitLoginCode(page: Page, text: typeof copy[Language], code: string): Promise<void> {
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(text.loginCode).fill(code);
  await dialog.getByRole("button", { name: text.signIn, exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function loginFromHeader(page: Page, text: typeof copy[Language], code: string): Promise<void> {
  const headerSignIn = page.locator("header").getByRole("button", { name: text.signIn, exact: true });
  if (await headerSignIn.isVisible()) await headerSignIn.click();
  await submitLoginCode(page, text, code);
}

async function storefrontNavigation(page: Page, text: typeof copy[Language]) {
  const isMobile = page.viewportSize()?.width === 390;
  const navigation = page.getByRole("navigation", {
    name: isMobile ? text.mobileNavigation : text.desktopNavigation,
  });
  await expect(navigation).toBeVisible();
  return navigation;
}

function navigationLink(page: Page, text: typeof copy[Language], destination: "cart" | "orders" | "profile") {
  const isMobile = page.viewportSize()?.width === 390;
  return page.getByRole("navigation", {
    name: isMobile ? text.mobileNavigation : text.desktopNavigation,
  }).getByRole("link", {
    name: destination === "cart" ? new RegExp(escapeRegExp(text.cart)) : text[destination],
    exact: destination !== "cart",
  });
}

async function assertStorefrontNavigation(page: Page, text: typeof copy[Language]): Promise<void> {
  const navigation = await storefrontNavigation(page, text);
  await expect(navigation.getByRole("link", { name: text.navCatalog, exact: true }))
    .toHaveAttribute("aria-current", "page");
  await expect(navigation.getByRole("link", { name: text.orders, exact: true })).toBeVisible();
  await expect(navigation.getByRole("link", { name: new RegExp(escapeRegExp(text.cart)) })).toBeVisible();
  await expect(navigation.getByRole("link", { name: text.profile, exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: text.language })).toBeVisible();
  const currentThemeLabel = await page.locator("html").evaluate((element) =>
    element.classList.contains("dark") ? "dark" : "light",
  );
  await expect(page.getByRole("button", {
    name: currentThemeLabel === "dark" ? text.themeButtonDark : text.themeButtonLight,
  })).toBeVisible();
}

async function assertTouchTargets(page: Page): Promise<void> {
  const smallTargets = await page.locator("a:visible, button:visible, input:visible, select:visible, textarea:visible")
    .evaluateAll((elements) => elements.flatMap((element) => {
      const isCheckbox = element instanceof HTMLInputElement &&
        (element.type === "checkbox" || element.type === "radio");
      const target = isCheckbox ? element.closest("label") ?? element : element;
      const bounds = target.getBoundingClientRect();
      return bounds.width < 44 || bounds.height < 44
        ? [{
            tag: target.tagName.toLowerCase(),
            label: target.getAttribute("aria-label") ?? target.textContent?.trim() ?? "",
            width: Math.round(bounds.width),
            height: Math.round(bounds.height),
          }]
        : [];
    }));
  expect(smallTargets, `Interactive targets under 44px: ${JSON.stringify(smallTargets)}`).toEqual([]);
}

async function assertKeyboardFocus(page: Page, text: typeof copy[Language]): Promise<void> {
  const language = page.getByRole("combobox", { name: text.language });
  await page.locator("body").click({ position: { x: 4, y: 120 } });
  for (let attempt = 0; attempt < 24 && !(await language.evaluate((element) => element === document.activeElement)); attempt += 1) {
    await page.keyboard.press("Tab");
  }
  await expect(language).toBeFocused();
  await expect(language).toHaveCSS("outline-style", "solid");
  await expect(language).toHaveCSS("outline-width", "2px");
}

async function captureVisualReview(page: Page, testInfo: TestInfo, language: Language, theme: Theme): Promise<void> {
  const viewportWidth = page.viewportSize()?.width ?? 0;
  const path = testInfo.outputPath("storefront-artifacts", `${viewportWidth}px-${language}-${theme}-catalog.png`);
  await mkdir(dirname(path), { recursive: true });
  await page.screenshot({ path, fullPage: true, animations: "disabled" });
}

async function waitForCatalogRequest(
  purchaseApi: PurchaseApiFixture,
  query: string,
  expected: Record<string, string>,
) {
  const isMatch = (request: PurchaseApiFixture["requests"][number]) => {
    const url = new URL(request.path, "http://fixture.invalid");
    return request.method === "GET" && url.pathname === "/catalog/products" &&
      url.searchParams.get("q") === query &&
      Object.entries(expected).every(([key, value]) => url.searchParams.get(key) === value);
  };
  await expect.poll(() => purchaseApi.requests.filter((request) => {
    return isMatch(request);
  }).length).toBeGreaterThan(0);
  return purchaseApi.requests.find(isMatch)!;
}

async function expectNoNetworkEscapes(page: Page, purchaseApi: PurchaseApiFixture): Promise<void> {
  expect(purchaseApi.unhandledApiRequests).toEqual([]);
  expect(purchaseApi.unexpectedExternalRequests).toEqual([]);
  expect(purchaseApi.telegramBridgeRequests).toBeGreaterThan(0);
  expect(purchaseApi.requests.every((request) => request.path.startsWith("/"))).toBe(true);
  expect(purchaseApi.requestsFor("POST", "/auth/telegram")).toHaveLength(0);
  await expect(page.locator("body")).toBeVisible();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
