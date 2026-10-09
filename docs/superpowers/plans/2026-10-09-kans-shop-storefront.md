# Kans Shop Storefront and Customer Cabinet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one responsive Kans Shop catalog and customer cabinet across Telegram Mini App and browser, using the existing catalog, account, checkout and order contracts as the source of truth.

**Architecture:** Extend the shared FastAPI catalog and customer services, preserving existing URLs and bot behavior. Add profile/address persistence and owner-scoped favorites/history contracts, then build typed React Query pages whose filter state lives in the URL and whose customer state is cleared on account changes. Keep prices, inventory, quote and order status authoritative on the server.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, Redis 7, React 19, TypeScript, Vite, TanStack Query, Zustand, Vitest, React Testing Library, Playwright.

**Spec:** [Storefront and customer cabinet design](../specs/2026-10-09-kans-shop-storefront-design.md). Read this approved design and the phase-one purchase plan before execution.

## Global Constraints

- Keep one store; anonymous users may browse, but server cart and account actions require a verified Telegram customer.
- Preserve `/`, `/product/:id`, `/cart`, `/checkout`, `/orders` and `/orders/:id`; add `/profile`, `/favorites` and `/profile/addresses`.
- Search debounce is 300ms; catalog/search pages contain 24 products; sort ties use stable IDs; filter changes reset page to 1.
- Saved addresses contain only customer-entered text and comment. No coordinates, map, geocoding or automatic address detection; order payloads store the confirmed address text/comment snapshot, never a saved-address ID.
- A customer has at most 20 saved addresses and at most one default. Lock the customer row for create/default/delete and enforce the default invariant with a partial unique index.
- Profile exposes only `display_name`, `phone`, and `language`; phone may be null, language is `uz` or `ru`, and name is 1–128 trimmed characters. Do not allow customers to change Telegram ID, username, admin flag or role.
- Reuse the existing `favorites` table and repository/service path for both bot and web. Do not add browser-local favorite state or a duplicate table.
- Public product visibility requires an active product and every category ancestor active; malformed/cyclic trees are omitted. Featured products require server `is_featured=true`.
- Do not invent prices, availability, discounts, bestseller marks, promo copy, support details, fees or payment readiness. No new payment provider or map provider.
- Only `GET /settings/public` allowlisted fields may reach the public storefront; secrets and admin fields remain private.
- Timeline exposes only customer-facing status and event time; never history comments, admin IDs or admin names. A sparse history never gets fabricated timestamps or future completed events.
- Use accessible labels and visible focus, minimum 44px touch targets, and honor `prefers-reduced-motion`. Light/dark styles remain readable at mobile and desktop sizes.
- Phase-one execution provides `./scripts/test-purchase.sh`, `backend/tests/api_helpers.py`, Vitest `frontend/src/test/renderWithProviders.tsx`, the Playwright config/fixtures, customer login provider, pending cart action, and auth-epoch cache handling. Reuse those fixtures and contracts; do not duplicate them.
- Phase two is the dependency for real category images, `is_featured`, support, work hours, welcome text and public settings. Its Alembic head is `2f7c9e13b0d5`; phase three has one migration, revision `3a8d0f24c1e6`, with that exact `down_revision`.
- Automated tests use synthetic users/products, disposable services, fake bot/API responses and no production database, Telegram account, real order or payment.

## Review Focus

- Inactive ancestors and cyclic category chains must not leak a product or trap navigation — Task 1: `test_catalog_hides_inactive_and_cyclic_ancestors`.
- Parallel address writes and address edits after checkout must preserve ownership, the 20-row cap, one default and immutable order snapshots — Task 2: `test_address_concurrency_limit_and_order_snapshot`.
- A late response to an old search must not replace a newer URL query or its results — Task 6: `test_catalog_debounce_abort_and_back_navigation`.
- A customer response arriving after logout/account switch must not repopulate private cache — Task 7: `test_customer_cache_isolated_after_account_switch`.
- A cancelled or sparse timeline must stay terminal/sparse and omit operator-only fields — Task 4: `test_customer_timeline_is_safe_for_cancelled_and_sparse_history`.

## File Responsibilities

