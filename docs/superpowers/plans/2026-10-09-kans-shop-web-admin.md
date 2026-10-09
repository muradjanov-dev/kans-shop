# Kans Shop Web Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a responsive `/admin` console with bot parity for orders, catalog, customers, reports, settings, staff, sources, audit, and durable broadcasts, backed by shared bot/web business services.

**Architecture:** Keep the React admin in the existing app, with a cookie-and-CSRF client separate from buyer JWT auth. HTTP routes and bot handlers call the same domain services; each mutation reloads the active actor and current role in its transaction, records audit/outbox data atomically, and leaves delivery to durable workers.

**Tech Stack:** Python 3.12, FastAPI, aiogram 3, SQLAlchemy 2 async, Alembic, PostgreSQL 16, Redis 7, React 19, TypeScript, Vite, TanStack Query, Zustand, Vitest, Testing Library, Playwright, Node 24.

**Spec:** [Approved phase 2 web admin design](../specs/2026-10-09-kans-shop-web-admin-design.md). Phase 1 purchase interfaces are defined in [the approved purchase plan](2026-10-09-kans-shop-purchase.md); its migrated head is `1e6b8d02a9c4`.

## Global Constraints

- Build on Alembic head `1e6b8d02a9c4`; this phase's additive migration is `2f7c9e13b0d5` and has no parallel head.
- Keep one store, buyer JWT behavior, current customer routes, product media, phase 1 checkout, private receipt and manual payment contracts intact.
- Admin cookie is `__Host-kans-admin`, `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, with no `Domain`; session cookie is a random 256-bit token whose SHA-256 digest alone is stored.
- Admin session idle lifetime is 12 hours and absolute lifetime is 7 days. Refresh changes only idle expiry; the cookie and stable session CSRF nonce do not rotate.
- Admin exchange requires JSON and exact `Origin == settings.webapp_url`; every cookie-authenticated unsafe request, including multipart upload, requires that Origin and `X-CSRF-Token`. Do not widen credentialed CORS.
- Every admin mutation service accepts internal `admin_id`, reloads `admins` in the same transaction, and checks live `is_active` and role. Never authorize from browser role, `is_admin`, Telegram ID, JWT claim, or stale bot FSM state.
- Admin endpoints reject Bearer fallback with `401 ADMIN_SESSION_REQUIRED`; the legacy admin exchange returns `410 ADMIN_SESSION_REQUIRED`. Buyer JWT endpoints remain unchanged.
- Auth/session/private receipt and private admin responses use `Cache-Control: private, no-store`. Never log code, session/CSRF token, full phone, receipt bytes, card number, provider secret, or raw gateway payload.
- Product/category edit uses `edit_version`; row lock plus expected version returns `409 ENTITY_CONFLICT`. Phase 1 checkout/cancel stock writes increment product version.
- Last active superadmin is protected by one PostgreSQL advisory transaction lock and a fresh count. Team role/deactivation/removal increments `auth_epoch` and revokes sessions in the same transaction.
- Missing store settings remain `null` and show as not configured. Add no demo fee, minimum, card, support identity, or merchant secret; phase 1 quote/checkout stays fail-closed. Do not enable Click, Payme, or Paynet.
- `today` starts at Asia/Tashkent midnight and ends now; `week` is the last 7 days; `month` is the last 30 days. Convert DB boundaries to UTC. `orders_count` includes cancelled orders; `order_value` excludes cancelled orders regardless of payment; `paid_amount` requires `payment_status=paid` and non-cancelled status; average divides `order_value` by non-cancelled count. Keep API `revenue` compatibility, but label it “uncancelled order value” in bot/web/XLSX.
- Campaign attribution is first-touch `users.traffic_source_id`; never rewrite it on login or later campaign links. Used sources are deactivated, not deleted.
- Outbox and broadcast are durable and at-least-once, not exactly-once. Use one shared Redis pacing gate capped at 20 messages/second and honor Telegram `RetryAfter`. Tests use fake Bot and disposable PostgreSQL/Redis only; no real customer messages or broadcasts.
- Do not change shared Netcup services or unrelated site blocks. Production release still requires owner review of a concrete final diff and release evidence; this plan approval does not authorize applying production configuration or sending a live broadcast.

## Review Focus

1. A role or active-state change while a bot FSM form is open must reject its final save using the fresh actor read — Task 5 `test_bot_save_rechecks_live_admin_role`.
2. A checkout/cancel stock change must make a stale product form return conflict without overwriting live stock — Task 4 `test_checkout_stock_version_rejects_stale_admin_edit`.
3. Tashkent midnight and cancelled/paid combinations must produce identical bot, API and XLSX figures — Task 7 `test_tashkent_period_and_amount_labels`.
4. Two concurrent staff mutations must never leave zero active superadmins — Task 6 `test_concurrent_last_superadmin_changes_keep_one_active`.
5. A changed audience or revoked launcher after restart must stop pending broadcast work before the next send — Task 10 `test_broadcast_rechecks_preview_and_actor_before_each_claim`.

## Execution Dependencies and File Ownership

Task 1 establishes all phase 2 tables and the sole migration head. Task 2 consumes those session models. Task 3 establishes shared actor, audit and outbox primitives. Tasks 4–8 share router/schema/locales registries and run sequentially in this checkout. Independent frontend Task 11 may run alongside backend tasks once Task 2 publishes its session contract. Task 9 owns outbox dispatch/lifespan; Task 10 also integrates its broadcast worker into lifespan and consumes Task 9 pacing, so Tasks 9/10 stay sequential. Task 11 owns the frontend admin auth shell and route registry; Task 12 owns domain pages/forms and their tests. Do not run writers on the same file or against shared test containers. Use `./scripts/test-purchase.sh` for backend tests and the phase 1 Vitest setup (`npm test -- ...`) for frontend tests; use Playwright only for browser journeys.

### Task 1: Add the phase 2 database foundation

**Files:** Create `backend/alembic/versions/2f7c9e13b0d5_web_admin.py`, `backend/app/db/models/admin_session.py`, `backend/app/db/models/admin_audit_event.py`, `backend/app/db/models/notification_outbox.py`, `backend/app/db/models/admin_order_message.py`, `backend/app/db/models/broadcast_recipient.py`, `backend/app/db/models/store_state.py`, `backend/tests/test_admin_migrations.py`; modify `backend/app/db/models/admin.py`, `backend/app/db/models/product.py`, `backend/app/db/models/category.py`, `backend/app/db/models/enums.py`, `backend/app/db/models/__init__.py`, `backend/tests/test_migrations.py`.

**Interfaces:** Migration `revision="2f7c9e13b0d5"`, `down_revision="1e6b8d02a9c4"`. Add `Admin.auth_epoch`, `Product.edit_version`, `Category.edit_version`, singleton `StoreState.settings_version`, `AdminSession` with cookie digest/CSRF nonce/auth epoch/idle and absolute expiry/revocation fields, `AdminAuditEvent` with redacted before/after JSON, `NotificationOutbox` with event/dedupe/availability/attempt/lease/sent/sanitized-error fields, `AdminOrderMessage` with protected text and UUID replay key, and `BroadcastRecipient` with unique `(broadcast_id,user_id)`, status `pending|sending|sent|failed|cancelled`, attempts, lease, retry, sent time and sanitized error. Add `Broadcast.photo_storage_key` for private web-uploaded campaign media and `cancelled` to PostgreSQL `broadcast_status`; preserve `admin_role` enum and phase 1 columns.

- [ ] Write `test_phase2_migration_from_phase1_head`, `test_phase2_upgrade_preserves_orders_receipts_and_media_refs`, and `test_phase2_has_single_head`. Assert the upgrade starts at `1e6b8d02a9c4`, historical order and receipt metadata survive, and all new unique keys exist.

  ```python
  assert preserved_order_ids == original_order_ids
  assert private_receipt_reference == original_private_receipt_reference
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_migrations.py tests/test_migrations.py -q`; expected missing revision/models and structure assertions to fail.
- [ ] Implement only additive DDL with defaults that preserve existing rows. `broadcast_recipients` has unique `(broadcast_id,user_id)`; `notification_outbox.dedupe_key` is unique; session FK cascades/revokes while audit actor history survives admin deletion.
- [ ] Rerun both migration tests; expected one head and preserved synthetic phase 1 data.
- [ ] Commit `feat: add web admin persistence`.

### Task 2: Add cookie admin sessions and request security

**Files:** Create `backend/app/services/admin_session_service.py`, `backend/app/api/admin_security.py`, `backend/tests/test_admin_sessions.py`; modify `backend/app/api/deps.py`, `backend/app/api/v1/auth.py`, `backend/app/api/v1/__init__.py`, `backend/app/core/exceptions.py`, `backend/app/core/config.py`, `backend/app/api/schemas/auth.py`.

**Interfaces:** `AdminSessionPrincipal(admin_id: int, session_id: int, role: AdminRole, csrf_token: str)`. Produce `create_admin_session(session: AsyncSession, *, admin_id: int, now: datetime) -> tuple[AdminSessionPrincipal, str]`, `resolve_admin_session(session: AsyncSession, *, raw_token: str, now: datetime) -> AdminSessionPrincipal`, `refresh_admin_session(session: AsyncSession, *, principal: AdminSessionPrincipal, now: datetime) -> None`, and `require_admin_roles(*roles: AdminRole) -> Callable[..., Awaitable[Admin]]`. Keep current `get_current_admin` returning the live ORM Admin resolved from the cookie principal so unchanged handlers using `admin.id` remain compatible. Session response is `{admin_id,full_name,role,csrf_token}`. Mount `POST /auth/admin/code/exchange`, `GET /auth/admin/session`, `POST /auth/admin/session/refresh`, `POST /auth/admin/logout`, and `POST /auth/admin/logout-all`.

- [ ] Write `test_admin_cookie_session_lifecycle`, `test_parallel_refresh_keeps_cookie_and_csrf_stable`, `test_admin_session_epoch_and_expiry_revoke`, `test_exact_origin_csrf_and_multipart_guards`, `test_admin_bearer_fallback_is_rejected`, and `test_legacy_admin_exchange_is_gone`. Assert cookie flags, 12-hour idle/7-day absolute expiry, only digest persisted, CSRF stable, exact-origin mismatch/CSRF mismatch return `403 CSRF_FAILED`, old Bearer gets `401 ADMIN_SESSION_REQUIRED`, old exchange gets 410, and buyer JWT still works.

  ```python
  assert bearer_admin_response.status_code == 401
  assert session_response.headers["cache-control"] == "private, no-store"
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_sessions.py -q`; expected absent session endpoints and principal.
- [ ] Consume the phase 1 `admin_login:` code atomically; exchange requires JSON and exact webapp Origin, checks an existing active Admin, and sets `__Host-kans-admin` with `Secure; HttpOnly; SameSite=Lax; Path=/` and no Domain. Store independent random 256-bit cookie and CSRF values as SHA-256 digest and session nonce. Refresh/logout validate Origin and `X-CSRF-Token`; all returned session/auth data is `private, no-store`.
- [ ] Rerun the task tests plus `tests/test_security.py`; expected buyer JWT contract unchanged and every admin route denies Bearer fallback.
- [ ] Commit `feat: add secure browser admin sessions`.

### Task 3: Centralize live actor checks, audit, and outbox writes

**Files:** Create `backend/app/services/admin_actor_service.py`, `backend/app/services/admin_audit_service.py`, `backend/app/services/notification_outbox_service.py`, `backend/app/api/v1/admin/audit.py`, `backend/tests/test_admin_mutation_policy.py`, `backend/tests/test_admin_audit.py`; modify `backend/app/api/v1/admin/__init__.py`, `backend/app/api/schemas/admin.py`, `backend/app/bot/utils/admin_guard.py`.

**Interfaces:** Produce `load_live_admin(session: AsyncSession, *, admin_id: int, allowed_roles: frozenset[AdminRole] | None = None, lock: bool = False) -> Admin`, `write_audit_event(session: AsyncSession, *, admin_id: int, action: str, entity: str, entity_id: int | None, request_id: str, before: dict[str, object] | None, after: dict[str, object] | None) -> AdminAuditEvent`, and `enqueue_outbox_event(session: AsyncSession, *, event_type: str, aggregate_id: int, dedupe_key: str, recipient_user_id: int | None = None, recipient_admin_id: int | None = None, payload_id: int | None = None) -> NotificationOutbox`.

- [ ] Write `test_live_actor_is_reloaded_for_every_mutation`, `test_audit_redacts_sensitive_values_and_rolls_back_with_write`, `test_audit_visibility_roles`, and `test_outbox_dedupe_is_transactional`. Assert the common actor helper rejects a demoted manager; Task 5 verifies the real final bot FSM save after its adapter is integrated. Audit has no full phone/card/code/token, and a rolled-back business write leaves neither audit nor outbox row.

  ```python
  assert stale_actor_response.status_code == 403
  assert rolled_back_audit_count == 0
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_mutation_policy.py tests/test_admin_audit.py -q`; expected missing common services.
- [ ] Implement helpers that never commit; `load_live_admin` reloads by internal ID and rejects inactive or newly unauthorized actors; mutation protection uses PostgreSQL FOR NO KEY UPDATE (`with_for_update(key_share=True)`) to serialize role changes while remaining compatible with FK key-share checks. Team operations acquire their advisory lock before actor/target row locks in ID order. Audit redaction masks card to last four and excludes full phone, secrets, auth material, receipt bytes, and raw gateway payload. Add paged `GET /api/v1/admin/audit` with superadmin-all, manager-operational, operator-own-event filtering.
- [ ] Rerun tests; expected actor recheck and atomic audit behavior pass.
- [ ] Commit `feat: centralize admin policy audit and outbox records`.

### Task 4: Move catalog and image mutations to shared services

**Files:** Create `backend/app/services/admin_catalog_service.py`, `backend/tests/test_admin_catalog_service.py`; modify `backend/app/api/v1/admin/products.py`, `backend/app/api/v1/admin/categories.py`, `backend/app/api/schemas/admin.py`, `backend/app/bot/handlers/admin/products.py`, `backend/app/bot/handlers/admin/products_form.py`, `backend/app/bot/handlers/admin/products_edit.py`, `backend/app/bot/handlers/admin/categories.py`, `backend/app/bot/states/admin_catalog.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`, `backend/app/services/purchase_service.py`, `backend/app/services/order_service.py`.

**Interfaces:** Produce `create_product(session, *, admin_id: int, values: ProductCreateIn) -> Product`, `update_product(session, *, admin_id: int, product_id: int, expected_edit_version: int, changes: ProductUpdateIn) -> Product`, `delete_product(session, *, admin_id: int, product_id: int) -> None`, `create_category(session, *, admin_id: int, values: CategoryCreateIn) -> Category`, `update_category(session, *, admin_id: int, category_id: int, expected_edit_version: int, changes: CategoryUpdateIn) -> Category`, `move_category(session, *, admin_id: int, category_id: int, parent_id: int | None, expected_edit_version: int) -> Category`, `delete_category(session, *, admin_id: int, category_id: int) -> None`, `add_product_image(session, *, admin_id: int, product_id: int, content: bytes, content_type: str) -> ProductImage`, `set_product_image(session, *, admin_id: int, product_id: int, image_id: int, is_main: bool, sort_order: int) -> ProductImage`, `set_category_image(session, *, admin_id: int, category_id: int, content: bytes, content_type: str) -> Category`, and `delete_category_image(session, *, admin_id: int, category_id: int) -> Category`. HTTP keeps existing CRUD paths and adds multipart product image upload, primary/reorder/delete, and category image PUT/DELETE paths from the spec. Admin product responses use `AdminProductOut(ProductOut)` with additional `barcode: str | None` and `sort_order: int` on list/detail/create/update/image paths so full edit forms can read current editable values. Add `GET /api/v1/admin/products/{product_id}` with the same admin permissions and eager image loading, including inactive products, so a conflict refresh does not depend on the current filtered page. Keep the public `ProductOut` unchanged; add an HTTP round-trip regression before frontend Task 12.

- [ ] Write `test_product_catalog_validation`, `test_checkout_stock_version_rejects_stale_admin_edit`, `test_category_cycle_parallel_edits`, `test_category_in_use_conflict`, `test_image_primary_reorder_is_atomic`, `test_catalog_multipart_requires_csrf_and_bounds`, and `test_bot_and_web_share_catalog_service`. Assert SKU uniqueness, price > 0, stock >= 0, `min_order_qty >= 1`, HTTPS-only lot URL, one primary image, category descendants cannot become ancestors, and checkout stock/version cannot be overwritten by a stale edit.

  ```python
  assert stale_stock_response.status_code == 409
  assert stock_after == stock_before_checkout - sold_quantity
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_catalog_service.py tests/test_catalog_service.py tests/test_lot_links_and_sources.py -q`; expected version/service parity failures.
- [ ] Implement product/category writes with fresh actor, row locks, expected `edit_version`, service-managed product/category counts, and one category-tree advisory lock for parent/delete checks. Existing image media validation remains in force. Route and bot form adapters call the same service; phase 1 checkout/cancel stock writes increment product `edit_version`.
- [ ] Rerun named tests and `tests/test_admin_order_card.py`; expected bot behavior and order snapshots retained.
- [ ] Commit `feat: share catalog administration across web and bot`.

### Task 5: Add customer administration and typed store settings

**Files:** Create `backend/app/services/customer_admin_service.py`, `backend/app/services/store_settings_service.py`, `backend/tests/test_customer_admin_service.py`, `backend/tests/test_store_settings_service.py`; modify `backend/app/api/v1/admin/users.py`, create `backend/app/api/v1/admin/settings.py`, modify `backend/app/api/v1/admin/__init__.py`, `backend/app/api/schemas/admin.py`, `backend/app/api/v1/settings.py`, `backend/app/services/checkout_settings.py`, `backend/app/bot/handlers/admin/users.py`, `backend/app/bot/handlers/admin/settings.py`, `backend/app/bot/keyboards/inline/admin_settings.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `list_admin_users(session, *, admin_id: int, query: str | None, page: int, limit: int) -> Page[User]`, `get_admin_user(session, *, admin_id: int, user_id: int) -> AdminUserDetail`, and `set_user_blocked(session, *, admin_id: int, user_id: int, blocked: bool) -> User`. Produce `get_store_settings(session, *, admin_id: int) -> StoreSettingsSnapshot`, `patch_store_settings(session, *, admin_id: int, expected_version: int, changes: StoreSettingsPatch) -> StoreSettingsSnapshot`, and `checkout_settings_from_store(session: AsyncSession) -> CheckoutSettings`. Define StoreSettingsPatch/Snapshot in admin schemas with exactly the existing setting keys; snapshot adds `version:int` and readiness. Numeric values serialize Decimal strings/null; PATCH accepts those typed fields plus `expected_version` and forbids unknown keys. AdminUserDetail carries current UserOut fields, order count and optional first-touch source summary; list phone is masked, authorized detail phone unmasked.

