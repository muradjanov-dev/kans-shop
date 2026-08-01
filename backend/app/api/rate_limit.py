from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.redis import get_redis

GENERAL_LIMIT = 20
GENERAL_WINDOW_SECONDS = 60
CHECKOUT_LIMIT = 3
CHECKOUT_WINDOW_SECONDS = 60
CHECKOUT_PATH = "/api/v1/orders"


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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """20 req/min per IP across the API, plus a tighter 3/min gate on checkout, per
    docs/ASSUMPTIONS.md section 10. Applies only under /api/v1 — webhook/media are exempt."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if not await _under_limit(
            f"ratelimit:general:{client_ip}", GENERAL_LIMIT, GENERAL_WINDOW_SECONDS
        ):
            return _rate_limited_response("Too many requests, please slow down")

        is_checkout = request.method == "POST" and request.url.path == CHECKOUT_PATH
        if is_checkout and not await _under_limit(
            f"ratelimit:checkout:{client_ip}", CHECKOUT_LIMIT, CHECKOUT_WINDOW_SECONDS
        ):
            return _rate_limited_response("Too many checkout attempts, please wait")

        return await call_next(request)
