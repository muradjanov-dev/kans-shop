# Kans Shop Purchase Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one store's Telegram and browser purchase journey reliable, from adding a product through order creation and private payment receipt review.

**Architecture:** Keep the current FastAPI/aiogram shared services and PostgreSQL cart as the source of truth. Add purpose-bound customer codes, transaction locks and replay records, a server quote, and private receipt storage; React consumes these contracts without duplicating purchase rules. Keep web admin UI and the visual storefront overhaul in later separately designed phases.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3, SQLAlchemy 2 async, Alembic, PostgreSQL 16 for tests, Redis 7, React 19, TypeScript, Vite, TanStack Query, Zustand; frontend test additions use Vitest, Testing Library and Playwright with Node 24.

**Spec:** [Approved purchase design](../specs/2026-10-09-kans-shop-purchase-design.md), approved by the owner on 2026-10-09. Read both documents. The owner also approved this implementation plan on 2026-10-09. Execution waits for agreement of phases 2 and 3, as the owner requested, then proceeds autonomously across all phases.

## Global Constraints

- One store; every purchasing account is a verified Telegram identity. Anonymous catalog browsing is allowed; no guest cart or anonymous checkout.
- Keep `CartOut` and existing catalog/cart/order URL paths; new HTTP contracts are additive with the specified legacy exceptions.
- Customer codes: eight random decimal digits, 300-second TTL, at most one issuance per user per 60 seconds, five exchanges per trusted client IP per 300 seconds. Private bot chat only; atomically consume; separate customer/admin namespaces.
- Preserve configured JWT TTLs, default access 30 minutes and refresh seven days. No browser-supplied user ID or role grants.
- Pending add expires after 24 hours; cart replay markers live at least seven days. Add keys and checkout keys are UUIDs scoped to the authenticated user.
- Receipts: JPEG/PNG/WebP/PDF, maximum 5 MiB, verified content, owner upload, owner/active-order-admin read, private caching. Upload means `receipt_uploaded`, not `paid`.
- Quote confirms cart contents as well as total. All price arithmetic is server `Decimal`; money is JSON decimal strings in new frontend contracts.
- No production tokens, real orders, payments, broadcasts, or production databases in automated tests. Tests create/drop schema and must use explicitly disposable services.
- Migration, payment, pricing, roles, secrets and CI/deploy changes require owner release review under `AGENTS.md`; plan review does not approve release.
- Product/catalog media and shared Netcup PostgreSQL/Redis remain intact. Changes to server configuration are limited to Kans Shop's mounts and its Caddy site block, reviewed before apply.
- Owner deferred real delivery/minimum/payment-launch settings on 2026-10-09. Keep implementation moving; missing values do not block a software release with explicit readiness status. New checkout stays unavailable until the owner supplies real settings in web admin. No inferred fee, demo card or automatic gateway enabling.
- Execution preference already supplied: GPT-6 Luna with max reasoning, subagents in parallel where task dependencies and file ownership permit. Preserve that preference; do not ask for the method again.

## Review Focus

1. React StrictMode/remount after a successful-but-unacknowledged add must replay the same key without incrementing twice — Task 9.
2. An empty newly created cart must serialize `items=[]` without lazy I/O, just like a cart containing photos — Task 1.
3. Two different baskets with the same total must require renewed confirmation — Tasks 4 and 5.
4. A replaced receipt must invalidate an admin's stale acceptance action — Tasks 7 and 8.
5. Rolling back the app image must not expose old or newly written legacy receipt paths — Task 12.

## File Responsibilities

Paths below are relative to `kans-shop/`. Existing routes, models and frontend types remain in their current modules. Create focused files rather than growing `order_service.py` or `CheckoutPage.tsx` into another subsystem.

| Area | New focused files | Existing integration points |
| --- | --- | --- |
| API tests | `backend/tests/api_helpers.py`, `backend/tests/test_cart_api.py`, `scripts/test-purchase.sh` | `backend/tests/conftest.py`, CI |
| Customer codes | `backend/app/services/customer_auth_service.py`, `backend/app/bot/handlers/user/web_login.py`, `backend/tests/test_customer_auth.py` | auth routes, bot router/commands, rate limiter |
| Locking and add replay | `backend/app/db/models/cart_mutation.py`, `backend/app/db/repositories/cart_mutation_repository.py`, `backend/app/services/purchase_locks.py`, `backend/app/services/cart_replay_service.py` | user/cart repository, cart service/API |
| Quote | `backend/app/services/checkout_settings.py`, `backend/app/services/checkout_quote.py`, `backend/app/api/schemas/checkout.py` | settings and order routes, bot summaries |
| Checkout orchestration | `backend/app/services/purchase_service.py`, `backend/app/services/after_commit.py` | order service/repository, API dependency, DB middleware |
| Receipts | `backend/app/services/receipt_storage.py`, `backend/app/services/receipt_service.py`, `backend/app/api/v1/receipts.py` | order fields/schema, bot upload/read, static media mount |
| Manual payment | `backend/app/services/manual_payment_service.py`, `backend/app/api/v1/admin/payments.py` | admin callback/keyboard, admin router |
| Browser purchase | `frontend/src/features/customer-auth/`, `frontend/src/lib/pendingCartAdd.ts`, `frontend/src/hooks/useCartActions.ts` | auth store, Axios client, cart/product/layout pages |
| Checkout UI | `frontend/src/features/checkout/`, `frontend/src/hooks/checkout.ts` | checkout/order pages and API types |
| Verification and release | `frontend/src/test/`, `frontend/e2e/`, `deploy/kans-shop.private-media.override.yml`, `deploy/kans-shop.caddy.snippet`, `backend/scripts/migrate_private_receipts.py`, `docs/RELEASE_PURCHASE.md` | source Compose/nginx, image build, existing Netcup workflow |

## Execution Dependencies

