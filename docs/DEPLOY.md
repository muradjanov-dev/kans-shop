# Deploying Kans Shop to Railway

This project has no CI/CD wired up — deployment is manual, via the Railway dashboard/CLI. Nothing
in this guide is run automatically by anyone other than you; there's no Railway API token in this
environment, so these steps are written for you to execute yourself.

## 1. Prerequisites

- A Railway account and a new empty **Project**.
- Your bot's token from [@BotFather](https://t.me/BotFather) (`BOT_TOKEN`) and its `@username`
  (`BOT_USERNAME`).
- Your own Telegram numeric user ID for `ADMIN_IDS` (bootstraps you as `superadmin` on first
  `/start` — get it from [@userinfobot](https://t.me/userinfobot) if you don't already have it).

## 2. Provision the services

In the Railway project, add:

1. **PostgreSQL** (Railway's managed Postgres plugin) — note the connection details it generates.
2. **Redis** (Railway's managed Redis plugin).
3. A **service from this repo** for the API + bot (webhook mode) — point it at the `backend/`
   directory with `backend/Dockerfile` as the Dockerfile path (Railway supports subdirectory
   builds; set the service's "Root Directory" to `backend`).
4. A **second service from this repo** for the Mini App — Root Directory `frontend`, using
   `frontend/Dockerfile`. Railway will assign it its own public domain; that domain is what you
   configure as the Telegram Mini App URL (see step 5).

You do **not** need a separate `bot` (polling) service in production — the `api` service runs the
bot in webhook mode via the same FastAPI process (see `app/main.py`'s lifespan).

## 3. Environment variables (API service)

Set these on the **API service** (values from `.env.example`, filled in for real):

| Variable | Value |
|---|---|
| `BOT_TOKEN` | from BotFather |
| `BOT_USERNAME` | your bot's username, no `@` |
| `WEBHOOK_URL` | `https://<your-api-service>.up.railway.app` (no trailing slash, no `/webhook` — the app appends it) |
| `WEBHOOK_SECRET` | `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `ADMIN_IDS` | your Telegram user ID (comma-separated if more than one bootstrap admin) |
| `ERROR_CHANNEL_ID` | a chat/channel ID for uncaught-exception reports (your own DM id is fine to start) |
| `DATABASE_URL` | Railway Postgres plugin's `postgresql+asyncpg://...` connection string (adjust the scheme prefix — Railway gives you `postgresql://`, prepend `+asyncpg`) |
| `DATABASE_URL_SYNC` | same connection string with `+psycopg` instead of `+asyncpg` (used only by Alembic) |
| `REDIS_URL` | Railway Redis plugin's connection string |
| `JWT_SECRET` | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `WEBAPP_URL` | the Mini App service's public URL (step 4) — used for CORS |
| `API_BASE_URL` | the API service's own public URL |
| `MEDIA_ROOT` | `/app/media` |
| `MEDIA_BASE_URL` | `https://<your-api-service>.up.railway.app/media` |

Leave `JWT_ALGORITHM`, `JWT_ACCESS_TTL_MINUTES`, `JWT_REFRESH_TTL_DAYS`, `DEFAULT_LANGUAGE`,
`TIMEZONE`, `CURRENCY`, `DEBUG` at their `.env.example` defaults unless you have a reason to change
them.

Railway runs `entrypoint.sh api`, which applies Alembic migrations on every deploy before starting
uvicorn — no separate migration step needed.

## 4. Environment variables (Mini App service)

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | build-time only (Docker `ARG`, not a runtime env var) — set it as a build argument in Railway's service settings: `https://<your-api-service>.up.railway.app/api/v1` |

(Locally/in `docker-compose.yml` this defaults to the relative `/api/v1` because nginx proxies
same-origin; on Railway the Mini App and API are separate services/domains, so it needs the API's
full public URL instead.)

## 5. Point Telegram at the deployed services

In [@BotFather](https://t.me/BotFather):

1. `/setmenubutton` on your bot → set the Web App URL to the Mini App service's Railway domain.
2. `/mybots` → your bot → **Bot Settings** → **Menu Button** (same URL, alternate path in the UI).

The webhook itself is set automatically by the app on startup (`app/main.py`'s `lifespan`, when
`WEBHOOK_URL` is configured) — no manual `setWebhook` call needed. You'll get a message from the
bot in Telegram (to every configured admin) confirming the app came up, right after each deploy.

## 6. First deploy checklist

- [ ] Both services build and start without crash-looping (check Railway's deploy logs).
- [ ] `GET https://<api-domain>/health` returns `{"status":"ok"}`.
- [ ] Opening the bot in Telegram and sending `/start` registers you and (if your ID is in
      `ADMIN_IDS`) shows the admin menu.
- [ ] The Mini App opens from the bot's menu button and loads the catalog.
- [ ] You receive the deploy-notification DM from the bot.
- [ ] Seed the catalog if this is a fresh database: `railway run --service api python -m app.db.seed`
      (or open a shell on the service via the Railway dashboard).

## 7. Persistent storage for uploads (required)

`MEDIA_ROOT` (`/app/media`) holds product images and payment receipts. A Railway container's
filesystem is **ephemeral** — without a volume mounted there, every deploy silently discards
all of it and the storefront renders each product with a broken image, while the API still
returns 200 for the catalog. Nothing in the logs reports this.

The `api` service therefore has a volume (`api-volume`) mounted at `/app/media`. If you
recreate the service, recreate the volume too:

```bash
railway service link api
railway volume add --mount-path /app/media
```

A freshly mounted volume starts empty. Because the bot stores every uploaded photo's Telegram
`file_id` in the database, the files can be pulled back from Telegram rather than re-uploaded
by hand:

```bash
railway ssh --service api "python -m app.db.restore_media --receipts"
```

It is idempotent (existing files are skipped; `--force` overwrites), so it is also the recovery
step after any future media loss.

## 8. Deploying from the CLI (exact commands)

`railway up` archives the **linked project directory** (the repo root), not your shell's
current directory — `cd backend && railway up` uploads the repo root all the same. Since
neither Dockerfile sits at the repo root, the build then dies with:

```
error | failed to read Dockerfile at 'Dockerfile'
```

which the CLI hides — `railway up` prints only a bare `Deploy failed`. To see the real reason,
ask the API directly:

```bash
railway api 'query { buildLogs(deploymentId: "<id>", limit: 200) { message severity } }'
```

Use `--path-as-root` to make the service's own subdirectory the archive root, so its Dockerfile
lands at the context root:

```bash
railway up backend  --path-as-root --service api      --ci
railway up frontend --path-as-root --service frontend --ci
```

Both services have `RAILWAY_DOCKERFILE_PATH=Dockerfile` set to match. Do not set it to
`/Dockerfile` from Git Bash on Windows — MSYS rewrites the leading slash and it arrives as
`C:/Program Files/Git/Dockerfile`. Use PowerShell, or a path with no leading slash.

## 9. Redeploying

Railway redeploys automatically on push if you've connected the GitHub repo, or manually via
the `railway up` commands in section 8 / the dashboard's "Deploy" button. Every deploy re-runs Alembic migrations
automatically and re-notifies admins on startup — no extra steps.
