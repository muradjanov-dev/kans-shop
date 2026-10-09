"""Shared per-bot Telegram pacing for outbox and broadcast workers.

Task 10 should call :func:`acquire_telegram_slot` before every Telegram send. The Redis sorted
set is keyed by bot ID, so API instances and worker types reserve from the same rolling one-second
window. The cap is intentionally 20 calls per second.
"""

import asyncio
from datetime import datetime
from uuid import uuid4

from redis.asyncio import Redis

_RESERVE_SLOT = """
local key = KEYS[1]
local server_time = redis.call('TIME')
local now_ms = tonumber(server_time[1]) * 1000 + math.floor(tonumber(server_time[2]) / 1000)
local token = ARGV[2] .. ':' .. ARGV[1]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - 1000)
if redis.call('ZCARD', key) < 20 then
    redis.call('ZADD', key, now_ms, token)
    redis.call('PEXPIRE', key, 2000)
    return 0
end
local first = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
return math.max(1, tonumber(first[2]) + 1000 - now_ms)
"""


async def acquire_telegram_slot(redis: Redis, *, bot_id: int, now: datetime) -> None:
    """Wait until this bot has a slot in the shared rolling 20-per-second window."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    key = f"telegram:pacing:{bot_id}"
    token = uuid4().hex
    while True:
        delay_ms = await redis.eval(
            _RESERVE_SLOT,
            1,
            key,
            int(now.timestamp() * 1000),
            token,
        )
        if not delay_ms:
            return
        # Redis scores use millisecond precision; a small margin prevents early wakeups from
        # crossing the one-second boundary while still well below Telegram's practical latency.
        await asyncio.sleep((float(delay_ms) + 2) / 1000)