Task 1 starts execution and establishes a usable backend test command. Tasks 2 and 3 can then run concurrently; only Task 2 owns auth/rate-limit files and only Task 3 owns purchase model migration and cart changes. Task 4 follows Task 3. Tasks 5 and 6 run in order because they share order/payment transaction interfaces. Tasks 7 then 8 share receipt/order fields and stay sequential. Task 9 may run alongside backend Tasks 4–8 after Tasks 2/3 publish their contracts; it owns frontend files. Task 10 follows Task 9 and backend Tasks 4–8. Tasks 11/12 complete integration and release preparation.

Use at most three child slots plus the root. Review and commit each tested deliverable. Do not run two writers against the same file, or share test containers between workers. Plan self-review is performed by the root, not delegated.

At execution time use `superpowers:using-git-worktrees` to prepare a clean checkout from the verified `origin/main`; do not implement on the stale `codex/agent-context` branch. Bring the approved spec and this plan into that checkout as documentation commits. Creating a worktree, installing dependencies and product edits happen after plan review.

## Task 1: Repair cart serialization with real HTTP regression coverage

**Files:** Modify `backend/app/db/repositories/cart_repository.py`, `backend/app/core/config.py`, `backend/tests/conftest.py`, `.github/workflows/ci.yml`; create `backend/tests/api_helpers.py`, `backend/tests/test_cart_api.py`, `scripts/test-purchase.sh`.

**Interfaces:** Produce `make_api_case(test_engine: AsyncEngine) -> AsyncIterator[ApiCase]` as an async context manager in `api_helpers.py`. `ApiCase` holds `client: httpx.AsyncClient`, `session_maker`, `user_id`, `other_user_id`, `product_id`, `token`, `other_token`, and a fake bot. HTTP requests use fresh committed sessions; synthetic seeds are committed before a request, and case data is cleaned afterward. Existing savepoint service tests remain supported.

- [ ] Write `test_cart_api_serializes_images_in_fresh_sessions`, `test_new_empty_cart_serializes` and `test_cart_api_isolates_users`. Create a saved product image and independently request add, GET, update, remove and clear; assert nested image URLs, quantities, subtotal and count. Assert an empty cart returns `items == []`, `items_count == 0`; another user's GET returns its own empty cart.

  ```python
  assert added.status_code == 201
  assert fresh_get.json()["items"][0]["product"]["images"][0]["url"] == image_url
  assert empty_get.json()["items"] == []
  assert empty_get.json()["items_count"] == 0
  ```
- [ ] Add the safe runner as part of this regression fixture: launch uniquely named ephemeral PostgreSQL 16 and Redis 7 containers on random loopback ports; export synthetic settings and explicit `TEST_DATABASE_URL`, clean only those containers with a trap. Reject non-loopback test DBs and database names outside `kansshop_test*` before the existing destructive schema fixture runs. Use a Python 3.12 venv with the existing `backend/requirements.txt`. Add `ENV_FILE` to Settings, preserving its production default and selecting a temporary empty env file in tests; provide synthetic `BOT_TOKEN`, `JWT_SECRET`, `WEBHOOK_SECRET`, `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`, empty webhook/admin/channel settings and temporary public/private media roots. No real `.env` or Telegram credential enters test Settings.
- [ ] Run `./scripts/test-purchase.sh tests/test_cart_api.py -q`. Expected red: response validation/lazy load failure for the photo or empty cart, not an infrastructure connection failure. The app is built with `create_app()` without entering real lifespan; fake `app.state.bot`, session factories and Redis are injected so no Telegram setup/webhook runs.
- [ ] Load `Cart.items -> CartItem.product -> Product.images` eagerly with `populate_existing=True`. Initialize newly created cart items to an empty collection. Preserve `CartOut` and current prices/counts. Add isolated Redis to backend CI because the HTTP middleware uses Redis directly.
- [ ] Repeat that command and existing `tests/test_cart_service.py`; expected all pass, with every response tested across fresh sessions.
- [ ] Stage only this task's listed files and commit `fix: eagerly load cart response relationships`.

All later backend task commands use this runner with their exact pytest paths; each invocation owns independent test services.

## Task 2: Provide private customer-code login and atomic admin-code consumption

