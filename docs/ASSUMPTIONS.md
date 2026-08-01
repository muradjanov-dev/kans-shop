# Assumptions & Decisions Log

Per the working agreement: no clarifying questions are asked mid-build. Where the spec was
ambiguous or silent, the decision made and its rationale are logged here.

## Environment
- **Host disk**: `C:` had ~0.2 GB free at project start; the entire project lives on
  `D:\Projects\kans-shop`. Do not create venvs, node_modules, docker volumes, or build output on
  `C:`.
- **Local Python**: host only has 3.13/3.14 installed (no 3.11/3.12). Backend targets **Python
  3.13** for the local dev venv (`backend/.venv`) and **Python 3.12-slim** for the Docker image
  (broadest wheel availability for the pinned stack). Both satisfy the spec's "3.11+" requirement.
- **No local Postgres/Redis binaries** are installed on the host. `docker-compose.yml` runs
  `postgres` and `redis` containers bound to `localhost:5432`/`localhost:6379`; the FastAPI app,
  bot, and Alembic run from the host venv against those containerized services during development
  (fast iteration, no image rebuild per code change). `make dev` documents this flow.
- Dependency versions in `backend/requirements.txt` were not guessed — installed unpinned into a
  clean venv, verified importable, then frozen (`pip freeze`) to the exact resolved versions.

## Product/architecture decisions
- **i18n**: implemented as a small custom middleware reading `locales/uz.json` / `ru.json`
  (dot-path keys, `{placeholder}` interpolation) rather than `aiogram-i18n`, because the spec
  explicitly names `uz.json`/`ru.json` as the locale files (Fluent `.ftl` is aiogram-i18n's native
  format, JSON is not a first-class fit for it).
- **Admin web login**: Telegram Login Widget requires a registered domain callback and HTTPS,
  which isn't available at localhost dev time. Implemented **both**: Login Widget for production
  domains, and a bot-issued one-time 6-digit code (`/admin_login` in the bot DM, 5 min TTL, stored
  in Redis) exchanged for a JWT at `POST /auth/telegram/code` — this is the only path usable in
  local dev and is kept in production as a fallback.
- **JWT library**: `PyJWT` chosen over `python-jose` (smaller, actively maintained, sufficient for
  HS256 access/refresh tokens; spec only requires "JWT", not a specific library).
- **order_number sequence**: a dedicated Postgres `SEQUENCE kans_order_seq` formatted as
  `KANS-{:06d}` in the service layer, rather than a trigger, so the format logic stays visible in
  Python and is easy to test.
- **Superadmin bootstrap**: `ADMIN_IDS` env var (comma-separated Telegram IDs) are upserted into
  the `admins` table as `superadmin` on bot startup, so the very first admin doesn't need to be
  inserted by hand. The user-supplied admin id `917456291` is seeded this way.
- **Mini App auth session length**: access token 30 min / refresh 7 days, per spec's Web Admin JWT
  numbers — reused identically for Mini App tokens for consistency (spec didn't separately specify
  Mini App token TTL).
- **Card payment receipt storage**: receipts are stored the same way as product images — Telegram
  `file_id` (fast bot re-send/preview) *and* a copy under `MEDIA_ROOT/receipts/` with a public
  `receipt_url` (for the web admin panel), mirroring the product-image dual-storage rule the spec
  states explicitly for products.
- **Excel export** uses `openpyxl` directly (spec names this library).
- **Rate limiting** implemented via a Redis fixed-window counter in a lightweight aiogram
  middleware + a FastAPI dependency (no extra framework), per spec's stated limits (20 req/min
  general, 3 checkouts/min).

## Phase 2 — service layer business rules
- **Cart pricing is always live**: `cart_service.calculate_subtotal` prices items at the
  product's *current* `price`, not the `price_snapshot` captured when the item was added.
  `price_snapshot` is still written/updated on every add (per DB_SCHEMA.md) for audit purposes,
  but display/total math always re-reads the live product row — consistent with the spec's
  "narx hech qachon klientdan olinmaydi — har doim bazadan" rule, extended from checkout to the
  cart view as well so the two never disagree.
