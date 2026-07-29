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

## Deferred/out of scope unless requested later
- Payment gateway *callbacks* for Click/Payme are modeled in the `payment_method` enum and the
  order/payment flow is built to accommodate them, but the spec's actual checkout flow only
  requires cash and manual card-transfer-with-receipt-screenshot — no live Click/Payme API
  integration is implemented (would need merchant credentials not provided).
