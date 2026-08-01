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

## Deferred/out of scope unless requested later
- Payment gateway *callbacks* for Click/Payme are modeled in the `payment_method` enum and the
  order/payment flow is built to accommodate them, but the spec's actual checkout flow only
  requires cash and manual card-transfer-with-receipt-screenshot — no live Click/Payme API
  integration is implemented (would need merchant credentials not provided).