**Files:** Create `backend/app/services/customer_auth_service.py`, `backend/app/bot/handlers/user/web_login.py`, `backend/tests/test_customer_auth.py`; modify `backend/app/api/v1/auth.py`, `backend/app/api/schemas/auth.py`, `backend/app/api/rate_limit.py`, `backend/app/core/config.py`, `backend/app/bot/handlers/user/__init__.py`, `backend/app/bot/handlers/user/start.py`, `backend/app/bot/handlers/admin/auth.py`, `backend/app/bot/utils/commands.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `issue_customer_code(redis: Redis, telegram_id: int) -> str` and `consume_customer_code(redis: Redis, code: str) -> int` in the new service. Produce `POST /api/v1/auth/customer/code` accepting `{code: str}` and returning existing `TokenOut`. Use `customer_login:code:<code>`, `customer_login:user:<telegram_id>` and an issuance throttle namespace; keep `admin_login:` purpose separate. Produce `trusted_client_ip(request: Request) -> str` in the rate limiter; trusted proxy addresses come from explicitly parsed `TRUSTED_PROXY_CIDRS`, never a wildcard.

- [ ] Write `test_customer_code_contract`, `test_private_chat_required`, `test_customer_code_one_winner`, `test_customer_code_collision_and_reissue`, `test_customer_and_admin_codes_cannot_cross`, and `test_code_rate_limits`. Assertions include `len(code)==8`, `code.isdecimal()`, TTL `300`, reissue within `60` seconds rejected, old code invalid after permitted reissue, exactly one successful concurrent exchange, sixth attempt in `300` seconds rejected, untrusted forwarded headers ignored, and blocked users rejected. Use injected time and fake Telegram methods; Redis atomicity tests use the isolated real Redis.

  ```python
  assert len(code) == 8 and code.isdecimal()
  assert 0 < await redis.ttl(f"customer_login:code:{code}") <= 300
  assert sum(response.status_code == 200 for response in raced_exchanges) == 1
  assert sixth_exchange.status_code == 429
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_customer_auth.py -q`; expected red because the customer endpoint/issuer is absent.
- [ ] Implement issuance/reissue as one atomic Redis operation with collision protection and per-user throttling. Consume atomically with `GETDEL` or a Lua script. Issue only in private chat; support `start=web_login` by dispatching to the same private issuer after first-time language selection. Add `/web_login` to commands. Validate the database user before issuing tokens with the current token helpers.
- [ ] Restrict `/admin_login` to private chat and replace its GET-then-DEL exchange with atomic consumption. Keep admin issuance guards and namespaces. Apply code exchange limits to both code endpoints. Use existing general API limits additionally; trust only the immediate configured proxy peer and extract its sanitized forwarded chain consistently.
- [ ] Rerun the task tests and `tests/test_security.py`; expected pass and no requests to Telegram. Assert neither a submitted Telegram ID nor a submitted admin flag can determine identity.
- [ ] Commit `feat: add private customer browser login codes`.

## Task 3: Add purchase metadata, common cart locks and safe add replay

**Files:** Create `backend/alembic/versions/1e6b8d02a9c4_purchase_reliability_metadata.py`, `backend/app/db/models/cart_mutation.py`, `backend/app/db/repositories/cart_mutation_repository.py`, `backend/app/services/purchase_locks.py`, `backend/app/services/cart_replay_service.py`, `backend/tests/test_cart_replay.py`, `backend/tests/test_purchase_migrations.py`; modify `backend/app/db/models/__init__.py`, `backend/app/db/models/order.py`, `backend/app/db/repositories/user_repository.py`, `backend/app/db/repositories/cart_repository.py`, `backend/app/services/cart_service.py`, `backend/app/services/order_service.py` (checkout entry lock), `backend/app/db/repositories/product_repository.py` (refresh locked stock), `backend/app/api/v1/cart.py`, `backend/tests/test_migrations.py`.

**Interfaces:** Produce `lock_customer_cart(session: AsyncSession, user_id: int) -> Cart`, `add_item_once(session: AsyncSession, *, user_id: int, product_id: int, quantity: int, mutation_key: UUID | None) -> Cart`. Locks are user row, active cart row, then any product rows in ascending ID order. Repository helpers flush but never commit or start a nested transaction.

Migration revision `1e6b8d02a9c4` follows verified head `9c1f4a7be2d0`. `cart_mutations` records `user_id`, `mutation_key` (36-char UUID), `request_fingerprint` (64-char SHA256 hex) and `created_at`; unique `(user_id, mutation_key)`. Add nullable order `checkout_key`, `checkout_fingerprint`, `payment_instructions` JSONB, `receipt_storage_key`, `receipt_content_type`, `payment_reviewed_by_admin_id` FK and `payment_reviewed_at`; `receipt_version` is non-null with server default `0`. Unique `(user_id, checkout_key)` allows existing null keys. Leave existing enums and orders intact.

- [ ] Write `test_add_replay_applies_delta_once`, `test_add_key_payload_conflict`, `test_cart_mutations_serialize_with_checkout`, `test_minimum_and_zero_quantity`, and migration roundtrip tests from the old head with synthetic historical orders. Assert same-key adds preserve one increment even after a lost response, a changed product/quantity returns 409, another user can use the same UUID independently, positive quantity below minimum is rejected on update, zero removes, and preexisting order rows survive upgrade.

  ```python
  assert replay.json()["items"][0]["quantity"] == original_quantity + requested_delta
  assert conflict.status_code == 409
  assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
  assert historical_order_ids_after_upgrade == historical_order_ids_before_upgrade
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_cart_replay.py tests/test_purchase_migrations.py -q`; expected missing fields/helpers and duplicate increment failures.
- [ ] Implement the additive migration and models; use user locking to serialize first cart creation and replay insertion. Existing cart add/update/remove/clear operations use the same lock helper. The new API add adapter optionally accepts `Idempotency-Key`; legacy callers retain current add behavior. Fingerprint normalized product ID and quantity; conflict returns `IDEMPOTENCY_CONFLICT`, replay returns the current cart even if it has subsequently changed. No marker is pruned before seven days.
- [ ] Rerun task tests, Task 1 API tests and existing cart service tests; expected pass. Migration tests use a separate disposable database from metadata/create_all tests, and structural tests still find one head.
- [ ] Commit `feat: make cart additions and purchase metadata retry safe`.

## Task 4: Define typed purchase settings and server quote

**Files:** Create `backend/app/services/checkout_settings.py`, `backend/app/services/checkout_quote.py`, `backend/app/api/schemas/checkout.py`, `backend/tests/test_checkout_quote.py`; modify `backend/app/api/v1/settings.py`, `backend/app/api/schemas/settings.py`, `backend/app/api/v1/orders.py`, `backend/app/core/exceptions.py`, `backend/app/services/payment_service.py`.

**Interfaces:** Produce `load_checkout_settings(session: AsyncSession) -> CheckoutSettings`; numeric settings are `Decimal | None`, shop-open is `bool | None`, card fields are optional strings. Produce `quote_checkout(session: AsyncSession, *, user_id: int, order_type: OrderType, payment_method: PaymentMethod) -> CheckoutQuote`. `CheckoutQuote` fields: `subtotal: Decimal`, `delivery_fee: Decimal | None`, `total: Decimal | None`, `payment_methods: list[PaymentMethod]`, `ready: bool`, `reasons: list[str]`, `quote_fingerprint: str | None`. `POST /api/v1/orders/quote` consumes `{order_type, payment_method}`; register before dynamic order routes.

- [ ] Write `test_quote_settings_validation`, `test_quote_fee_boundary`, `test_quote_preorder_exemption`, `test_payment_method_readiness`, `test_same_total_different_cart_changes_quote`. With two 5000-so'm units and explicit 20000 delivery fee, assert `subtotal=Decimal('10000')`, `total=Decimal('30000')`; at an explicit free-delivery threshold assert fee zero. Missing/null/malformed/negative values make relevant checkout unavailable; explicit zero is valid. Preorder needs shop-open but no price minimum or fee settings; pickup needs minimum; delivery needs all three numeric settings.

  ```python
  assert quote.subtotal == Decimal("10000")
  assert quote.total == Decimal("30000")
  assert quote_a.total == quote_b.total
  assert quote_a.quote_fingerprint != quote_b.quote_fingerprint
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_checkout_quote.py -q`; expected quote endpoint/types absent.
- [ ] Implement typed validation without production seeding. Available methods: cash when ready; card transfer only with both card fields; tender only with at least one lot URL and preserve missing-link reporting; preorder forces cash as a technical default with no payment step. Click/Payme readiness checks all current required merchant fields and secrets; Paynet readiness is always false in this phase. Return a readable `CHECKOUT_UNAVAILABLE` reason for missing configuration.
- [ ] Canonicalize fingerprint with sorted product ID/quantity/live-price/active fields, order type, payment method, totals and applicable settings/card instructions. Normalize decimals to fixed cent precision before SHA256; do not include changing stock in the fingerprint, but validate stock separately. Add additive public readiness fields while preserving existing fields and never exposing secret credentials.
- [ ] Rerun tests; assert two different cart contents with equal total produce different fingerprints. Expected all task tests pass.
- [ ] Commit `feat: quote checkout from validated server settings`.

## Task 5: Make order creation atomic, quote bound and replayable

**Files:** Create `backend/app/services/purchase_service.py`, `backend/tests/test_purchase_checkout.py`; modify `backend/app/services/order_service.py`, `backend/app/db/repositories/order_repository.py`, `backend/app/api/schemas/order.py`, `backend/app/api/v1/orders.py`, `backend/app/bot/handlers/user/checkout.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `CheckoutCommand` with exactly the current `CheckoutIn` business fields (normalized name/phone/address/comments, order type, payment method and optional Decimal coordinates), excluding the new HTTP contract metadata. Produce `CheckoutResult(order: Order, created: bool)` and `submit_checkout(session: AsyncSession, *, user_id: int, command: CheckoutCommand, checkout_key: UUID | None, expected_quote: str | None, expected_total: Decimal | None, source: str, lang: str) -> CheckoutResult`. Consume Tasks 3/4. Produce `order_repository.get_by_id_for_update(session, order_id: int) -> Order | None` and `get_by_checkout_key(session, user_id: int, key: UUID) -> Order | None`.