- **Checkout re-prices from the DB at checkout time**, independent of whatever the cart showed —
  `order_service.checkout` locks each product row (`SELECT ... FOR UPDATE`, ordered by
  `product_id` to prevent cross-checkout deadlocks) and uses that row's live `price`/`stock_qty`.
- **`min_order_amount` does not apply to `preorder`** orders: preorder is a manual
  "a manager will call you back" flow (no payment collected, no address), not a self-checkout,
  so the minimum-basket guard is skipped for it. Delivery and pickup both enforce it.
- **`preorder` payment_method defaults to `cash`** as a placeholder — the enum has no "not
  applicable" value and the bot never asks a preorder customer for a payment method (spec 5.5).
- **Order status transitions are a fixed graph** (`order_service.ALLOWED_TRANSITIONS`):
  new→confirmed→preparing→{delivering,completed}→completed. Skipping a step (e.g. new straight to
  delivering) raises `OrderAlreadyProcessedError`. `cancel_order` is reachable from any
  non-terminal status and restores `stock_qty`/`sold_count` on the affected products.
- **Stock-safety is verified with a real concurrency test**, not just code review:
  `tests/test_order_service.py::test_concurrent_checkouts_never_oversell_stock` runs two
  independent DB connections racing to buy the last unit of a product via `asyncio.gather` and
  asserts exactly one succeeds — this is the Definition-of-Done item "Qoldiq yetmasa buyurtma
  yaratilmaydi (race condition test qilingan)".
- **Test database**: a separate `kansshop_test` Postgres database (not `kansshop`) is used by
  the pytest suite (`TEST_DATABASE_URL`, defaults to `kansshop_test` on the same local Postgres
  container). Schema is built once per test session directly from `Base.metadata` (not via
  Alembic) for speed; each test runs inside a SAVEPOINT that's rolled back afterward, except the
  dedicated concurrency test which needs real cross-connection commits and manages its own data.

## Phase 4 — cart, checkout FSM, receipts
- **Checkout FSM sends sequential new messages rather than editing in place.** Catalog/cart
  browsing (Phase 3, and cart in this phase) edit the same message for a scrollable-app feel,
  but the checkout wizard mixes inline keyboards with two reply-keyboard steps (phone via
  `request_contact`, address via `request_location`) that Telegram cannot attach to an edited
  message — so every step in the wizard sends a fresh message for consistency, not just those two.
- **"⬅️ Orqaga" is not offered on the phone and address steps** (reply-keyboard-based, per
  above) — only "❌ Bekor qilish". All inline-keyboard steps (name, address comment, comment,
  payment, receipt, confirm) do support back. Documented gap vs. the spec's "har qadamda orqaga
  va bekor qilish", justified by reply-keyboard/inline-keyboard being mutually exclusive on one
  message; the user can simply retype instead of using "back" at those two steps.
- **"✏️ O'zgartirish" at the final confirmation restarts the whole wizard** from order-type,
  rather than jumping to edit one specific field. Field-level re-entry would need materially more
  state-machine branching for marginal benefit at this stage.
- **`product_name_snapshot` is captured in the customer's checkout-time language** (`uz` or
  `ru`), since `order_items` has a single snapshot column (per docs/DB_SCHEMA.md), not one per
  language. `order_service.checkout()` takes a `lang` parameter for this.
- **Receipts mirror the product-image dual-storage pattern** (Telegram `file_id` + a copy on
  disk under `MEDIA_ROOT/receipts/`), but the disk copy is only written *after* the order is
  created (inside the confirm handler), because the filename is keyed by `order.id`, which
  doesn't exist yet while the user is still in the `uploading_receipt` FSM step.
