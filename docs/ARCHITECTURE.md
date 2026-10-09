# Kans Shop — Architecture

## Overview

Kans Shop is one online stationery and office-supplies store in Tashkent. Its customer and admin
surfaces share **one database and one business-logic layer**:

1. **Telegram Bot** (aiogram 3.x) — customer ordering and bot administration.
2. **Web admin** (React + TypeScript) — operator workflows under `/admin`.
3. **Customer storefront** (React + TypeScript) — catalog, cart, checkout, and customer account in
   browsers and Telegram Mini App.

The bot and React app go through the **service layer** (`app/services/*`). The bot calls services
in-process; the customer storefront and web admin call the same services through FastAPI
(`app/api/v1/*`). This keeps cart, catalog, order, and admin rules in one place.

```
                        ┌─────────────────────┐
                        │   PostgreSQL 16      │
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
        │  aiogram Bot     │                    │  React Web App     │
        │ customer + admin │                    │ admin + storefront │
        └──────────────────┘                    └────────────────────┘
```

## Backend layout (`backend/app`)

- `core/` — settings (`pydantic-settings`), security (JWT, initData HMAC), structured logging,
  exception types + global exception handler.
- `db/` — SQLAlchemy `Base`, async session/engine factory, `models/` (ORM), `repositories/`
  (pure data access, no business rules — one repository per aggregate).
- `services/` — business logic. Handlers/routers call services; services call repositories.
  Services own transactions (`async with session.begin(): ...`).
- `api/v1/` — FastAPI routers for the customer storefront and `/admin` console. Customer routes
  use buyer bearer tokens; admin routes use a separate cookie session with CSRF checks, live role
  validation, and audit records.
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
2. Browser or Mini App: `POST /api/v1/cart/items` → router resolves the buyer from the active
   customer session → calls the exact same `cart_service.add_item(...)`.
3. Both paths hit the same `carts`/`cart_items` rows, so the cart shown in the bot and in the Mini
   App is always identical — there is one cart per user, not one per client.

## Stock-safety

Order creation runs inside a DB transaction that locks the relevant `products` rows with
`SELECT ... FOR UPDATE`, re-validates `stock_qty >= quantity` for every line, decrements stock, and
only then commits the order. This prevents overselling under concurrent checkouts.

## Admin notification and audit records

Admin changes record audit and notification-outbox events in the business transaction. The durable
notification dispatcher and broadcast worker must be present and verified in the release SHA
before queue delivery is treated as an operational guarantee. Earlier direct order-card fan-out
described in the historical notes is not evidence of restart-safe delivery.

## Frontend (`frontend/src`)

Single Vite React app with customer storefront and web-admin routes. The storefront includes the
catalog, product details, favorites, cart, quote-based checkout, orders, profile, and saved
addresses. Telegram Mini App uses validated `initData`; browser customers can sign in through the
bot's one-time code flow. The admin console uses a separate cookie and CSRF-protected API client.

State: Zustand for auth/language (small, persisted, non-server state), TanStack Query for customer
and admin server state (fetch/cache/invalidate). No Redux.

## Infra

- `docker-compose.yml`: local `postgres`, `redis`, `api` (uvicorn and webhook), optional polling
  `bot`, and root `nginx` (serves the built web app and routes local API/webhook requests).
- Alembic migrations run automatically on container start (`entrypoint.sh` → `alembic upgrade head`
  → start process).
- Current production uses the Netcup stack and Caddy for public API, webhook, payment callback, and
  media routing. Railway instructions are historical; see `docs/DEPLOY.md`.
- Product images remain in public `MEDIA_ROOT`. Payment receipts use separate persistent
  `PRIVATE_MEDIA_ROOT`; the Kans Caddy site denies `/media/receipts` before app routing. Keep that
  denial installed through an old-image rollback.

## Why these boundaries

- **One business-logic layer** — the master requirement is that bot and web cart/order operations
  stay in sync and admin rules stay consistent across the bot and `/admin`; putting logic in
  `services/` keeps that true by construction rather than by convention.
- **Repository pattern** — keeps SQLAlchemy specifics out of business logic, makes services
  testable with a fake repository if ever needed, and keeps handlers/routers under the 50-line
  function / 400-line file budget.
- **JSONB `admin_message_ids`** — Telegram has no concept of "edit this message for N different
  chat_ids at once"; we have to track each admin's copy of the order card ourselves to keep them
  all in sync and to prevent double-processing.