- [ ] Write `test_checkout_replay`, `test_checkout_fingerprint_conflict`, `test_checkout_same_cart_concurrency`, `test_checkout_last_unit_race`, `test_checkout_same_total_quote_change`, `test_checkout_failure_rolls_back`, `test_checkout_rejects_invalid_customer_fields` and `test_legacy_card_requires_reload`. Assert same key/payload yields one order/decrement; different payload is 409; two fresh sessions on the same cart create at most one order; competing users cannot oversell; changed equal-total cart is `QUOTE_CHANGED`; error preserves cart/stock and creates no partial order. API blank/over-128-character name, invalid Uzbek phone, and missing delivery address return 422; direct bot-service validation rejects the same invalid fields without creating an order.

  ```python
  assert created.status_code == 201 and replay.status_code == 200
  assert created.json()["id"] == replay.json()["id"]
  assert stock_after == stock_before - requested_quantity
  assert changed_quote.json()["error"]["code"] == "QUOTE_CHANGED"
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_purchase_checkout.py -q`; expected replay/quote/concurrency failures.
- [ ] Implement `normalize_checkout_command(command: CheckoutCommand) -> CheckoutCommand` in `purchase_service.py`: trim/validate name (1–128 characters), use existing Uzbek phone normalization/validation, require nonempty HTTP/webapp delivery text in the submit adapter; common normalization retains existing bot-only coordinate delivery and validates finite latitude[-90,90]/longitude[-180,180] pairs. Discard delivery fields for pickup/preorder. Apply it to API and bot adapters. Implement user/cart/product locking through Task 3; lookup replay before validating the now-empty cart. Compare current quote/total with expected values before side effects. Store normalized request fingerprint, checkout key and card instruction snapshot during order creation; preserve current stock/sold counters, order numbers, item snapshots and status history. All writes use the caller's transaction.
- [ ] Add `purchase_contract_version: Literal[1] | None`, optional `expected_total: Decimal | None`, `expected_quote: str | None` and UUID header parsing. Version 1 requires all three metadata values; unknown version returns 422. Return 201 for `created=True`, 200 for replay. Legacy cash/tender remain allowed only when the shared typed quote is ready (shop-open, numeric settings and method eligibility), with locking and no guessed default0; legacy HTTP card transfer returns `CLIENT_UPDATE_REQUIRED` before mutation. Bot confirmation obtains the same quote and stable key; preserved preorder flow skips payment and minimum.
- [ ] Lock/refetch orders before confirm/advance/cancel, then validate current status. Test simultaneous cancel and confirm/cancel, including inventory and sold_count restored once, one cancellation history event and no deadlock when another customer checks out that product.
- [ ] Rerun task tests and existing `tests/test_order_service.py`, `tests/test_lot_links_and_sources.py`; expected pass.
- [ ] Commit `feat: protect checkout and order transitions from retries`.

## Task 6: Commit purchases before external effects and harden existing gateway guards

**Files:** Create `backend/app/services/after_commit.py`, `backend/tests/test_purchase_commit.py`, `backend/tests/test_payment_callbacks.py`; modify `backend/app/api/deps.py`, `backend/app/api/v1/*.py` and `backend/app/api/v1/admin/*.py` only where consistent DB dependency scope is required, `backend/app/bot/middlewares/db.py`, `backend/app/api/v1/orders.py`, `backend/app/bot/handlers/user/checkout.py`, `backend/app/bot/handlers/admin/orders.py`, `backend/app/api/payments_webhooks.py`, `backend/app/services/payment_service.py`, `backend/app/bot/services/order_notifications.py`.