- **Preorder skips the payment step entirely**; `payment_method` defaults to `cash` internally
  for those orders (enum has no "n/a" value — see Phase 2 assumption on this).

## Phase 5 — admin order notifications, status flow, message customer
- **Each admin's copy of the order card is localized to that admin's own language**, not a
  fixed `uz`. `admins` has no `language` column, but every admin is also a `users` row (created
  automatically on first bot contact via `UserRegistrationMiddleware`), so `order_notifications.py`
  looks up each admin's `users.language` individually when sending/editing their copy — two
  admins can see the same order in two different languages.
- **Race safety**: `orders.admin_message_ids` (JSONB, built in Phase 2) maps
  `{admin_telegram_id: message_id}`. Any status-changing action re-renders *every* admin's copy
  via `sync_admin_cards`, stamping who acted and when. A second admin tapping a now-stale button
  hits `order_service`'s status-transition guard (`OrderAlreadyProcessedError`), which is caught
  and turned into `answer_callback_query(show_alert=True)` naming the admin who already handled
  it — the first commit wins, matching the spec's "ikki admin bir vaqtda" requirement.
- **"💬 Mijozga yozish" is a two-option sub-menu**, not a single action: a URL button opens the
  direct Telegram chat (`t.me/<username>` or `tg://user?id=` if no username), and a second
  "✍️ Bot orqali yozish" button starts a short FSM (`AdminOrderStates.writing_to_customer`) that
  relays one typed message from the admin to the customer, prefixed so the customer knows it's
  from the shop. This matches the spec's "URL tugma ... qo'shimcha: admin bot orqali ham xabar
  yuborishi mumkin".
- **Cancel is available at any non-terminal status** (new/confirmed/preparing/delivering), not
  only at `new` — `order_service.cancel_order` already supports this (Phase 2) and restores
  stock regardless of which status it's cancelled from.
- **`ORDERS_CHANNEL_ID`** (optional channel/group posting alongside per-admin DMs) is defined in
  `.env` but not wired up in this phase — only direct messages to each notification-enabled admin
  are sent. Can be added later as one more send target inside `notify_admins_new_order`.

## Phase 6 — product/category CRUD, stats, broadcast, users, settings
- **Role gating**: product/category CRUD, broadcast, settings, and user management (block/
  unblock) are restricted to `manager`+`superadmin` (`MANAGEMENT_ROLES` in
  `app/bot/utils/admin_guard.py`), matching DB_SCHEMA.md's role matrix. Order actions (Phase 5)
  and viewing stats stay open to every active admin including `operator`, since the spec
  explicitly scopes `operator` to "buyurtmalarni ko'rish va status o'zgartirish" — that's
  everything Phase 5 does, and stats-viewing isn't a mutation.
- **Category deletion is blocked** if the category has any products (active or inactive) or any
  child categories — admin must reassign/delete those first. This mirrors the DB's real
  constraint (`products.category_id` is `ON DELETE RESTRICT`) as a friendly in-bot check instead
  of surfacing a raw FK-violation error.
- **New-product images are held as Telegram `file_id`s in FSM state** during the add-product
  wizard and only written to disk (`MEDIA_ROOT/products/{product_id}/`) after the `Product` row
  exists, for the same reason as receipts in Phase 4: the on-disk path is keyed by an id that
  doesn't exist yet mid-form.
- **Stats**: `orders_count` counts every order created in the period regardless of status (a raw
  activity number); `revenue`/`avg_check` exclude cancelled orders; the top-10 list aggregates
  `order_items.product_name_snapshot` (what was actually sold, by name at sale time) rather than
  joining to the live `products` table, so renamed/deleted products still show correctly in
  historical stats.
