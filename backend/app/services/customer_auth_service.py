import secrets
import time

from redis.asyncio import Redis

from app.core.exceptions import RateLimitedError, UnauthorizedError

CUSTOMER_CODE_TTL_SECONDS = 300
CUSTOMER_CODE_COOLDOWN_SECONDS = 60
CUSTOMER_CODE_KEY_PREFIX = "customer_login:code:"
CUSTOMER_USER_KEY_PREFIX = "customer_login:user:"
CUSTOMER_ISSUANCE_THROTTLE_KEY_PREFIX = "customer_login:throttle:issue:"


class InvalidOrExpiredCustomerCodeError(UnauthorizedError):
    code = "INVALID_OR_EXPIRED_CODE"


_ISSUE_CODE_SCRIPT = """
local issued_at = redis.call('GET', KEYS[3])
if issued_at and tonumber(ARGV[2]) - tonumber(issued_at) < tonumber(ARGV[4]) then
    return -1
end
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 0
end
local previous_code = redis.call('GET', KEYS[2])
if previous_code then
    redis.call('DEL', ARGV[5] .. previous_code)
end
redis.call('SET', KEYS[1], ARGV[6], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[3])
redis.call('SET', KEYS[3], ARGV[2], 'EX', ARGV[4])
return 1
"""

_CONSUME_CODE_SCRIPT = """
local telegram_id = redis.call('GET', KEYS[1])
if not telegram_id then
    return false
end
redis.call('DEL', KEYS[1])
local user_key = ARGV[1] .. telegram_id
if redis.call('GET', user_key) == ARGV[2] then
    redis.call('DEL', user_key)
end
return telegram_id
"""


async def issue_customer_code(redis: Redis, telegram_id: int) -> str:
    """Issue an eight-digit one-time customer code and replace any older code atomically."""
    user_key = f"{CUSTOMER_USER_KEY_PREFIX}{telegram_id}"
    throttle_key = f"{CUSTOMER_ISSUANCE_THROTTLE_KEY_PREFIX}{telegram_id}"
    issued_at = int(time.time())

    # A collision is extraordinarily unlikely, but a stored code must never be replaced by
    # another customer's code. Retry with a fresh candidate while leaving Redis unchanged.
    for _ in range(16):
        code = f"{secrets.randbelow(100_000_000):08d}"
        result = await redis.eval(
            _ISSUE_CODE_SCRIPT,
            3,
            f"{CUSTOMER_CODE_KEY_PREFIX}{code}",
            user_key,
            throttle_key,
            code,
            issued_at,
            CUSTOMER_CODE_TTL_SECONDS,
            CUSTOMER_CODE_COOLDOWN_SECONDS,
            CUSTOMER_CODE_KEY_PREFIX,
            telegram_id,
        )
        if result == 1:
            return code
        if result == -1:
            raise RateLimitedError("Please wait before requesting another login code")

    raise RuntimeError("Could not allocate a unique customer login code")


async def consume_customer_code(redis: Redis, code: str) -> int:
    """Consume a customer code and its reverse user mapping in one Redis operation."""
    result = await redis.eval(
        _CONSUME_CODE_SCRIPT,
        1,
        f"{CUSTOMER_CODE_KEY_PREFIX}{code}",
        CUSTOMER_USER_KEY_PREFIX,
        code,
    )
    if result is None:
        raise InvalidOrExpiredCustomerCodeError("Invalid or expired code")
    return int(result)