**Interfaces:** Produce `register_after_commit(session: AsyncSession, action: Callable[[], Awaitable[None]]) -> None` and `commit_with_after_commit(session: AsyncSession) -> None`. Actions carry IDs/immutable data, not live ORM objects. Commit failure clears actions and propagates; post-commit effect failure logs a sanitized order/event identifier and does not propagate into the purchase response. Notification metadata uses a new short-lived session after the order commit.

- [ ] Write `test_commit_failure_sends_no_notification`, `test_success_response_follows_commit`, `test_notification_failure_preserves_order`, `test_checkout_replay_skips_new_notification`, `test_gateway_exact_duplicate`, `test_gateway_second_transaction_rejected`, and wrong provider/order/amount/terminal-order tests with fabricated signatures/Basic auth and no external HTTP.

  ```python
  assert events.index("commit_finished") < events.index("http_success_sent")
  assert events.index("commit_finished") < events.index("telegram_send_started")
  assert created_order_exists_after_notification_failure is True
  assert payment_transition_count_after_duplicate == 1
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_purchase_commit.py tests/test_payment_callbacks.py -q`; expected pre-commit notification/guard failures.
- [ ] Use function-scoped yielded DB dependencies consistently across route and auth/admin subdependencies so commit completes before HTTP success is sent. Register post-commit ID-based notifications for first order creation/status changes only; bot DB middleware and explicit gateway session orchestration use the same commit helper. Keep services free of nested `begin()` and commit calls. This function scope behavior is documented by [FastAPI](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope).
- [ ] In existing Click/Payme handlers, locate transaction association without locking, lock the associated order first, then lock/refetch its provider transaction and revalidate signature/auth, provider, amount and payable state. Preserve each provider's response envelope. Recognize a valid exact duplicate before the new-payment terminal guard: replay after later order completion still returns the previous payment result without another state transition. Another successful transaction for a paid order is rejected. Pay-link creation verifies requested provider equals the order's configured payment method and the order is unpaid/non-terminal. Paynet endpoints reject unsupported use rather than executing the placeholder.
- [ ] Rerun task tests and Task 5 tests; expected pass. Do not claim Telegram exactly-once delivery or introduce a worker/queue in this task.
- [ ] Commit `fix: commit purchases before notifications and validate payment retries`.

## Task 7: Store and retrieve payment receipts privately

**Files:** Create `backend/app/services/receipt_storage.py`, `backend/app/services/receipt_service.py`, `backend/app/api/v1/receipts.py`, `backend/tests/test_private_receipts.py`; modify `backend/app/core/config.py`, `backend/app/core/uploads.py`, `backend/app/main.py`, `backend/app/api/v1/__init__.py`, `backend/app/api/v1/orders.py`, `backend/app/api/schemas/order.py`, `backend/app/bot/handlers/user/checkout.py`, `backend/app/bot/handlers/user/receipt_redirect.py`, `backend/app/bot/handlers/admin/orders.py`, `backend/app/bot/utils/admin_order_card.py`, `backend/Dockerfile`, `docker-compose.yml`, `nginx/nginx.conf`, `frontend/nginx.conf`.

**Interfaces:** In `receipt_storage.py`, `PrivateReceiptStorage(root: Path)`, `StoredReceipt(storage_key: str, content_type: str, size_bytes: int, sha256: str)`, `store(content: bytes, content_type: str) -> StoredReceipt`, `resolve(storage_key: str) -> Path`; immutable UUID object names with fixed type suffix, validated under the private root. In `receipt_service.py`, `attach_card_transfer_receipt(session, storage, *, order_id: int, owner_user_id: int, content: bytes, declared_content_type: str, telegram_file_id: str | None = None) -> Order` and `open_order_receipt(session, storage, *, order_id: int, user_id: int, admin_id: int | None = None) -> ReceiptRead` (`path: Path`, `content_type: str`). Add `PRIVATE_MEDIA_ROOT`, default `/app/private_media` in containers, never inside public `MEDIA_ROOT`.

- [ ] Write `test_receipt_owner_method_state_guards`, `test_receipt_content_and_size`, `test_receipt_replacement`, `test_receipt_private_http_read`, `test_public_receipt_path_denied`, `test_web_receipt_visible_to_bot_admin`, and `test_receipt_storage_rejects_traversal`. Assert 5 MiB accepted only for supported content; 5 MiB+1 rejected, MIME spoof rejected, another user/inactive admin denied, public route 404 and authenticated response `Cache-Control: private, no-store`.

  ```python
  assert public_get.status_code == 404
  assert owner_get.headers["cache-control"] == "private, no-store"
  assert owner_get.content == uploaded_content
  assert uploaded_order.payment_status == PaymentStatus.RECEIPT_UPLOADED
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_private_receipts.py -q`; expected public storage/read and missing state-guard failures.
- [ ] Read at most limit+1 for HTTP; cap bot download as well as advertised size. Verify JPEG/PNG/WebP via existing Pillow; PDF requires `%PDF-` header and a bounded ending `%%EOF` check, without rendering/executing content. Lock/refetch the order, verify owner/card-transfer/unpaid/non-terminal state, stage an immutable private object, update storage reference/content type/file ID, increment version and set `receipt_uploaded`. Preserve old objects through commit; unreferenced cleanup is deferred and never exposes files.
- [ ] Mount owner/admin authenticated receipt GET on the existing order path; bearer-authenticated frontend read later uses this API, never tokens in a URL. Close `/media/receipts` and its descendants before the public media mount and with `location ^~ /media/receipts/ { return 404; }` in both nginx variants; deny the exact prefix too. Product images remain public. Reuse this service for both bot upload flows and recheck ownership/state after their FSM delay. Adapt admin receipt action to use Telegram file ID or private bytes.
- [ ] Extend `OrderOut` additively with `payment_instructions`, `receipt_version`, `has_receipt`, review actor/time; retain nullable `receipt_url` for compatibility. Test past card orders without instruction snapshots show an explicit support-needed state rather than a guessed new card.
- [ ] Rerun task tests, Task 1/5 tests and bot order-card tests; expected pass.
- [ ] Commit `feat: keep payment receipts private across bot and web`.