- [ ] Write `test_user_phone_masking_and_block_auth`, `test_customer_admin_roles_and_operator_order_only`, `test_settings_version_conflict`, `test_settings_validation_and_null_readiness`, `test_settings_never_returns_gateway_secrets`, and `test_bot_save_rechecks_live_admin_role`. Assert list phone is masked, detail contains phone only to authorized manager/superadmin, blocking causes buyer auth rejection, all numeric values are nonnegative (explicit zero allowed), missing values remain null/readiness false, stale settings return `409 ENTITY_CONFLICT`, and the real bot settings final save is denied after demotion.

  ```python
  assert unconfigured_snapshot["delivery_fee"] is None
  assert stale_settings_response.status_code == 409
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_customer_admin_service.py tests/test_store_settings_service.py -q`; expected absent typed service and admin settings API.
- [ ] Implement manager/superadmin customer list/detail/block and the typed delta settings API. `StoreState.settings_version` is locked and incremented; bot settings forms use this service and expected version. The phase 1 quote loader consumes the same typed source. Return readiness for delivery fee, free threshold, minimum, work hours, card/support fields and shop-open state; never seed or expose provider secrets.
- [ ] Rerun task tests, `tests/test_checkout_quote.py`, and `tests/test_security.py`; expected an unconfigured store remains browseable while checkout quote fails closed.
- [ ] Commit `feat: manage customers and typed store settings`.

