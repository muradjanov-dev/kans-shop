# Kans Shop — Architecture

## Overview

Kans Shop is an online stationery/office-supplies storefront for the Uzbekistan market (Tashkent),
delivered through three coordinated clients that all share **one database and one business-logic
layer**:

1. **Telegram Bot** (aiogram 3.x) — primary customer channel + admin operations console.
2. **Telegram Mini App** (React + TypeScript, served as a Telegram WebApp) — visual storefront.
3. **Web Admin Panel** (same React app, `/admin` route) — back-office for staff.

The bot and the Mini App never talk to the database directly for business operations — both go
through the **service layer** (`app/services/*`). The bot calls services in-process (same Python
process/import), the Mini App calls the same services through the **FastAPI REST API**
(`app/api/v1/*`), which is a thin HTTP wrapper around the identical services. This guarantees the
cart, catalog, and order logic can never drift between bot and web.

```
                        ┌─────────────────────┐
                        │   PostgreSQL 15+     │
                        └───────────▲──────────┘
                                    │ SQLAlchemy 2.0 async (repositories)
                        ┌───────────┴──────────┐
                        │   services/*          │  <- single source of business logic
                        │ (cart, catalog, order,│
                        │  admin, stats, auth)  │
                        └───────▲───────▲───────┘
                                │       │
                 in-process     │       │  HTTP (FastAPI, /api/v1)
                                │       │
                 ┌──────────────┘       └───────────────┐
                 │                                       │
        ┌────────┴────────┐                    ┌─────────┴─────────┐
        │  aiogram Bot     │                    │  React Mini App    │
        │  (polling/webhook)│                   │  + Web Admin Panel │
        └──────────────────┘                    └────────────────────┘
```

## Backend layout (`backend/app`)

- `core/` — settings (`pydantic-settings`), security (JWT, initData HMAC), structured logging,
  exception types + global exception handler.
- `db/` — SQLAlchemy `Base`, async session/engine factory, `models/` (ORM), `repositories/`
  (pure data access, no business rules — one repository per aggregate).
- `services/` — business logic. Handlers/routers call services; services call repositories.
  Services own transactions (`async with session.begin(): ...`).
- `api/v1/` — FastAPI routers (`catalog`, `cart`, `orders`, `admin`, `auth`, `settings`). Routers
  are thin: validate input via Pydantic, call a service, return a Pydantic response model.
  `deps.py` provides `get_db`, `get_current_user` (initData JWT), `get_current_admin` (role guard).
- `bot/` — aiogram application: `handlers/user` (customer flows), `handlers/admin` (admin console),
  `keyboards/`, `states/` (FSM state groups), `middlewares/` (db-session injection, i18n,
  throttling, user auto-registration, last_active_at touch).
- `locales/` — `uz.json`, `ru.json`. No hardcoded user-facing strings anywhere in the codebase.
- `main.py` — FastAPI app factory; mounts the Telegram webhook route and lifespan-starts the bot
  in webhook mode when `WEBHOOK_URL` is set.
- `bot_polling.py` — standalone polling entrypoint for local development (`make dev`).

Rule: **handlers never touch SQL** — handler → service → repository → model. Every repository
method takes an `AsyncSession` explicitly (no ambient/global session).

## Data flow: adding to cart (bot vs Mini App)

1. Bot: `handlers/user/catalog.py` calls `cart_service.add_item(session, user_id, product_id, qty)`.
2. Mini App: `POST /api/v1/cart/items` → router resolves `current_user` from validated initData →
   calls the exact same `cart_service.add_item(...)`.
3. Both paths hit the same `carts`/`cart_items` rows, so the cart shown in the bot and in the Mini
   App is always identical — there is one cart per user, not one per client.

## Stock-safety

Order creation runs inside a DB transaction that locks the relevant `products` rows with
`SELECT ... FOR UPDATE`, re-validates `stock_qty >= quantity` for every line, decrements stock, and
only then commits the order. This prevents overselling under concurrent checkouts.

## Admin notification fan-out & race safety

When an order is created, `order_service.notify_admins(...)` sends the order card to every active
admin with `notifications_enabled=true` and stores `{admin_telegram_id: message_id}` in
`orders.admin_message_ids` (JSONB). When any admin acts on the order (confirm/cancel), the service
edits **every** stored message to reflect the new state and tags who acted, and subsequent taps by
other admins get `answer_callback_query(..., show_alert=True)` instead of a duplicate action. The
state check and update happen inside one transaction keyed on `orders.status`, so the first commit
wins.

## Frontend (`frontend/src`)

Single Vite React app serving two audiences via routing:

- `/` … Mini App routes (Home, Category, Product, Search, Cart, Checkout, Orders, Order detail,
  Profile) — mounted only inside Telegram (`@twa-dev/sdk`), theme driven by `themeParams`.
- `/admin/*` … Web Admin Panel routes (Dashboard, Orders, Products, Categories, Customers,
  Settings, Broadcasts) — guarded by JWT stored in memory + httpOnly-less refresh via
  `/auth/refresh` (short-lived access token in memory, refresh token in httpOnly cookie).

State: Zustand for local/UI state (cart optimistic state, WebApp theme), TanStack Query for all
server state (fetch/cache/invalidate). No Redux.

## Infra

- `docker-compose.yml`: `postgres`, `redis`, `api` (uvicorn, runs FastAPI + webhook), `bot`
  (separate container running `bot_polling.py` for environments without a public webhook URL — in
  production the `api` container handles the webhook instead and `bot` is not started), `nginx`
  (serves the built frontend + reverse-proxies `/api` to `api`).
- Alembic migrations run automatically on container start (`entrypoint.sh` → `alembic upgrade head`
  → start process).
- Railway: one service per container, `DATABASE_URL`/`REDIS_URL` injected by Railway's Postgres/
  Redis plugins; webhook mode is used in production (see `docs/DEPLOY.md`).

## Why these boundaries

- **One business-logic layer** — the master requirement is that bot and Mini App carts/orders stay
  in sync; putting logic in `services/` and never in handlers/routers is what makes that true by
  construction rather than by convention.
- **Repository pattern** — keeps SQLAlchemy specifics out of business logic, makes services
  testable with a fake repository if ever needed, and keeps handlers/routers under the 50-line
  function / 400-line file budget.
- **JSONB `admin_message_ids`** — Telegram has no concept of "edit this message for N different
  chat_ids at once"; we have to track each admin's copy of the order card ourselves to keep them
  all in sync and to prevent double-processing.