## Task 8: Accept manual transfer evidence as a distinct admin action

**Files:** Create `backend/app/services/manual_payment_service.py`, `backend/app/api/v1/admin/payments.py`, `backend/tests/test_manual_payment.py`; modify `backend/app/api/v1/admin/__init__.py`, `backend/app/api/schemas/admin.py`, `backend/app/bot/keyboards/callback_data.py`, `backend/app/bot/handlers/admin/orders.py`, `backend/app/bot/utils/admin_order_card.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `accept_card_transfer_payment(session: AsyncSession, *, order_id: int, admin_id: int, expected_receipt_version: int) -> Order`; the admin ID is internal `Admin.id`. `POST /api/v1/admin/orders/{order_id}/payment/accept` consumes `{expected_receipt_version: int}` under current active-order-admin permissions. Produce an `AdminAcceptPaymentCallback` containing order ID and integer receipt version, staying under Telegram's callback byte limit.

- [ ] Write `test_manual_accept_keeps_order_status`, `test_manual_accept_audit_and_replay`, `test_replaced_receipt_invalidates_old_acceptance`, and `test_manual_accept_authorization`. Assert only `receipt_uploaded` card transfers can be newly accepted; `payment_status=paid`, reviewer/time populated, order status unchanged, same-version replay unchanged, stale version 409 and anonymous/inactive admins rejected. Race upload replacement and accept in two sessions; accepted evidence must be the version actually approved.

  ```python
  assert accepted.payment_status == PaymentStatus.PAID
  assert accepted.status == original_order_status
  assert accepted.payment_reviewed_by_admin_id == active_admin.id
  assert stale_version_response.status_code == 409
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_manual_payment.py -q`; expected action/service absent.
- [ ] Lock/refetch order, check current active admin and version, recognize exact previously accepted replay before new-action eligibility checks, and save payment review fields atomically. Show separate localized «To‘lovni tasdiqlash» on the bot card; existing confirm/cancel stay separate. Sync admin/customer notifications through Task 6 post-commit actions. No refund or payment reversal is added.
- [ ] Rerun task tests and `tests/test_admin_order_card.py`; expected pass and callback payload within limit.
- [ ] Commit `feat: review manual transfer payments separately from orders`.

## Task 9: Implement browser login, account isolation and clear cart feedback

**Files:** Create `frontend/vitest.config.ts`, `frontend/src/test/setup.ts`, `frontend/src/test/renderWithProviders.tsx`, `frontend/src/features/customer-auth/CustomerCodeDialog.tsx`, `frontend/src/features/customer-auth/CustomerAuthProvider.tsx`, `frontend/src/features/customer-auth/useCustomerCodeLogin.ts`, `frontend/src/lib/pendingCartAdd.ts`, `frontend/src/hooks/useCartActions.ts`, `frontend/src/lib/pendingCartAdd.test.ts`, `frontend/src/features/customer-auth/CustomerCodeDialog.test.tsx`, `frontend/src/hooks/useCartActions.test.tsx`, `frontend/src/lib/api.test.ts`, `frontend/src/pages/CartPage.test.tsx`; modify `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/App.tsx`, `frontend/src/store/auth.ts`, `frontend/src/hooks/useTelegramAuth.ts`, `frontend/src/lib/api.ts`, `frontend/src/hooks/queries.ts`, `frontend/src/components/ProductCard.tsx`, `frontend/src/pages/ProductPage.tsx`, `frontend/src/pages/CartPage.tsx`, `frontend/src/components/QuantityStepper.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/lib/i18n.ts`.

**Interfaces:** `PendingCartAdd = {productId: number; quantity: number; origin: string; mutationKey: string; createdAt: number}`. Produce `readPendingAdd(nowMs: number): PendingCartAdd | null`, `writePendingAdd(intent: PendingCartAdd): void`, `clearPendingAdd(): void`; storage key `kans-shop-pending-add`. Produce `useCartActions()` with `add(productId: number, quantity: number, origin: string): void`, `retry(): void`, `cancelLogin(): void`, `pending: boolean`, `errorCode: string | null`. Provider owns code dialog and one pending action; current JWT store remains authoritative, with an added internal `userId` from verified token subject to scope query keys.

- [ ] Install test-only packages in the execution worktree with Node 24: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`; add `test: vitest run`, preserve the lockfile. Configure alias matching Vite and jsdom, fresh QueryClient and MemoryRouter per test; no real API or Telegram. Vitest configuration follows its [official guide](https://vitest.dev/guide/).
- [ ] Write `pendingCartAdd.test.ts`, `CustomerCodeDialog.test.tsx`, `useCartActions.test.tsx`, `api.test.ts`, and `CartPage.test.tsx`. Assert 24-hour expiry, malformed stored intent discarded, login cancel restores route/discards intent, second add does not replace open dialog intent, code error/expiry feedback, one UUID reused after timeout/remount/StrictMode, zero optimistic increments before success, and quantity bounded by minimum/stock.

  ```typescript
  expect(readPendingAdd(createdAt + 24 * 60 * 60 * 1000)).toBeNull();
  expect(firstAddKey).toBe(retryAddKey);
  expect(refreshCallCount).toBe(1);
  expect(useAuthStore.getState().accessToken).toBeNull(); // logout during refresh
  ```
- [ ] Run `npm test -- src/lib/pendingCartAdd.test.ts src/features/customer-auth src/hooks/useCartActions.test.tsx src/lib/api.test.ts src/pages/CartPage.test.tsx`. Expected red: missing provider/action and login flow, not unresolved test imports.
- [ ] Implement browser sign-in dialog linking to `https://t.me/kansshopbot?start=web_login`, customer exchange and pending replay through Task 2/3 contracts. Mini App continues automatic validated auth; auth unavailable has readable recovery. Catalog quick add stays in catalog, detail add navigates to cart only after success. Every mutation displays a localized error and preserves the server cart; update/remove are not silently retried.
- [ ] Scope authenticated query keys as `['cart', userId]`, `['orders', userId]`, `['order', userId, orderId]`; on logout cancel outstanding requests, increment an auth epoch, clear tokens/owned cache and pending actions. Ignore late mutation/login/refresh responses from an older epoch so they cannot repopulate a switched account. Refresh remains shared for parallel 401s and retries each request once. Display line amounts from live product price or server totals, not a stale snapshot multiplied locally.
- [ ] Rerun task tests, `npm run typecheck`, `npm run build`; expected pass. Test three simultaneous 401s make one refresh call, expired refresh shows sign-in, and logout during that refresh never restores old tokens.
- [ ] Commit `feat: make browser cart login and recovery explicit`.

## Task 10: Build quote-based checkout and receipt recovery UI

**Files:** Create `frontend/src/hooks/checkout.ts`, `frontend/src/features/checkout/useCheckoutFlow.ts`, `frontend/src/features/checkout/CheckoutForm.tsx`, `frontend/src/features/checkout/CheckoutSuccess.tsx`, `frontend/src/features/checkout/ReceiptUpload.tsx`, `frontend/src/features/checkout/useCheckoutFlow.test.tsx`, `frontend/src/features/checkout/ReceiptUpload.test.tsx`, `frontend/src/pages/OrderDetailPage.test.tsx`; modify `frontend/src/pages/CheckoutPage.tsx`, `frontend/src/pages/OrderDetailPage.tsx`, `frontend/src/hooks/queries.ts`, `frontend/src/types/api.ts`, `frontend/src/lib/i18n.ts`.

**Interfaces:** Mirror Task 4 `CheckoutQuote` as strings/nulls for money, readiness/reasons, methods and fingerprint. Extend `CheckoutPayload` with `purchase_contract_version: 1`, `expected_total: string`, `expected_quote: string`; `useCheckout` mutation variables are `{payload: CheckoutPayload, checkoutKey: string}` and send the UUID header. `useCheckoutFlow()` produces form state/setters, current quote, submission state/error, created order and retry controls. Produce `useUploadReceipt()` (`{orderId, file: File}`), `useReceiptBlob(orderId: number, enabled: boolean)` and same-user order invalidation; fetch bearer-authenticated blob and revoke object URLs after display teardown.

- [ ] Write flow tests for quote loading/unavailable, field blur errors, correct delivery/pickup/preorder behavior, hidden unavailable methods, stable key on lost response, new key after deliberate form/quote change, `QUOTE_CHANGED` confirmation, unknown version rejection and `CLIENT_UPDATE_REQUIRED`. Assert the actual sent request carries version `1`, the displayed expected total/fingerprint and one UUID, never a total calculated from frontend settings.

  ```typescript
  expect(sentPayload.purchase_contract_version).toBe(1);
  expect(sentPayload.expected_total).toBe(displayedQuote.total);
  expect(sentPayload.expected_quote).toBe(displayedQuote.quote_fingerprint);
  expect(firstCheckoutKey).toBe(retriedCheckoutKey);
  ```
- [ ] Run `npm test -- src/features/checkout src/pages/OrderDetailPage.test.tsx`; expected red on absent server quote/receipt controls.
- [ ] Reduce `CheckoutPage` to route composition using the focused files. Guard authenticated checkout/orders routes with sign-in recovery. Obtain server quote after cart/type/method changes; discard stale responses and disable submit until current quote ready. Show phone/name/address validation on blur and submit attempt. Preorder omits payment/address/fee UI; tender shows lot URLs and missing items. Unknown checkout outcome freezes editing until same-key retry resolves; persist only key/quote fingerprint/opaque attempt state in sessionStorage, never form PII. If the page reloads without retained form, show order history/recovery and never silently resubmit a new attempt.
- [ ] Order success links to the created order detail. Card transfer shows immutable instruction snapshot, total, copy action and receipt upload/replacement while eligible. Show support-needed message for legacy orders without snapshots. Online pay-link failures retain the created order and expose same-order retry; payment completion comes from server order status, not redirect success. Receipt preview uses authenticated blob with no public URL or JWT query parameter.
- [ ] Rerun tests, `npm run typecheck`, `npm run build`; expected pass. Test server rounding, same-total changed quote, navigating away during upload, object URL cleanup, and existing order remaining accessible after an upload/pay-link error.
- [ ] Commit `feat: complete checkout and private receipt recovery`.

## Task 11: Verify browser journeys and exact release CI checks

**Files:** Create `frontend/playwright.config.ts`, `frontend/e2e/purchase.spec.ts`, `frontend/e2e/fixtures/purchaseApi.ts`, `backend/tests/test_purchase_journey.py`; modify `frontend/package.json`, `frontend/package-lock.json`, `.github/workflows/ci.yml`.

**Interfaces:** Add `test:e2e: playwright test`. Playwright uses a local Vite webServer with `VITE_API_BASE_URL=/api/v1`, loopback base URL, `reuseExistingServer: false` in CI and Node 24. Frontend-only tests route every `/api/v1/**` to fixture responses and intercept Telegram bridge script; unhandled external requests are rejected. This is separate from backend real-session HTTP journey tests, not claimed as proof that browser mocks exercise the DB.

- [ ] Add `@playwright/test` as a locked dev dependency; write journeys named `browser login to cash order`, `mini app cart to manual receipt`, `lost add and checkout responses reuse keys`, `quote change requires confirmation`, `sign out hides previous account`, and `legacy cached checkout requests reload`. Assert public catalog, visible feedback, correct payloads/badge/navigation and server-status-driven receipt/payment UI in UZ and RU at 390px mobile and 1280px desktop viewports.

  ```typescript
  expect(capturedCheckout.purchase_contract_version).toBe(1);
  expect(capturedAddKeys[0]).toBe(capturedAddKeys[1]);
  await expect(page.getByText(orderNumber, { exact: false })).toBeVisible();
  expect(unhandledExternalRequests).toEqual([]);
  ```
- [ ] Run `npm run test:e2e`; before implementation fixes, a scenario fails for the actual missing journey behavior rather than browser launch. Playwright local webServer setup follows [official documentation](https://playwright.dev/docs/test-webserver).
- [ ] Add backend `test_purchase_journey` covering auth → add → fresh cart read → quote → version 1 checkout → upload → admin acceptance, with one user seen by both code login and fabricated valid Mini App initData. Assert foreign-user isolation and transaction counters independently from frontend fixtures. Inject all Telegram effects.
- [ ] Add CI unit tests and Chromium install/run after typecheck/build; run backend lint/mypy/full pytest with isolated PostgreSQL/Redis and explicit synthetic env. Validate migration upgrade separately on an old-head disposable DB rather than relying on `metadata.create_all` alone. Keep public PR permissions read-only as defined on current `origin/main`; no secrets or deployment authority in test jobs.
- [ ] Run `./scripts/test-purchase.sh -q`, backend `ruff check app tests`, `black --check app tests`, `mypy app`, frontend `npm ci`, `npm test`, `npm run typecheck`, `npm run build`, `npm run test:e2e`. Expected zero errors; record actual results and any environment limitation.
- [ ] Commit `test: cover complete purchase journeys in CI`.

## Task 12: Prepare persistent private media cutover and owner-reviewed release

**Files:** Create `deploy/kans-shop.private-media.override.yml`, `deploy/kans-shop.caddy.snippet`, `backend/scripts/migrate_private_receipts.py`, `backend/tests/test_receipt_cutover.py`, `docs/RELEASE_PURCHASE.md`; modify `docs/ARCHITECTURE.md`, `docs/ASSUMPTIONS.md`, `README.md`, and `docs/DEPLOY.md` only to distinguish current Netcup and historical Railway behavior. Server-owned files `/srv/stack/stacks/kans-shop.yml` and `/srv/stack/infra/Caddyfile` are review targets, not repository files or automatic test mutations.

**Interfaces:** `migrate_private_receipts.py --dry-run` reports counts and a local restricted manifest; `--apply --manifest PATH` verifies hashes, copies each legacy receipt to immutable private storage, updates only that order's receipt metadata and removes each public copy only after private/DB reference verification. Repeat runs use the manifest and remain idempotent. Add a read-only `--verify` check. The script refuses private root inside public root and refuses unrecognized/traversing old file references; no remote receipt download.

- [ ] Write `test_receipt_cutover_preserves_content`, `test_cutover_partial_failure_keeps_backup`, `test_cutover_repeat_is_idempotent`, `test_old_image_cannot_expose_receipts`, and `test_kans_proxy_routes_callbacks`. Synthetic file/DB fixtures assert hashes/counts and no data loss; an isolated Docker fixture with old static-serving behavior cannot fetch receipts after cutover, including a simulated new legacy write. Assert unchanged product-image access.

  ```python
  assert private_sha256 == original_sha256
  assert public_receipt_after_rollback.status_code == 404
  assert new_legacy_receipt_after_rollback.status_code == 404
  assert public_product_image.status_code == 200
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_receipt_cutover.py -q`; expected missing migration/private mounts/route denial. Never run apply against Netcup as a red test.
- [ ] Implement the copy/verify/update/finalize script with a backup-first manifest and rollback-safe private volume. Prepare a Kans-only compose override mounting a persistent named private-media volume at `/app/private_media` and setting `PRIVATE_MEDIA_ROOT`. Preserve the existing product media mount and shared DB/Redis configuration. Add a Kans Caddy snippet denying `/media/receipts` and descendants before app routing; this deny rule remains installed on app rollback so even new receipts written by an old image cannot become public.
- [ ] Include `/payments/*` in the Kans site's existing API matcher so current backend callback routes reach `kans-api`, and replace only the stale Railway fallback in image nginx with a static SPA config: Netcup Caddy owns API routing, local Compose's root nginx owns its API routing. Do not alter other Caddy site blocks. Check trusted-proxy IP handling through the real chain with synthetic headers in isolated containers. These are scoped release corrections, not a change to gateway protocols.
- [ ] Rerun cutover tests, config validation in isolated Docker and the migration compatibility check. Write release instructions in this order: owner reviews final diff/settings/migration; verify DB and media backups; apply reviewed Kans mount and edge receipt deny; start new image and run protected cutover; verify every receipt reference privately and every public path denied; inspect matching SHA CI/deploy and smoke checks. Route callback checks use read-only/fake invalid requests, never a paid transaction.
- [ ] Document rollback: keep edge deny/private volume, restore only compatible app image/schema, and never restore public receipt copies. A partial cutover blocks rollback unless its edge deny remains in place. Document the final integrated notification queue, web admin and storefront behavior after all three phases are verified; describe Kans Shop as one store and keep unverified device/deployment limits explicit.
- [ ] Commit `docs: prepare private receipt cutover and Netcup release` after tests pass.
- [ ] Present concrete release diff, actual CI evidence, migration/backup checks and store readiness status for owner review. The owner's real fee/payment settings are deferred and may remain unset; explicitly show checkout unavailable and do not invent values to pass readiness. Stop before production config apply, protected-branch merge/main push or deployment until that release review is received. The spec's payment/price/role/migration/deploy owner gate is the reason for this stop.

## Plan Self Review and Handoff

The root must verify: every spec section maps to Tasks 1–12; all created interfaces have a producer before a consumer; the five Review Focus cases appear in owning tests; changes remain purchase-focused; schema is additive; complete checks occur before release claims. Repair gaps inline, without dispatching plan self-review to an agent.

Owner review of this phase-one plan is complete. After phases 2 and 3 have their required design/plan agreements, execute using the already requested subagents and model/effort, with autonomous completion across all phases. Report per-task red/green evidence and a tested commit. Keep three writer slots for disjoint files when useful; join at shared interfaces, then review the whole branch. The existing concrete production release review remains separate from this plan approval unless the owner explicitly supersedes that requirement.