### Task 6: Add staff, roles, session revocation, and last-superadmin protection

**Files:** Create `backend/app/services/admin_team_service.py`, `backend/app/api/v1/admin/team.py`, `backend/tests/test_admin_team_service.py`; modify `backend/app/api/v1/admin/__init__.py`, `backend/app/api/schemas/admin.py`, `backend/app/db/repositories/admin_repository.py`, `backend/app/bot/handlers/admin/manage.py`, `backend/app/bot/keyboards/inline/admin_manage.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Define AdminChanges in admin schemas for full_name, role, is_active and notifications_enabled only. Produce `add_admin(session, *, actor_admin_id: int, telegram_id: int, full_name: str, role: AdminRole) -> Admin`, `update_admin(session, *, actor_admin_id: int, admin_id: int, changes: AdminChanges) -> Admin`, `remove_admin(session, *, actor_admin_id: int, admin_id: int) -> None`, and `revoke_admin_sessions(session, *, actor_admin_id: int, admin_id: int) -> int`. Mount the spec's `GET/POST /api/v1/admin/team`, `PATCH/DELETE /.../team/{admin_id}`, and `POST /.../team/{admin_id}/sessions/revoke` as superadmin-only.

- [ ] Write `test_team_roles_and_self_delete`, `test_last_superadmin_single_mutation`, `test_concurrent_last_superadmin_changes_keep_one_active`, `test_role_change_revokes_sessions_and_epoch`, and `test_seed_does_not_reactivate_existing_admin`. Assert self-delete is denied; neither demote, deactivate nor delete can remove the final active superadmin; concurrent two-transaction changes yield at least one `409 LAST_SUPERADMIN_REQUIRED`; role/deactivation/removal increments auth epoch and revokes sessions.

  ```python
  assert active_superadmin_count >= 1
  assert revoked_session_response.status_code == 401
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_team_service.py -q`; expected team route/service and locking assertions to fail.
- [ ] Acquire one fixed `pg_advisory_xact_lock` for all add/promote/demote/activate/deactivate/delete flows, then re-read count and write. Do not change `ADMIN_IDS` seed behavior to reactivate or promote existing rows. Write audit and team notifications through Task 3 helpers in the same transaction.
- [ ] Rerun task tests and `tests/test_admin_sessions.py`; expected revoked cookie sessions fail on the next request.
- [ ] Commit `feat: manage staff roles and revoke sessions safely`.

### Task 7: Share Tashkent statistics, export, and traffic-source reporting

**Files:** Create `backend/app/services/traffic_source_service.py`, `backend/app/api/v1/admin/sources.py`, `backend/tests/test_admin_stats_service.py`, `backend/tests/test_traffic_source_admin.py`; modify `backend/app/services/stats_service.py`, `backend/app/api/v1/admin/stats.py`, `backend/app/api/v1/admin/__init__.py`, `backend/app/api/schemas/admin.py`, `backend/app/bot/handlers/admin/stats.py`, `backend/app/bot/handlers/admin/sources.py`, `backend/app/bot/utils/stats_export.py`, `backend/app/bot/keyboards/inline/admin_stats.py`, `backend/app/bot/keyboards/inline/admin_sources.py`, `backend/app/db/repositories/traffic_source_repository.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `period_bounds(period: Literal["today", "week", "month"], *, now: datetime) -> tuple[datetime, datetime]`, `get_admin_stats(session, *, admin_id: int, period: str, now: datetime) -> AdminStats`, `export_admin_stats_xlsx(session, *, admin_id: int, period: str, now: datetime) -> bytes`, `list_sources(session, *, admin_id: int, page: int, limit: int) -> Page[TrafficSource]`, `create_source(session, *, admin_id: int, name: str, code: str) -> TrafficSource`, `get_source_stats(session, *, admin_id: int, source_id: int) -> SourceStats` (clicks, first-touch users, their orders and order value), and `update_source(session, *, admin_id: int, source_id: int, name: str | None, active: bool | None) -> TrafficSource`. Expose `GET /api/v1/admin/stats/overview`, `GET /api/v1/admin/stats/export.xlsx`, `GET/POST /api/v1/admin/sources`, and `GET/PATCH /api/v1/admin/sources/{id}`.