- **Broadcast pacing**: 20 msg/sec (spec says "25 msg/sek limit" — 20 is a deliberately
  conservative margin under Telegram's own ~30/sec global cap), progress message updated every
  20 sends (not per-message, to avoid flooding the *edit* rate too), `TelegramRetryAfter`
  respected with one retry, `TelegramForbiddenError` marks the user `is_blocked=true` and counts
  as failed. Audience "active" = `last_active_at` within the last 30 days.
- **Settings editor exposes 9 of the 11 seeded keys** — `welcome_text_uz`/`welcome_text_ru` are
  left out of the bot's quick-edit list (longer free-form text better suited to the Phase 9 web
  admin panel's form UI) but remain fully readable/writable via `setting_repository` already.
- **"🌐 Web admin panel" menu button** links to `{WEBAPP_URL}/admin` even though that panel is
  Phase 9's deliverable and doesn't exist yet — it's a stable placeholder link, not a stub
  removed later.

## Phase 7 — FastAPI REST API, initData auth, webhook
- **`PATCH`/`DELETE /cart/items/{id}`**: `{id}` in the spec's endpoint list is interpreted as
  `product_id`, not `cart_item.id` — matches `cart_service`'s existing interface (which already
  keys on `user_id` + `product_id`) and matches what a Mini App cart screen actually has on hand
  (the product being displayed), no extra lookup needed.
- **Admin-panel login without HTTPS/Telegram WebApp context**: the web admin panel (Phase 9)
  can't use `initData` validation (it's not opened from inside Telegram). Added a fallback:
  `/admin_login` in the bot issues a 6-digit code (Redis, 5 min TTL, `app/bot/handlers/admin/
  auth.py`), exchanged via `POST /auth/telegram/code` for the same JWT pair the Mini App gets.
- **Broadcast send is a `BackgroundTasks` fire-and-forget**, not synchronous-in-request or a
  separate worker/queue: `POST /admin/broadcasts` creates the `Broadcast` row and returns `202`
  immediately; the actual paced send (still 20 msg/sec, same algorithm as the bot's composer
  flow) runs after the response via FastAPI's `BackgroundTasks`, in its own DB session (the
  request-scoped session is already closed by then). `GET /admin/broadcasts/{id}` polls status.
  A real queue (Celery/RQ) would survive a process restart mid-send; not worth the added infra
  for this product's traffic volume, but noted here in case broadcasts grow large enough to matter.
- **Notification helpers shared between bot and API**: `_notify_customer` (order status DMs) and
  the broadcast pacing loop (`_send_one`/`_run_broadcast`) were bot-handler-private in Phase 5/6.
  Both the admin API's `PATCH /admin/orders/{id}/status` and `POST /admin/broadcasts` need the
  identical logic, so they were promoted to `app/bot/services/order_notifications.py` (
  `notify_customer_status_change`) and a new `app/services/broadcast_service.py` (`run_broadcast`,
  with progress-reporting as an optional callback so the bot's Telegram-message-editing UI stays
  bot-specific while the send/retry/pacing core is shared) rather than duplicated.
- **Rate limiting**: implemented as Starlette middleware (`app/api/rate_limit.py`) using Redis
  `INCR`+`EXPIRE` sliding-ish windows — 20 req/min/IP general, 3 req/min/IP on `POST /api/v1/
  orders` specifically (checkout), per spec section 10. Applied only under `/api/v1`; `/webhook`
  and `/media` are exempt (webhook has its own secret-token gate, media is static reads).
