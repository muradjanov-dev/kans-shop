"""One-time admin panel login codes.

A code is issued either by the bot's /admin_login command or by the web login page, and is
always delivered to the admin's own Telegram chat. It is valid for five minutes and only the
newest code per admin works: issuing a new one revokes the previous one, so a "resend" never
leaves two live codes behind.
"""

import secrets

from redis.asyncio import Redis

ADMIN_LOGIN_KEY_PREFIX = "admin_login:"
ADMIN_LATEST_CODE_KEY_PREFIX = "admin_login:latest:"
ADMIN_CODE_REQUEST_COOLDOWN_KEY_PREFIX = "admin_login:cooldown:"
CODE_TTL_SECONDS = 300
REQUEST_COOLDOWN_SECONDS = 60

# Delete the previous code only while it still belongs to this admin: after it was used or
# expired, the same six digits may already have been issued to someone else.
_DELETE_IF_OWNED_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


async def issue_admin_login_code(redis: Redis, telegram_id: int) -> str:
    owner = str(telegram_id)
    latest_key = f"{ADMIN_LATEST_CODE_KEY_PREFIX}{owner}"
    previous = await redis.get(latest_key)
    previous_code = previous.decode() if isinstance(previous, bytes) else previous

    for _attempt in range(10):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if await redis.set(
            f"{ADMIN_LOGIN_KEY_PREFIX}{code}", owner, ex=CODE_TTL_SECONDS, nx=True
        ):
            break
    else:  # pragma: no cover - needs ~a million live codes
        raise RuntimeError("Could not allocate a unique admin login code")

    await redis.set(latest_key, code, ex=CODE_TTL_SECONDS)
    if previous_code and previous_code != code:
        await redis.eval(
            _DELETE_IF_OWNED_SCRIPT, 1, f"{ADMIN_LOGIN_KEY_PREFIX}{previous_code}", owner
        )
    return code


async def claim_request_slot(redis: Redis, telegram_id: int) -> bool:
    """At most one web-requested code per admin per cooldown window (no Telegram spam)."""
    claimed = await redis.set(
        f"{ADMIN_CODE_REQUEST_COOLDOWN_KEY_PREFIX}{telegram_id}",
        "1",
        ex=REQUEST_COOLDOWN_SECONDS,
        nx=True,
    )
    return bool(claimed)


async def release_request_slot(redis: Redis, telegram_id: int) -> None:
    await redis.delete(f"{ADMIN_CODE_REQUEST_COOLDOWN_KEY_PREFIX}{telegram_id}")
