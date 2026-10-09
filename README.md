# Kans Shop

Online store for stationery and office supplies in Tashkent, Uzbekistan. Kans Shop has a Telegram
bot for customer ordering and bot administration, a web admin console, and a customer storefront
that runs in browsers and Telegram Mini App. All three use one PostgreSQL database and shared
business services through one REST API.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together,
[docs/DB_SCHEMA.md](docs/DB_SCHEMA.md) for the data model, and
[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) for non-obvious decisions and historical scope changes.

## Stack

- **Backend**: Python 3.12/3.13, FastAPI, aiogram 3.x, SQLAlchemy 2.0 (async), Alembic, PostgreSQL
  16, Redis (FSM storage + rate limiting), structlog.
- **Web app**: React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, Zustand,
  react-router-dom, @twa-dev/sdk. It contains both the customer storefront and `/admin` console.
- **Infra**: Docker Compose (`postgres`, `redis`, `api`, `nginx` serving the built web app +
  reverse-proxying `/api`); pushes to `main` run GitHub Actions, which builds and pushes images
  to GHCR before deploying them to netcup.

## Quick start (Docker)

```bash
cp .env.example .env      # fill in BOT_TOKEN, JWT_SECRET, WEBHOOK_SECRET at minimum
docker compose up -d --build
```

This starts Postgres, Redis, the FastAPI API (with the bot running in **webhook** mode if
`WEBHOOK_URL` is set — leave it empty for local Docker use), and nginx serving the Mini App at
`http://localhost/` with `/api/*` and `/webhook` proxied through to the API container.

For local Telegram testing without a public HTTPS URL, run the bot in **polling** mode instead:

```bash
docker compose --profile polling up -d bot
```

Seed the catalog with demo categories/products:

```bash
docker compose exec api python -m app.db.seed
```

## Local development (without Docker for the app itself)

```bash
docker compose up -d postgres redis   # only the infra, not the app containers
make migrate
make seed
make dev     # runs bot_polling.py + uvicorn --reload together
```

Mini App:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev   # http://localhost:5173
```

## Testing & linting

```bash
make test     # pytest (backend)
make lint     # ruff + black --check + mypy (backend), tsc --noEmit (frontend)
make format   # ruff --fix + black (backend)
```

## Deploying to production

Pushes to `main` run GitHub CI, build GHCR images, and deploy to Netcup through
`.github/workflows/deploy.yml`. The deployment waits for healthy containers. Railway instructions
in [docs/DEPLOY.md](docs/DEPLOY.md) are historical. Purchase release and private-receipt cutover
require the owner review described in [docs/RELEASE_PURCHASE.md](docs/RELEASE_PURCHASE.md).

## Project layout

```
backend/
  app/
    api/        # FastAPI routers + Pydantic schemas consumed by the Mini App
    bot/        # aiogram handlers/keyboards/states/middlewares — customer + admin
    core/       # settings, security (JWT/initData), logging, domain exceptions
    db/         # SQLAlchemy models, repositories, seed script
    services/   # business logic shared by the bot and the API
    locales/    # uz.json / ru.json — every user-facing string
  alembic/      # additive purchase, admin, and storefront migrations
  tests/        # pytest, Postgres-backed via a real test DB + savepoint rollback per test
frontend/
  src/
    pages/      # Storefront, account, and customer-order pages
    admin/      # Web admin auth shell, routes, and API client
    components/ Layout, ProductCard, CategoryCard, QuantityStepper, ...
    hooks/      # TanStack Query hooks (queries.ts) + Telegram auth bootstrap
    store/      # Zustand: auth (JWT), language
    lib/        # axios client, i18n dictionary, Telegram WebApp glue, formatting
docs/           # ARCHITECTURE.md, DB_SCHEMA.md, ASSUMPTIONS.md, DEPLOY.md
nginx/          # nginx.conf — SPA + /api + /webhook reverse proxy
```