- **`products_count` denormalization**: the bot's product editor never hard-deletes a product
  (only edits fields/stock/active-flag), so it never had to keep `categories.products_count` in
  sync on delete. The admin API adds the first real hard-delete (`DELETE /admin/products/{id}`,
  intentionally supported at the schema level — `order_items.product_id` is `ON DELETE SET NULL`
  precisely so historical orders survive a product's removal) and the first category-reassignment
  (`PATCH /admin/products/{id}` with a new `category_id`), so both paths now increment/decrement
  `products_count` on the old/new category to keep the counter accurate.
- **`app/db/repositories/category_repository.py::list_children` bug found via live smoke test**:
  used `Category.parent_id.is_(parent_id)`, which only produces valid SQL when `parent_id is
  None` (`IS NULL`) — Postgres rejects `IS $1` for a bound non-NULL parameter. This silently broke
  category deletion (and the bot's own subcategory listing) any time a category with real
  subcategories was checked; nothing in the existing test suite exercised that path against a
  live category with children. Fixed to a plain `==` comparison, which SQLAlchemy compiles to
  `IS NULL` for a literal `None` and to a normal bound-parameter `=` otherwise.

## Phase 8+ — scope change: web admin panel dropped, Mini App is customer-only
- **Web admin panel (originally Phase 9) was cancelled by the user mid-build**: "web admin panel
  no need, i need only admin panel that controls everywhere from bot." All admin control stays
  exclusively in the Telegram bot (Phases 5–6: orders, products, categories, stats, broadcasts,
  users). The Mini App (Phase 8) is customer-facing only — catalog, product, cart, checkout,
  orders — with no admin UI.
- **Phase 7's `/api/v1/admin/*` REST routes were NOT deleted** even though their originally
  intended consumer (the web admin panel) no longer exists. They're complete, tested, and
  harmless to keep (no dead-code/stub issue — every handler is fully implemented), and ripping
  out a full day's already-verified work on a scope change alone seemed like the wrong call
  without being asked to. Bot-based admin control (Phases 5–6) is what's actually wired up and
  used; the admin API is unused-but-functional infrastructure, should it be wanted later.
- **Deploy notification**: per the user's request ("after finish deploy and send notification to
  admins... from bot"), `app/main.py`'s lifespan now calls `notify_admins_deploy()` once, right
  after the webhook is registered — i.e., every time the production app starts up after a real
  deploy or restart. It only messages active admins (never customers), and only fires in webhook
  mode (`WEBHOOK_URL` set) — `bot_polling.py` (local dev) does not trigger it. This satisfies the
  request without me actually running the Railway deploy myself (still no Railway credentials —
  see docs/DEPLOY.md, which the user runs manually).
- **Product image management for existing products**: the Phase 6 admin bot could only attach
  photos while *creating* a new product (`products_form.py`) — there was no way to add photos to
  a product afterward. `AdminProductActionCallback`'s docstring already anticipated an
  `"add_photo"`-style action that was never implemented. Closed that gap: `products_edit.py` now
  has a "🖼 Rasmlar (N)" button opening the same upload-then-finish flow, reusing a newly shared
  `persist_product_images()` (promoted out of `products_form.py`, parameterized with
  `start_index` so it can append to a product's existing images instead of only writing from
  index 0). Caught and fixed the same "stale in-memory relationship collection" class of bug
  encountered earlier in Phase 7: after `session.add()`-ing a new `ProductImage` by FK column
  only (not through the `.product` relationship attribute), the already-loaded `product.images`
  collection doesn't reflect it without an explicit `session.refresh(product, ["images"])`.
- **Checkout phone validation gap closed**: `order_service.checkout()` never validated
  `customer_phone` format — the bot's checkout FSM validates before calling it
  (`is_valid_uz_phone`), but the Phase 7 API's `POST /orders` didn't, so a Mini App client could
  submit garbage phone numbers. Added a Pydantic `field_validator` on `CheckoutIn.customer_phone`
  reusing the bot's existing `normalize_uz_phone`/`is_valid_uz_phone` (`app/bot/utils/helpers.py`)
  rather than a second regex — raises plain `ValueError` (not a `KansShopError` subclass), since
  Pydantic only auto-wraps `ValueError`/`TypeError`/`AssertionError` from validators into a
  catchable `ValidationError`; anything else would bypass FastAPI's request-validation handling
  entirely and surface as a raw 500 instead of a clean 422.

## Phase 8 — Mini App (React/Vite/Tailwind)
- **`npm audit` flags 2 high-severity findings in `react-router-dom@7.18.2`** (GHSA-qwww-vcr4-c8h2,
  "RSC Mode CSRF Bypass Allows Action Execution Before 400 Response"). Reviewed and accepted:
  the advisory is specific to React Router's RSC (React Server Components) / server-actions mode
  — this app never imports `unstable_RSCStaticRouter`, defines no `action()`/`loader()` server
  functions, and uses plain client-side `BrowserRouter` against a separate FastAPI backend, so
  the vulnerable code path is never reached. The fix (`npm audit fix --force`) would downgrade to
  7.11.0 or require migrating off `react-router-dom` entirely onto the unified `react-router`
  v8 package (which dropped the `-dom` split) — not worth the churn/regression risk for a
  vulnerability class this app doesn't exercise. Revisit if the app ever adopts RSC/framework mode.

## Phase 10 — final wiring, infra fixes, and Docker verification
- **`docker-compose.yml`'s `nginx` service originally bind-mounted `./frontend/dist`**, which
  wouldn't exist on a fresh clone until someone manually ran `npm run build` — breaking the "just
  `docker-compose up`" requirement. Added `frontend/Dockerfile` (multi-stage: `node:24-alpine`
  build → `nginx:1.27-alpine` serving the built `dist/`) and switched the compose service to
  `build: context: ./frontend` instead. `VITE_API_BASE_URL` is baked in at Docker build time via
  a build arg, defaulting to the relative `/api/v1` (nginx proxies same-origin in production);
  Railway needs it set to the API's full public URL instead since the two services get separate
  domains there — documented in docs/DEPLOY.md.
- **pytest's `kansshop_test` database bootstrap was undocumented-and-manual**: `conftest.py`
  connected straight to `kansshop_test` assuming it already existed, but nothing in the repo ever
  created it — it only existed because it was created once by hand earlier in the build and
  silently kept working across sessions. This surfaced as 39 test failures
  (`InvalidCatalogNameError`) after a full Docker volume reset (see below) wiped it. Fixed:
  `conftest.py`'s `test_engine` fixture now connects to the `postgres` maintenance database first
  and issues `CREATE DATABASE kansshop_test` if it's missing (can't run inside a transaction, so
  this uses a short-lived `AUTOCOMMIT`-isolation connection) — `make test` / `pytest` now works
  against a completely fresh Postgres server with zero manual setup.