| Area | New files | Existing integration points |
| --- | --- | --- |
| Shared catalog | `backend/app/api/schemas/catalog.py`, `backend/tests/test_storefront_catalog.py` | `backend/app/api/v1/catalog.py`, `backend/app/services/catalog_service.py`, `backend/app/db/repositories/{category,product}_repository.py` |
| Profile and addresses | `backend/app/db/models/address.py`, `backend/app/api/schemas/customer.py`, `backend/app/api/v1/profile.py`, `backend/app/api/v1/addresses.py`, `backend/app/services/{profile,address}_service.py`, `backend/alembic/versions/3a8d0f24c1e6_storefront_customer_data.py`, `backend/tests/test_storefront_customer_api.py`, `backend/tests/test_storefront_migrations.py` | `backend/app/db/models/user.py`, `backend/app/db/models/__init__.py`, `backend/app/db/repositories/user_repository.py`, `backend/app/api/v1/__init__.py`, checkout address inputs |
| Shared favorites | `backend/app/services/favorite_service.py`, `backend/app/api/v1/favorites.py`, `backend/app/api/schemas/favorites.py`, `backend/tests/test_favorites_api.py` | existing `favorite_repository.py`, `bot/handlers/user/favorites.py`, `api/v1/__init__.py` |
| Customer orders | `backend/app/api/schemas/customer_orders.py`, `backend/app/services/customer_order_service.py`, `backend/tests/test_customer_orders_api.py` | `backend/app/api/v1/orders.py`, `backend/app/db/repositories/order_repository.py`, `backend/app/db/models/order_status_history.py` |
| Responsive shell | `frontend/src/components/storefront/{StorefrontHeader,MobileNavigation,LanguageSwitcher,ThemeToggle}.tsx`, `frontend/src/store/theme.ts`, `frontend/src/components/storefront/StorefrontShell.test.tsx` | `App.tsx`, `Layout.tsx`, `index.css`, `lib/i18n.ts`, `store/language.ts` |
| Catalog pages | `frontend/src/components/storefront/{CategoryTile,CategoryBreadcrumbs,CatalogFilters,ProductGallery}.tsx`, `frontend/src/hooks/useCatalog.ts`, `frontend/src/pages/CatalogPage.test.tsx`, `frontend/src/components/storefront/ProductGallery.test.tsx` | `pages/CatalogPage.tsx`, `pages/ProductPage.tsx`, `components/ProductCard.tsx`, `hooks/queries.ts`, `types/api.ts`, `lib/i18n.ts` |
| Customer pages | `frontend/src/hooks/customer.ts`, `frontend/src/pages/{ProfilePage,FavoritesPage,AddressesPage}.tsx`, `frontend/src/features/customer/AddressFormDialog.tsx`, `frontend/src/pages/CustomerPages.test.tsx` | `App.tsx`, phase-one customer auth/pending action, `CheckoutPage.tsx`, `hooks/queries.ts`, `types/api.ts` |
| Orders and acceptance | `frontend/src/pages/OrderTimeline.tsx`, `frontend/src/pages/OrderHistoryPage.test.tsx`, `frontend/e2e/storefront.spec.ts`, `frontend/e2e/fixtures/storefrontApi.ts` | `OrdersPage.tsx`, `OrderDetailPage.tsx`, `App.tsx`, `Layout.tsx`, `hooks/queries.ts`, `types/api.ts`, `lib/i18n.ts` |

---

### Task 1: Unify public catalog filtering and category visibility

**Files:** Modify `backend/app/services/catalog_service.py`, `backend/app/db/repositories/category_repository.py`, `backend/app/db/repositories/product_repository.py`, `backend/app/api/v1/catalog.py`, `backend/app/services/common.py`; create `backend/tests/test_storefront_catalog.py`.

**Interfaces:** Define `CatalogSort = Literal["default", "price_asc", "price_desc", "newest"]` and `CatalogFilters(category_id: int | None, min_price: Decimal | None, max_price: Decimal | None, in_stock: bool, sort: CatalogSort)` in `catalog_service.py`. Produce `list_public_products(session, *, query: str | None, filters: CatalogFilters, page: int = 1, limit: int = 24) -> Page[Product]`; keep current service entry points as wrappers. Add `GET /catalog/products` and `GET /catalog/featured?limit=...`; apply identical filters to all-products, category products and search. The new frontend requests 24; preserve legacy public limit values up to 50 and existing endpoint defaults for compatibility. Keep existing `ProductOut` and `PageOut` shapes.

