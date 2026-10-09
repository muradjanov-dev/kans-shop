#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_root/backend"
venv_dir="$backend_dir/.venv"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/kans-shop-purchase.XXXXXX")"
pg_name=""
redis_name=""
pg_started=0
redis_started=0

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if (( redis_started )); then
    docker rm -f "$redis_name" >/dev/null 2>&1 || true
  fi
  if (( pg_started )); then
    docker rm -f "$pg_name" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$tmp_dir"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ $# -eq 0 ]]; then
  echo "Usage: ./scripts/test-purchase.sh <pytest arguments>" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run isolated purchase tests." >&2
  exit 1
fi
if [[ ! -x "$venv_dir/bin/python" ]]; then
  python3.12 -m venv "$venv_dir"
fi
if ! "$venv_dir/bin/python" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
  echo "backend/.venv must use Python 3.12." >&2
  exit 1
fi
suffix="$("$venv_dir/bin/python" -c 'import secrets; print(secrets.token_hex(6))')"
pg_name="kans-shop-purchase-pg-$suffix"
redis_name="kans-shop-purchase-redis-$suffix"
if "$venv_dir/bin/python" -m pip --version >/dev/null 2>&1; then
  "$venv_dir/bin/python" -m pip install --quiet -r "$backend_dir/requirements.txt"
elif command -v uv >/dev/null 2>&1; then
  uv pip install --quiet --python "$venv_dir/bin/python" \
    --requirement "$backend_dir/requirements.txt"
else
  echo "Install pip or uv to provision backend/requirements.txt into backend/.venv." >&2
  exit 1
fi

db_name="kansshop_test_$suffix"
dotenv_file="$tmp_dir/empty.env"
media_root="$tmp_dir/public-media"
private_media_root="$tmp_dir/private-media"
: > "$dotenv_file"
mkdir -p "$media_root" "$private_media_root"

docker run --detach --name "$pg_name" \
  --publish 127.0.0.1::5432 \
  --env POSTGRES_USER=kansshop \
  --env POSTGRES_PASSWORD=kansshop \
  --env "POSTGRES_DB=$db_name" \
  postgres:16-alpine >/dev/null
pg_started=1

docker run --detach --name "$redis_name" \
  --publish 127.0.0.1::6379 \
  redis:7-alpine >/dev/null
redis_started=1

pg_port="$(docker port "$pg_name" 5432/tcp | sed 's/.*://')"
redis_port="$(docker port "$redis_name" 6379/tcp | sed 's/.*://')"
if [[ ! "$pg_port" =~ ^[0-9]+$ || ! "$redis_port" =~ ^[0-9]+$ ]]; then
  echo "Docker did not publish PostgreSQL and Redis on loopback ports." >&2
  exit 1
fi

wait_for_service() {
  local name="$1"
  local command="$2"
  local attempt
  for attempt in $(seq 1 60); do
    if docker exec "$name" sh -c "$command" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "Timed out waiting for isolated service $name." >&2
  return 1
}
wait_for_service "$pg_name" "pg_isready -U kansshop -d $db_name"
wait_for_service "$redis_name" "redis-cli ping"

database_url="postgresql+asyncpg://kansshop:kansshop@127.0.0.1:$pg_port/$db_name"
sync_database_url="postgresql+psycopg://kansshop:kansshop@127.0.0.1:$pg_port/$db_name"

cd "$backend_dir"
env -i \
  PATH="$PATH" \
  ENV_FILE="$dotenv_file" \
  TEST_DATABASE_URL="$database_url" \
  BOT_TOKEN="123456:synthetic-purchase-test-token" \
  BOT_USERNAME="purchase_test_bot" \
  WEBHOOK_URL="" \
  WEBHOOK_SECRET="synthetic-purchase-webhook-secret" \
  ADMIN_IDS="" \
  ERROR_CHANNEL_ID="" \
  ORDERS_CHANNEL_ID="" \
  REQUIRED_CHANNEL_ID="" \
  REQUIRED_CHANNEL_URL="" \
  DATABASE_URL="$database_url" \
  DATABASE_URL_SYNC="$sync_database_url" \
  REDIS_URL="redis://127.0.0.1:$redis_port/0" \
  JWT_SECRET="synthetic-purchase-jwt-secret-key-at-least-32-bytes-long" \
  MEDIA_ROOT="$media_root" \
  PRIVATE_MEDIA_ROOT="$private_media_root" \
  MEDIA_BASE_URL="http://127.0.0.1/media" \
  "$venv_dir/bin/python" -m pytest "$@"