- **Host environment ran out of disk space on `C:` mid-build** (`docker_data.vhdx`, Docker
  Desktop's WSL2 data disk, had grown to 14 GB from this session's image builds/pulls, filling the
  drive to 0 bytes free and blocking all shell command execution). Fixed by deleting that file
  (user-authorized — it's fully reproducible: base images, containers, build cache, nothing
  irreplaceable) after stopping Docker Desktop/WSL to release the lock. This is a host-machine
  issue, not a project one — the project itself already lives on `D:` (see "Environment" above),
  but Docker Desktop's own WSL2 disk cache lives on `C:` by default regardless and doesn't follow
  the project's drive. Relocating it permanently requires Docker Desktop → Settings → Resources →
  Advanced → "Disk image location" → a `D:` path — a GUI-only setting with no safe CLI/config-file
  equivalent found.
- **Full stack verified end-to-end via `docker compose up -d --build`** against a completely reset
  Postgres/Redis (fresh volumes): migrations auto-apply (`entrypoint.sh` → `alembic upgrade head`),
  `python -m app.db.seed` populates the catalog, and nginx correctly serves the Mini App SPA,
  proxies `/api/*` to the API container, proxies `/webhook`, and falls back to `index.html` for
  client-side routes (`/product/1` → 200, not 404). No errors in any container's logs.

## Deferred/out of scope unless requested later
- Payment gateway *callbacks* for Click/Payme are modeled in the `payment_method` enum and the
  order/payment flow is built to accommodate them, but the spec's actual checkout flow only
  requires cash and manual card-transfer-with-receipt-screenshot — no live Click/Payme API
  integration is implemented (would need merchant credentials not provided).