- [ ] Write `test_catalog_all_products_filters_with_decimal_prices`, `test_catalog_sorts_stably_and_paginates`, `test_catalog_hides_inactive_and_cyclic_ancestors`, `test_catalog_category_tree_requires_active_ancestors`, `test_featured_and_detail_require_active_ancestors`, `test_featured_endpoint_is_empty_without_real_flags`, and `test_catalog_rejects_invalid_price_range`. Assert stock means `stock_qty >= min_order_qty and stock_qty > 0`; category/default ties use `sort_order,id`, price ties use `id`, newest uses `created_at DESC,id DESC`, and search keeps relevance then `id`.

  ```python
  assert in_stock_product_ids == [minimum_satisfied_product.id]
  assert len(first_page.items) == 24
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_storefront_catalog.py -q`. Expected FAIL on missing shared filters, all-products route and ancestor checks.
- [ ] Implement one public visibility predicate used by all-products, category, search, featured and detail reads. A category filter matches that category only; category navigation supplies children separately. Omit invalid/cyclic category branches and their products. Validate `min_price <= max_price` with 422 and use Decimal comparisons in SQL.
- [ ] Rerun the focused tests, `tests/test_catalog_service.py`, and `tests/test_storefront_catalog.py`; expected PASS with stable repeated-page IDs and no inactive branch results.
- [ ] Commit `feat: add filtered public storefront catalog`.

### Task 2: Add customer profile and saved address contracts

**Files:** Create `backend/app/db/models/address.py`, `backend/app/api/schemas/customer.py`, `backend/app/api/v1/profile.py`, `backend/app/api/v1/addresses.py`, `backend/app/services/profile_service.py`, `backend/app/services/address_service.py`, `backend/alembic/versions/3a8d0f24c1e6_storefront_customer_data.py`; modify `backend/app/db/models/user.py`, `backend/app/db/models/__init__.py`, `backend/app/db/repositories/user_repository.py`, `backend/app/bot/handlers/user/checkout.py`, and `backend/app/api/v1/__init__.py`; create `backend/tests/test_storefront_customer_api.py` and `backend/tests/test_storefront_migrations.py`.

**Interfaces:** `ProfileOut` contains exactly `display_name: str`, `phone: str | None`, `language: Literal["uz","ru"]`; `ProfilePatch` accepts those optional fields only, with `extra="forbid"`. `AddressOut` contains `id,label,address_text,address_comment,is_default`; create/patch schemas enforce trimmed lengths 1–60, 1–1000, optional 0–500, and forbid extra fields. Produce `update_profile(session, user, patch) -> User`, `create_address(session,user,payload) -> Address`, `set_default_address(session,user,address_id) -> Address`, and owner-scoped get/list/update/delete operations. Patch allows label/address_text/address_comment only; is_default is changed through the dedicated default endpoint. Initialize legacy display name from trimmed Telegram name, then username, then the generic display label Foydalanuvchi if both are absent. Modify bot checkout name/phone prefills to use profile values without overwriting profile on order submit. Routes are `GET/PATCH /profile`, `GET/POST /addresses`, `PATCH/DELETE /addresses/{address_id}`, `PUT /addresses/{address_id}/default`.

- [ ] Write `test_profile_allowlist_phone_and_language`, `test_profile_old_user_name_backfill`, `test_addresses_owner_limit_and_default`, `test_address_concurrency_limit_and_order_snapshot`, and `test_foreign_address_is_not_found`. Assert 20 is the maximum, first address defaults, deleting a default leaves the rest non-default, and an order's confirmed text/comment remain unchanged after address edits/deletion.

  ```python
  assert twenty_first_address_response.status_code == 409
  assert historical_order.address == original_confirmed_address
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_storefront_customer_api.py tests/test_storefront_migrations.py -q`. Expected FAIL on missing profile/address routes and migration.
- [ ] Add nullable `users.display_name`, backfill with trimmed Telegram first/last name, then make it non-null; update user creation to initialize it. Create `addresses` with user FK and `(user_id)` partial unique index where `is_default=true`. Create/default/delete lock the `users` row before counting/changing addresses; reject a 21st row and never auto-select a replacement default. Address API ownership comes only from `get_current_user`; return 404 for foreign IDs. Reuse phone normalization/validation. Checkout continues receiving only selected address text/comment; saved address ID never enters `CheckoutIn` or order snapshot.
- [ ] Upgrade from phase-two head `2f7c9e13b0d5` and downgrade/upgrade on disposable PostgreSQL; rerun focused tests and `tests/test_phone_validation.py`. Expected PASS with exactly one Alembic head.
- [ ] Commit `feat: add customer profile and saved addresses`.

