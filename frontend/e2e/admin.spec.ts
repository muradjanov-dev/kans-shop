import { expect, test } from "@playwright/test";

const adminSession = {
  admin_id: 57,
  full_name: "Synthetic operator",
  role: "operator",
  csrf_token: "synthetic-admin-csrf",
};

const report = {
  period: "today",
  orders_count: 3,
  order_value: "92000",
  paid_amount: "40000",
  revenue: "92000",
  avg_check: "46000",
  new_users: 1,
  top_products: [{ name: "Synthetic notebook", sold: 2 }],
};

const order = {
  id: 401,
  order_number: "SYN-401",
  status: "new",
  customer_name: "Synthetic buyer",
  total: "46000",
  created_at: "2026-10-09T09:00:00Z",
};

test("operator reports and orders work on mobile and desktop without buyer auth", async ({ page }) => {
  const requests: Array<{ method: string; path: string }> = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = request.method();
    requests.push({ method, path });
    if (path === "/auth/admin/session" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", json: adminSession });
      return;
    }
    if (path === "/admin/stats/overview" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", json: report });
      return;
    }
    if (path === "/admin/orders" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", json: { items: [order], total: 1, page: 1, limit: 20, total_pages: 1 } });
      return;
    }
    await route.fulfill({ status: 501, contentType: "application/json", json: { error: { code: "UNHANDLED_SYNTHETIC_ROUTE", message: "No browser fixture exists for this request." } } });
  });

  await page.goto("/admin/reports");
  await expect(page.getByRole("heading", { name: "Hisobotlar" })).toBeVisible();
  await expect(page.getByText(/bekor qilinmagan buyurtmalar summasi/i)).toBeVisible();
  await expect(page.getByText(/to'lovi tasdiqlangan buyurtmalar summasi/i)).toBeVisible();

  const nav = page.getByRole("navigation", { name: "Asosiy menyu" });
  await expect(nav.getByRole("link", { name: "Buyurtmalar" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Katalog" })).toHaveCount(0);
  await nav.getByRole("link", { name: "Buyurtmalar" }).click();
  await expect(page.getByRole("button", { name: /SYN-401/i })).toBeVisible();

  const viewportFits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(viewportFits).toBe(true);
  expect(requests.some(({ path }) => path.startsWith("/auth/telegram") || path.startsWith("/auth/customer"))).toBe(false);
  expect(requests.every(({ path }) => path.length > 0)).toBe(true);
});

test("opening broadcasts stays inert while Task 10 owns its contract", async ({ page }) => {
  const requests: Array<{ method: string; path: string }> = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api\/v1/, "");
    const method = request.method();
    requests.push({ method, path });
    if (path === "/auth/admin/session" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", json: { ...adminSession, role: "manager" } });
      return;
    }
    await route.fulfill({ status: 501, contentType: "application/json", json: { error: { code: "UNHANDLED_SYNTHETIC_ROUTE", message: "No browser fixture exists for this request." } } });
  });

  await page.goto("/admin/broadcasts");
  await expect(page.getByRole("status")).toContainText(/Task 10.*broadcast API/i);
  expect(requests.some(({ method, path }) => method !== "GET" && path.includes("broadcasts"))).toBe(false);
});
