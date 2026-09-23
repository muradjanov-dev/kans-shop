# Kans Shop agent guide

Kans Shop is a stationery store with a Telegram bot and React Mini App. Read
`docs/ARCHITECTURE.md`, `docs/DB_SCHEMA.md` and `docs/ASSUMPTIONS.md` for the
current business model. Parts of `README.md` and `docs/DEPLOY.md` still describe
Railway; production deploys from `main` through `.github/workflows/deploy.yml`
to netcup.

## Checks and boundaries

- `backend/app/services/` owns order, cart, catalog and payment rules shared by
  the bot and API. Keep bot and Mini App behavior consistent.
- `backend/app/db/` owns PostgreSQL models and repositories. A model change
  requires an Alembic migration and an appropriate test.
- `frontend/` is the Mini App. `npm ci`, `npm run typecheck` and `npm run build`
  must pass for frontend changes.
- Backend CI runs `ruff check app tests`, `black --check app tests`, `mypy app`
  and `pytest -q` from `backend/` with a test PostgreSQL service.

## Delivery

- Keep changes focused on one task and report the exact checks performed.
- Test customer order flows with fake bot/payment data, never the production
  token or a real customer's order.
- Payment, prices, roles, migrations, mass messages, secrets and CI/deploy
  changes need owner review before release.
- GitHub CI and the exact deployed image SHA are the release evidence. A
  passing typecheck alone does not prove the Mini App build or checkout works.