- [ ] Write `test_tashkent_period_and_amount_labels`, `test_cancelled_orders_count_but_not_order_value`, `test_paid_amount_requires_paid_and_non_cancelled`, `test_stats_operator_read_only`, `test_xlsx_uses_same_period_and_labels`, and `test_source_first_touch_and_used_source_deactivation`. Assert UTC bounds represent Tashkent today midnight, week/month spans are exactly 7/30 days, avg check uses non-cancelled count, both API `revenue` and display labels retain the correct meaning, and campaign totals use first-touch users without rewriting attribution.

  ```python
  assert today_start.isoformat() == "2026-10-08T19:00:00+00:00"  # now=2026-10-09T07:00Z
  assert paid_amount == Decimal("5000")  # one non-cancelled paid fixture
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_stats_service.py tests/test_traffic_source_admin.py tests/test_stats_service.py tests/test_traffic_sources.py -q`; expected operator REST access and shared labels/periods to fail.
- [ ] Route bot, REST, and XLSX through the same service. Add operator read-only access to overview/export and manager/superadmin source list/create/patch. Source deactivation preserves historical relations; no hard delete for used sources.
- [ ] Rerun named tests; expected API, bot labels and XLSX formulas agree.
- [ ] Commit `feat: share admin reports and traffic source metrics`.

