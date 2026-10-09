import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.redis import get_redis

GENERAL_LIMIT = 20
GENERAL_WINDOW_SECONDS = 60
CHECKOUT_LIMIT = 3
CHECKOUT_WINDOW_SECONDS = 60
CHECKOUT_PATH = "/api/v1/orders"
CODE_EXCHANGE_LIMIT = 5
CODE_EXCHANGE_WINDOW_SECONDS = 300
CODE_EXCHANGE_PATHS = {
    "/api/v1/auth/customer/code",
    "/api/v1/auth/telegram/code",
}
_CODE_EXCHANGE_RATE_KEY_PREFIX = "ratelimit:auth_code:"

_ATOMIC_INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def _rate_limited_response(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMITED", "message": message, "details": {}}},
    )


async def _under_limit(key: str, limit: int, window_seconds: int) -> bool:
    redis = get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count <= limit


async def _under_atomic_limit(key: str, limit: int, window_seconds: int) -> bool:
    redis = get_redis()
    count = await redis.eval(_ATOMIC_INCREMENT_SCRIPT, 1, key, window_seconds)
    return int(count) <= limit


def trusted_client_ip(request: Request) -> str:
    """Return the peer address, trusting X-Forwarded-For only from a configured proxy."""
    client = request.client
    if client is None:
        return "unknown"

    peer_text = client.host
    try:
        peer = ipaddress.ip_address(peer_text)
    except ValueError:
        return peer_text or "unknown"

    trusted_networks = settings.trusted_proxy_networks

    def is_trusted(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(
            address.version == network.version and address in network
            for network in trusted_networks
        )

    if not is_trusted(peer):
        return str(peer)

    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return str(peer)

    try:
        forwarded = [ipaddress.ip_address(part.strip()) for part in forwarded_for.split(",")]
    except ValueError:
        return str(peer)

    chain = [*forwarded, peer]
    for address in reversed(chain):
        if not is_trusted(address):
            return str(address)
    return str(chain[0])


class RateLimitMiddleware(BaseHTTPMiddleware):
    """20 req/min per IP across the API, plus a tighter 3/min gate on checkout, per
    docs/ASSUMPTIONS.md section 10. Applies only under /api/v1 — webhook/media are exempt."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        client_ip = trusted_client_ip(request)

        if not await _under_limit(
            f"ratelimit:general:{client_ip}", GENERAL_LIMIT, GENERAL_WINDOW_SECONDS
        ):
            return _rate_limited_response("Too many requests, please slow down")

        if (
            request.method == "POST"
            and request.url.path in CODE_EXCHANGE_PATHS
            and not await _under_atomic_limit(
                f"{_CODE_EXCHANGE_RATE_KEY_PREFIX}{client_ip}",
                CODE_EXCHANGE_LIMIT,
                CODE_EXCHANGE_WINDOW_SECONDS,
            )
        ):
            return _rate_limited_response("Too many code attempts, please wait")

        is_checkout = request.method == "POST" and request.url.path == CHECKOUT_PATH
        if is_checkout and not await _under_limit(
            f"ratelimit:checkout:{client_ip}", CHECKOUT_LIMIT, CHECKOUT_WINDOW_SECONDS
        ):
            return _rate_limited_response("Too many checkout attempts, please wait")

        return await call_next(request)