### Task 3: Share favorite state between the Telegram bot and web API

**Files:** Create `backend/app/services/favorite_service.py`, `backend/app/api/v1/favorites.py`, `backend/app/api/schemas/favorites.py`, `backend/tests/test_favorites_api.py`; modify `backend/app/bot/handlers/user/favorites.py`, `backend/app/api/v1/__init__.py`, and existing favorite repository only if a page/eager-loading query requires it.

**Interfaces:** `GET /favorites?page=1&limit=24` returns `PageOut[ProductOut]`; `PUT /favorites/{product_id}` and `DELETE /favorites/{product_id}` are idempotent. Add `GET /favorites/{product_id}` returning `FavoriteStateOut(is_favorite: bool)` so a product detail can read customer state without contaminating public product cache. Service functions are `list_favorites(session,user_id,page=1,limit=24) -> Page[Product]`, `is_favorite(session,user_id,product_id) -> bool`, `add_favorite(session,user_id,product_id) -> None`, and `remove_favorite(session,user_id,product_id) -> None`.

- [ ] Write `test_favorite_api_is_owner_scoped_and_idempotent`, `test_favorites_page_eager_loads_product_images`, `test_favorite_state_is_separate_from_public_catalog`, and `test_bot_and_web_use_same_favorite_service`. Assert repeated PUT/DELETE succeeds without duplicate rows and a favorite added/removed through either client appears in the other's list for the same Telegram user.

  ```python
  assert repeated_put_response.status_code in (200, 204)
  assert favorite_row_count == 1
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_favorites_api.py -q`. Expected FAIL because customer API routes/service are absent and the bot calls the repository directly.
- [ ] Implement owner-scoped pagination and eager loading through the existing `Favorite` model/repository. Reject inactive or public-ineligible products on add without exposing their data. Route bot list/add/remove through `favorite_service`; do not create another favorites table.
- [ ] Rerun focused tests and existing favorite-related bot tests; expected PASS, including a fresh session response with product image data.
- [ ] Commit `feat: share favorites across bot and storefront`.

### Task 4: Add paginated order history and safe customer timeline

**Files:** Create `backend/app/api/schemas/customer_orders.py`, `backend/app/services/customer_order_service.py`, `backend/tests/test_customer_orders_api.py`; modify `backend/app/api/v1/orders.py` and `backend/app/db/repositories/order_repository.py`.

**Interfaces:** `GET /orders/history?page&limit` returns `PageOut[OrderHistoryItemOut]` with `id,order_number,created_at,status,payment_status,order_type,total`; `GET /orders/{order_id}/timeline` returns only `list[OrderTimelineEventOut(status: OrderStatus, occurred_at: datetime)]`. Produce `list_customer_orders(session,user_id,page=1,limit=24) -> Page[Order]` and `customer_timeline(session,user_id,order_id) -> list[OrderTimelineEventOut]`. Register `/history` before `/{order_id}`. Keep existing `/orders` and `/orders/{id}` response contracts.

- [ ] Write `test_order_history_pages_by_owner`, `test_customer_timeline_is_safe_for_cancelled_and_sparse_history`, `test_foreign_order_timeline_is_not_found`, and `test_public_settings_has_only_allowlisted_customer_fields`. Assert admin ID, admin name and history comment never serialize; sparse history returns no invented timestamp; cancelled is terminal; current status is not falsely marked completed.

  ```python
  assert "changed_by_admin_id" not in timeline_response.text
  assert "comment" not in timeline_response.text
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_customer_orders_api.py -q`. Expected FAIL on missing history/timeline contracts.
- [ ] Query status history using `created_at`, project it to the safe schema, and use the order owner's token user ID for every query. Keep raw ORM history out of schemas. Confirm support/welcome values are exposed only by phase-two `PublicSettingsOut` allowlist; do not add payment/admin settings.
- [ ] Rerun focused tests and `tests/test_order_service.py`; expected PASS with foreign-order isolation and no operator-only fields.
- [ ] Commit `feat: expose customer order history and safe timeline`.

### Task 5: Build the responsive storefront shell and persisted language/theme controls