### Task 8: Unify order administration, private receipt reads, and one-off messages

**Files:** Create `backend/app/services/admin_order_service.py`, `backend/tests/test_admin_order_service.py`; modify `backend/app/api/v1/admin/orders.py`, `backend/app/api/v1/orders.py`, `backend/app/api/v1/admin/__init__.py`, `backend/app/api/schemas/admin.py`, `backend/app/api/schemas/order.py`, `backend/app/bot/handlers/admin/orders.py`, `backend/app/bot/handlers/admin/orders_list.py`, `backend/app/bot/utils/admin_order_card.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `list_admin_orders(session, *, admin_id: int, status: OrderStatus | None, query: str | None, date_from: date | None, date_to: date | None, page: int, limit: int) -> Page[Order]`, `get_admin_order(session, *, admin_id: int, order_id: int) -> AdminOrderDetail`, and `queue_order_message(session, *, admin_id: int, order_id: int, text: str, idempotency_key: UUID) -> AdminOrderMessage`. `POST /api/v1/admin/orders/{id}/message` accepts `{text: str, idempotency_key: UUID}` and returns queued message ID/state. Keep status mutations on phase 1 `order_service` transitions and receipt service; add cookie-admin principal to `GET /api/v1/orders/{order_id}/receipt` while Bearer remains owner-only.

- [ ] Write `test_order_permissions_and_detail_history`, `test_admin_receipt_requires_live_order_role`, `test_bearer_receipt_is_owner_only`, `test_order_message_is_deduped_and_uses_order_owner`, and `test_order_message_validation_and_audit`. Assert all active roles can view/transition orders and accept phase 1 transfers; client cannot select a Telegram recipient; text length is 1–4096; API queues one message ID and audit stores no message body.

  ```python
  assert foreign_receipt_bearer.status_code == 403
  assert replay_message_id == original_message_id
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_order_service.py tests/test_private_receipts.py tests/test_manual_payment.py -q`; expected browser admin principal and message queue absent.
- [ ] Use Task 3 live-actor/audit/outbox helpers and phase 1 order/receipt/payment services. Add filter/pagination and detail snapshots/status/payment history. Cookie receipt read requires an active order-view session; Bearer read requires `user.id == order.user_id` even if claims contain admin metadata. All receipt/private order responses are `private, no-store`.
- [ ] Rerun task tests, `tests/test_admin_order_card.py`, and `tests/test_manual_payment.py`; expected bot callbacks and web updates use the same order rules.
- [ ] Commit `feat: administer orders and queue customer messages`.

### Task 9: Dispatch transactional notifications with durable leases

**Files:** Create `backend/app/services/notification_outbox_worker.py`, `backend/app/services/telegram_pacing_service.py`, `backend/tests/test_notification_outbox_worker.py`; modify `backend/app/main.py`, `backend/app/services/order_service.py`, `backend/app/services/purchase_service.py`, `backend/app/services/manual_payment_service.py`, `backend/app/services/admin_team_service.py`, `backend/app/services/store_settings_service.py`, `backend/app/api/v1/admin/orders.py`, `backend/app/bot/services/order_notifications.py`, `backend/app/bot/services/system_notifications.py`.

**Interfaces:** Produce `claim_outbox_batch(session, *, worker_id: str, now: datetime, limit: int, lease_seconds: int) -> list[OutboxClaim]`, `ack_outbox(session, *, event_id: int, lease_token: UUID, sent_at: datetime) -> bool`, `retry_outbox(session, *, event_id: int, lease_token: UUID, available_at: datetime, safe_error: str) -> bool`, and `run_outbox_worker(bot: Bot, session_maker: async_sessionmaker[AsyncSession], redis: Redis, stop: Event) -> None`. Pacing interface: `acquire_telegram_slot(redis: Redis, *, bot_id: int, now: datetime) -> None`.

- [ ] Write `test_business_rollback_removes_outbox`, `test_two_sessions_claim_distinct_rows`, `test_expired_lease_reclaimed_and_old_token_cannot_ack`, `test_restart_sends_pending_outbox`, `test_fanout_is_one_row_per_admin`, `test_retry_after_and_forbidden_update`, and `test_phase1_direct_send_is_not_duplicated`. Assert network send occurs after business commit, shared rate is at most 20/sec, retry delay is honored, Forbidden blocks a user, and revoked actor/admin/user state is rechecked before delivery.

  ```python
  assert stale_lease_ack is False
  assert sent_before_business_commit == 0
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_notification_outbox_worker.py -q`; expected absent worker/lease behavior.
- [ ] Claim with `FOR UPDATE SKIP LOCKED` in a short transaction, send outside DB locks, and ack/retry only for the current lease token. Start and stop one task in FastAPI lifespan and replace matching phase 1 direct sends so no same-event dual delivery remains. Log sanitized event IDs only; document post-send/pre-ack duplicate window as at-least-once.
- [ ] Rerun task tests with two independent database sessions and fake Bot; expected crash/restart recovery and idempotent checkpoints.
- [ ] Commit `feat: deliver admin notifications from durable outbox`.

### Task 10: Make broadcasts previewed, durable, and explicitly launched

**Files:** Create `backend/app/services/admin_broadcast_service.py`, `backend/app/services/broadcast_media_service.py`, `backend/app/services/broadcast_worker.py`, `backend/tests/test_admin_broadcast_service.py`; modify `backend/app/api/v1/admin/broadcasts.py` (replace existing BackgroundTasks implementation), `backend/app/main.py`, `backend/app/db/models/broadcast.py`, `backend/alembic/versions/2f7c9e13b0d5_web_admin_foundation.py`, `backend/tests/test_admin_migrations.py`, `backend/app/db/repositories/broadcast_repository.py`, `backend/app/api/schemas/admin.py`, `backend/app/bot/handlers/admin/broadcast.py`, `backend/app/bot/keyboards/inline/admin_broadcast.py`, `backend/app/locales/uz.json`, `backend/app/locales/ru.json`.

**Interfaces:** Produce `store_broadcast_photo(*, content: bytes, content_type: str) -> str` returning an opaque UUID storage key under `PRIVATE_MEDIA_ROOT/broadcasts`; `preview_broadcast(session, *, admin_id: int, target: BroadcastTarget, text: str, photo_storage_key: str | None, photo_file_id: str | None, button_text: str | None, button_url: str | None) -> BroadcastPreview`; `create_broadcast_draft(session, *, admin_id: int, preview: BroadcastPreview) -> Broadcast`; `launch_broadcast(session, *, admin_id: int, broadcast_id: int, preview_fingerprint: str, preview_count: int, idempotency_key: UUID) -> Broadcast`; and `cancel_broadcast(session, *, admin_id: int, broadcast_id: int) -> Broadcast`. Persist nullable launch metadata on Broadcast: unique `launch_idempotency_key: UUID`, `launch_fingerprint: str` (64), `launch_count: int` (nonnegative), `launcher_auth_epoch: int` (nonnegative), and timezone-aware `launched_at`. Add these fields to the unreleased additive phase-two migration `2f7c9e13b0d5`; preserve the sole head and old rows. Snapshot the actual launcher in existing `admin_id` at launch and compare the epoch before sends, so revocation followed by reactivation cannot resume an old job. Legacy sending rows without a durable launch/recipient checkpoint must stop without guessing or resending an audience. `POST /media` accepts bounded JPEG/PNG/WebP multipart with the Task 2 Origin/CSRF checks and returns the opaque asset key. Mount `POST /preview`, `POST /`, `GET /{id}`, `POST /{id}/launch`, and `POST /{id}/cancel` under `/api/v1/admin/broadcasts`.

- [ ] Write `test_preview_and_draft_never_send`, `test_broadcast_photo_upload_is_private_and_csrf_guarded`, `test_launch_snapshot_idempotency_and_preview_conflicts`, `test_broadcast_recipient_restart_and_checkpoint`, `test_cancel_and_revoked_actor_stop_pending`, `test_forbidden_user_is_blocked`, `test_shared_pacing_and_retry_after`, and `test_broadcast_rechecks_preview_and_actor_before_each_claim`. Assert audience fingerprint sorts recipient IDs and binds target/text/photo/button, photo bytes remain outside public media and require multipart CSRF, changed count gives `409 BROADCAST_AUDIENCE_CHANGED`, changed content gives `409 BROADCAST_PREVIEW_CHANGED`, duplicate key launches one job, and only explicit launch creates deliveries.

  ```python
  assert sent_after_preview_and_draft == 0
  assert changed_content_response.status_code == 409
  ```
- [ ] Run `./scripts/test-purchase.sh tests/test_admin_broadcast_service.py -q`; expected current `BackgroundTasks` route to fail durability/no-send guarantees.
- [ ] In one transaction snapshot recipients into unique `(broadcast_id,user_id)` rows and transition draft to sending. Start/stop the broadcast worker in the API lifespan alongside Task 9. Worker claims pending/expired-sending rows with lease tokens, uses Task 9 shared pacing, rechecks block/cancel/live launch actor immediately before send, and records sent/failed/cancelled plus sanitized error and retry time. Preserve photo/button content; send private uploaded bytes with `BufferedInputFile` and legacy bot `photo_file_id` as-is. Honor RetryAfter. No real Broadcast send is used in tests.
- [ ] Rerun task tests plus `tests/test_traffic_sources.py`; expected restart resumes only unsent recipient checkpoints.
- [ ] Commit `feat: add durable previewed broadcasts`.

### Task 11: Build admin auth client, route shell, and responsive navigation

**Files:** Create `frontend/src/admin/api.ts`, `frontend/src/admin/AdminAuthProvider.tsx`, `frontend/src/admin/AdminLayout.tsx`, `frontend/src/admin/RequireAdmin.tsx`, `frontend/src/admin/adminRoutes.tsx`, `frontend/src/admin/adminAuth.test.tsx`, `frontend/src/admin/adminShell.test.tsx`; modify `frontend/src/App.tsx`, `frontend/src/lib/i18n.ts`, `frontend/src/index.css`.

**Interfaces:** `adminApi` uses `baseURL="/api/v1"`, `withCredentials: true`, sends `X-CSRF-Token` on unsafe calls from server session state, and has `exchangeCode(code: string)`, `loadSession()`, `refreshSession()`, `logout()`, and `logoutAll()`. `AdminSession = {admin_id: number; full_name: string; role: "superadmin" | "manager" | "operator"; csrf_token: string}`. `/admin/*` bootstrap never calls `useTelegramAuth` and never sends buyer Authorization.

- [ ] Write `adminAuth.test.tsx` and `adminShell.test.tsx`. Assert no customer-initData request from an admin route; unauthenticated session shows login and no private data; expired/revoked session clears the view; role nav follows the server response; logout calls API; unsafe JSON and multipart include CSRF; 360px nav/table does not overflow.

  ```typescript
  expect(customerInitDataRequestCount).toBe(0);
  expect(unsafeRequestHeaders["X-CSRF-Token"]).toBe(serverSession.csrf_token);
  ```
- [ ] Run `cd frontend && npm test -- src/admin/adminAuth.test.tsx src/admin/adminShell.test.tsx`; expected missing routes/client and session states.
- [ ] Implement `/admin/login`, session bootstrap and all spec route registrations: `/admin`, `/admin/orders`, `/admin/catalog`, `/admin/customers`, `/admin/reports`, `/admin/settings`, `/admin/team`, `/admin/sources`, `/admin/audit`, `/admin/broadcasts`. Preserve buyer app providers and routes; hide nav entries by role while server remains authoritative. Provide Uzbek/Russian labels and accessible loading/error/empty/session-expired shell.
- [ ] Rerun task tests, `npm run typecheck`, and `npm run build`; expected admin route doesn't start the buyer Telegram flow.
- [ ] Commit `feat: add admin session shell and navigation`.

### Task 12: Add responsive admin pages and contract-focused form tests

**Files:** Create `frontend/src/admin/pages/DashboardPage.tsx`, `frontend/src/admin/pages/OrdersPage.tsx`, `frontend/src/admin/pages/CatalogPage.tsx`, `frontend/src/admin/pages/CustomersPage.tsx`, `frontend/src/admin/pages/ReportsPage.tsx`, `frontend/src/admin/pages/SettingsPage.tsx`, `frontend/src/admin/pages/TeamPage.tsx`, `frontend/src/admin/pages/SourcesPage.tsx`, `frontend/src/admin/pages/AuditPage.tsx`, `frontend/src/admin/pages/BroadcastsPage.tsx`, `frontend/src/admin/adminPages.test.tsx`, `frontend/src/admin/adminForms.test.tsx`, `frontend/src/admin/adminTypes.ts`, `frontend/src/admin/adminQueries.ts`.

**Interfaces:** Domain query/mutation functions consume the Task 2–10 REST contracts and `AdminSession`; all mutations pass server-issued CSRF and required product/category `expected_edit_version` or settings `expected_version`. `AdminStoreSettings` has `version`, nullable decimal-string `delivery_fee`, `free_delivery_from`, `min_order_amount`, nullable `work_hours`, card number/holder, support username/phone, nullable boolean `is_shop_open`, Uzbek/Russian welcome text, and readiness flags per field. Product/category drafts include the latest server version. Broadcast upload returns an opaque photo asset key; launch submits preview fingerprint, count and a fresh UUID idempotency key.

- [ ] Write page/form assertions for operator order-only access and stats access, masked customer phone, stale product/settings conflict retaining the draft, missing-settings readiness without demo values, report amount labels, first-touch source metrics, explicit broadcast preview/confirm/launch, cancel/progress, and no send on draft/page load. Exercise product/category and broadcast photo upload plus catalog primary/reorder controls through multipart requests.

  ```typescript
  expect(settingsForm.delivery_fee).toBeNull();
  expect(broadcastSendCountAfterPageLoad).toBe(0);
  ```
- [ ] Run `cd frontend && npm test -- src/admin/adminPages.test.tsx src/admin/adminForms.test.tsx`; expected missing domain pages/forms or incorrect role/readiness behavior.
- [ ] Implement order list/detail with phase 1 receipt/payment history and queued message state; catalog/category/image forms; customer block controls; report/export/source views; typed settings readiness; superadmin team/session controls; audit filters; broadcast preview, explicit confirmation, progress and cancel. Handle `ENTITY_CONFLICT`, `LAST_SUPERADMIN_REQUIRED`, `BROADCAST_AUDIENCE_CHANGED`, and `BROADCAST_PREVIEW_CHANGED` with recoverable draft/refresh states. Keep all admin layouts usable at 360px, tablet, and desktop.
- [ ] Rerun task tests, `npm run typecheck`, `npm run build`, and `npm run test:e2e` for `/admin` at 390px and 1280px with fake API responses. Expected role, locale and no-send assertions pass.
- [ ] Commit `feat: build responsive web admin pages`.

## Execution Handoff

Owner approved both written designs and explicitly directed writing these plans then immediate autonomous implementation without another approval stop. Root self-review completed the file/interface map; preserve the requested GPT-6 Luna/max and disjoint parallel work. No real messages or payments are sent as tests.
