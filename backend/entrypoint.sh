#!/usr/bin/env sh
set -e

echo "[entrypoint] running alembic migrations..."
alembic upgrade head

case "$1" in
  api)
    echo "[entrypoint] starting FastAPI (uvicorn)..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  bot-polling)
    echo "[entrypoint] starting bot in polling mode..."
    exec python -m app.bot_polling
    ;;
  *)
    echo "[entrypoint] unknown command: $1 (expected 'api' or 'bot-polling')"
    exec "$@"
    ;;
esac