**Files:** Create `frontend/src/components/storefront/StorefrontHeader.tsx`, `frontend/src/components/storefront/MobileNavigation.tsx`, `frontend/src/components/storefront/LanguageSwitcher.tsx`, `frontend/src/components/storefront/ThemeToggle.tsx`, `frontend/src/components/storefront/SupportLinks.tsx`, `frontend/src/store/theme.ts`, `frontend/src/store/theme.test.ts`, `frontend/src/components/storefront/StorefrontShell.test.tsx`; modify `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/index.css`, `frontend/src/lib/i18n.ts`, and `frontend/src/store/language.ts`.

**Interfaces:** `Layout` composes `StorefrontHeader`, route content and `MobileNavigation`; header shows brand/search/catalog/orders/cart/profile/language on desktop. Mobile navigation shows catalog/cart/orders/profile, with favorites linked from profile. `useTheme()` in `store/theme.ts` exposes `theme: "light" | "dark"` and `setTheme(theme)` and persists preference. Add routes for `/profile`, `/favorites`, `/profile/addresses` while preserving phase-one paths.

- [ ] Write `StorefrontShell.test.tsx` and `theme.test.ts`; assert desktop/mobile nav contents, selected nav `aria-current`, explicit accessible labels, language choice updates `uz`/`ru`, persisted light/dark preference, visible focus, minimum 44px controls and reduced-motion CSS.

  ```typescript
  expect(activeNavLink).toHaveAttribute("aria-current", "page");
  expect(restoredTheme).toBe("dark");
  ```
- [ ] Run `cd frontend && npm test -- src/components/storefront/StorefrontShell.test.tsx src/store/theme.test.ts`. Expected FAIL on missing shell/routes/theme store.
- [ ] Replace the fixed mobile-only layout with a centered responsive shell: two catalog columns on narrow screens and four at wide widths; use a readable neutral surface with the existing violet brand accent. Apply theme classes to storefront and existing cart/checkout/account/dialog surfaces. Preserve a working back affordance in Telegram WebView. Use real `PublicSettings` for optional support presentation; no empty placeholder banner.
- [ ] Rerun focused tests, `npm run typecheck`, and `npm run build`; expected PASS at 390px and 1280px CSS breakpoints with no focus loss.
- [ ] Commit `feat: add responsive Kans storefront shell`.

### Task 6: Implement URL-driven catalog search, filtering, pagination and product gallery

**Files:** Create `frontend/src/components/storefront/CategoryTile.tsx`, `frontend/src/components/storefront/CategoryBreadcrumbs.tsx`, `frontend/src/components/storefront/CatalogFilters.tsx`, `frontend/src/components/storefront/ProductGallery.tsx`, `frontend/src/hooks/useCatalog.ts`, `frontend/src/pages/CatalogPage.test.tsx`, `frontend/src/components/storefront/ProductGallery.test.tsx`; modify `frontend/src/pages/CatalogPage.tsx`, `frontend/src/pages/ProductPage.tsx`, `frontend/src/components/ProductCard.tsx`, `frontend/src/hooks/queries.ts`, `frontend/src/types/api.ts`, and `frontend/src/lib/i18n.ts`.

**Interfaces:** `CatalogQuery` has `q,category,min_price,max_price,in_stock,sort,page`; `useCatalog(query: CatalogQuery)` returns pages, `loadMore`, loading/error state, and `hasMore`. Query keys use normalized URL parameters; pass TanStack Query's `AbortSignal` to Axios. `ProductGallery({images,name})` shows the first valid image initially, thumbnails/swipe for remaining images, and a neutral per-image fallback. Product detail links back to the saved URL/scroll state.

- [ ] Write `test_catalog_debounce_abort_and_back_navigation`, `test_catalog_filters_reset_page_and_append_unique_ids`, `test_category_tree_and_breadcrumb_navigation`, `test_featured_hidden_when_empty`, and `ProductGallery.test.tsx` cases for missing/broken images and image selection. Assert no search before 300ms, old requests receive abort, late results are ignored, page appends keep earlier results and de-duplicate by product ID.

  ```typescript
  expect(searchRequestsBefore300ms).toHaveLength(0);
  expect(new Set(renderedProductIds).size).toBe(renderedProductIds.length);
  ```
- [ ] Run `cd frontend && npm test -- src/pages/CatalogPage.test.tsx src/components/storefront/ProductGallery.test.tsx`. Expected FAIL on absent URL filter state/gallery behavior.
- [ ] Hydrate input from URL (`q`, `category`, `min_price`, `max_price`, `in_stock`, `sort`, `page`); normalize the same values into query keys and requests. Debounce `q` 300ms, cancel stale requests, reset page on any filter change, request 24 items, and append next pages. Provide distinct loading/empty/error/rate-limit/retry states and a clear-filters action. Render configured localized welcome text only when present, all active catalog products independently of category/featured selection, and featured only when actual featured products exist; render root/child category images or neutral fallback. Show only server product data and real images. Detail displays localized text, current/valid old price, unit/SKU/stock/minimum and blocks quantities above stock or below minimum.
- [ ] Rerun focused tests plus `npm run typecheck` and `npm run build`; expected PASS for UZ/RU, query back-navigation, stable pagination and gallery fallback.
- [ ] Commit `feat: build searchable filtered storefront catalog`.

### Task 7: Add profile, favorites and address-book customer pages

**Files:** Create `frontend/src/components/storefront/FavoriteButton.tsx`, `frontend/src/hooks/customer.ts`, `frontend/src/pages/ProfilePage.tsx`, `frontend/src/pages/FavoritesPage.tsx`, `frontend/src/pages/AddressesPage.tsx`, `frontend/src/features/customer/AddressFormDialog.tsx`, `frontend/src/pages/CustomerPages.test.tsx`; modify `frontend/src/App.tsx`, `frontend/src/hooks/queries.ts`, `frontend/src/types/api.ts`, phase-one `frontend/src/lib/pendingCartAdd.ts` and `frontend/src/features/customer-auth/CustomerAuthProvider.tsx`, plus `frontend/src/components/ProductCard.tsx`, `frontend/src/pages/ProductPage.tsx`, `frontend/src/lib/i18n.ts`, `frontend/src/pages/CheckoutPage.tsx`, `frontend/src/features/checkout/CheckoutForm.tsx` and `frontend/src/features/checkout/useCheckoutFlow.ts`.

**Interfaces:** `Profile`, `Address`, `FavoritePage`, and `FavoriteState` mirror Tasks 2–3 exactly. `useCustomerProfile`, `useUpdateCustomerProfile`, `useAddresses`, `useAddressMutations`, `useFavorites`, and `useFavoriteState(productId)` use user-scoped keys. Replace the pending action payload with the discriminated union `PendingCustomerAction = {kind:"cart_add";productId:number;quantity:number;origin:string;mutationKey:string;createdAt:number} | {kind:"favorite_add";productId:number;mutationKey:string;createdAt:number}`; preserve phase-one cart add semantics and one pending action per login dialog.

- [ ] Write `CustomerPages.test.tsx` and `test_customer_cache_isolated_after_account_switch`. Assert profile rejects Telegram/admin edits and retains form values on errors; one pending guest favorite opens phase-one login, executes once after login, cannot be replaced by a second action, and cancel discards it; favorites use server state; add/edit/default/delete address forms enforce lengths; logout/account switch clears personal queries and ignores late responses.

  ```typescript
  expect(checkoutPayload.address).toBe(confirmedAddressText);
  expect(checkoutPayload).not.toHaveProperty("address_id");
  ```
- [ ] Run `cd frontend && npm test -- src/pages/CustomerPages.test.tsx src/lib/api.test.ts`. Expected FAIL on missing customer pages and pending favorite intent.
- [ ] Implement typed query/mutation hooks and localized pages. Do not put customer favorite fields in public catalog cache. On `401/403/offline`, retain unsent field values and show recoverable errors. Prefill checkout name/phone from profile without silently writing checkout edits back to profile; profile language updates the shared `users.language` value used by the bot, while guest language stays a local preference. In checkout, selecting a saved address copies server `address_text` and `address_comment`; editing the address book in another tab does not silently replace the current form. “Save for next time” calls the address API separately. Pickup/preorder omit address; send only confirmed text/comment so phase-one idempotency fingerprints those values; never send a saved address ID, coordinates or a frontend delivery calculation.
- [ ] Rerun focused tests, `npm run typecheck`, and `npm run build`; expected PASS including stale-request isolation after logout.
- [ ] Commit `feat: add customer profile favorites and addresses`.

### Task 8: Show order history, customer timeline and configured support

**Files:** Create `frontend/src/pages/OrderTimeline.tsx` and `frontend/src/pages/OrderHistoryPage.test.tsx`; modify `frontend/src/pages/OrdersPage.tsx`, `frontend/src/pages/OrderDetailPage.tsx`, `frontend/src/hooks/queries.ts`, `frontend/src/types/api.ts`, `frontend/src/components/Layout.tsx`, and `frontend/src/lib/i18n.ts`.

**Interfaces:** `useOrderHistory(page: number)` returns `Page<OrderHistoryItem>`; `useOrderTimeline(orderId: number | undefined)` returns only status/time events. `SupportLinks` derives optional links from `PublicSettings.support_username` and `shop_phone`, and renders work hours/welcome text only when nonempty.

- [ ] Write `OrderHistoryPage.test.tsx` cases `history_is_paginated_and_localized`, `timeline_does_not_invent_future_events`, `cancelled_timeline_is_terminal`, `support_links_hide_invalid_or_empty_values`, and `order_detail_keeps_snapshot_address`. Assert no admin/comment text, missing timestamps stay absent, and links are absent for null/invalid contacts.

  ```typescript
  expect(renderedHistory).not.toContain(adminInternalComment);
  expect(supportLinksForNullSettings).toHaveLength(0);
  ```
- [ ] Run `cd frontend && npm test -- src/pages/OrderHistoryPage.test.tsx`. Expected FAIL on customer timeline/history presentation.
- [ ] Render paginated server order summary and snapshot detail; map only known lifecycle states through UZ/RU dictionaries. Show completed historical events, current status and pending milestones; render cancelled as a terminal branch. If event history is empty/corrupt, show current status only. Build `https://t.me/...`/`tel:` only from validated configured values. Keep checkout available-state/readiness and all money from backend data.
- [ ] Rerun focused tests, `npm run typecheck`, and `npm run build`; expected PASS for order ownership errors and missing optional support fields.
- [ ] Commit `feat: add localized customer order tracking`.

### Task 9: Verify storefront journeys at mobile/desktop, both languages and themes

**Files:** Create `frontend/e2e/storefront.spec.ts` and `frontend/e2e/fixtures/storefrontApi.ts`; modify `frontend/package.json` only if a phase-one script alias is needed. Reuse phase-one Playwright config, browser install and CI wiring.

**Interfaces:** Fixture intercepts all `/api/v1/**` requests with synthetic catalog/profile/favorite/address/order/settings responses and rejects unexpected external requests. Add `test:e2e:storefront` as `playwright test e2e/storefront.spec.ts` if not already present.

- [ ] Add journeys `guest_catalog_to_favorite_login`, `filter_product_back_restores_query`, `profile_address_snapshot_stays_confirmed`, `favorite_syncs_after_login`, and `order_timeline_and_support_use_server_data`. Run each in UZ/RU and light/dark at 390px and 1280px; assert no real Telegram/API calls, nav/accessibility labels, 44px touch targets, product details/gallery, preserved URL/query, account-cache isolation and conditional support.

  ```typescript
  expect(unexpectedExternalRequests).toEqual([]);
  expect(touchTargetBox.width).toBeGreaterThanOrEqual(44);
  ```
- [ ] Run `cd frontend && npm run test:e2e:storefront`. Expected red should be an unmet behavior assertion, not browser startup or network setup.
- [ ] Capture mobile/desktop light/dark screenshots as CI artifacts for visual review; keep fixtures free of fake promotions, fabricated support, invented prices, and demo products. Run `./scripts/test-purchase.sh -q`, backend `ruff check app tests`, `black --check app tests`, `mypy app`, `npm ci`, `npm test`, `npm run typecheck`, `npm run build`, and `npm run test:e2e:storefront`.
- [ ] Expected result: all functional checks pass; no frontend/backend contract drift, forbidden public data, cross-account cache leakage or fabricated content. Record any environment limitation explicitly; screenshot comparison complements but does not replace functional checks.
- [ ] Commit `test: cover storefront and customer cabinet journeys`.

## Execution Handoff

The owner approved the storefront design and directed the team to write the implementation plans and proceed directly through implementation without pausing for another plan approval. Execute tasks in dependency order after the phase-one and phase-two contracts are present; do not add an approval stop between this plan and implementation. Root performs plan self-review and whole-phase review.
