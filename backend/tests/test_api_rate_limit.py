import httpx
import pytest
from fastapi import FastAPI

from app.api import rate_limit


class WindowRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def eval(self, script: str, keys: int, key: str, seconds: int) -> int:
        return await self.incr(key)


@pytest.fixture
def rate_client(monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    redis = WindowRedis()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: redis)
    app = FastAPI()
    app.add_middleware(rate_limit.RateLimitMiddleware)

    @app.get("/api/v1/catalog/products")
    @app.get("/api/v1/catalog/categories")
    @app.get("/api/v1/admin/orders")
    @app.post("/api/v1/orders")
    @app.post("/api/v1/auth/customer/code")
    async def endpoint() -> dict[str, bool]:
        return {"ok": True}

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def test_normal_browsing_and_admin_polling_share_an_ip_without_lockout(
    rate_client: httpx.AsyncClient,
) -> None:
    # A customer searching/filtering and an admin polling from the same connection.
    async with rate_client as client:
        for _ in range(15):
            for path in (
                "/api/v1/catalog/products",
                "/api/v1/catalog/categories",
                "/api/v1/admin/orders",
            ):
                assert (await client.get(path)).status_code == 200
        for _ in range(3):
            assert (await client.post("/api/v1/orders")).status_code == 200
        assert (await client.post("/api/v1/orders")).status_code == 429


async def test_general_request_budget_still_blocks_excess_traffic(
    rate_client: httpx.AsyncClient,
) -> None:
    async with rate_client as client:
        for _ in range(rate_limit.GENERAL_LIMIT):
            assert (await client.get("/api/v1/catalog/products")).status_code == 200
        blocked = await client.get("/api/v1/catalog/categories")
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "RATE_LIMITED"


async def test_code_exchange_keeps_its_separate_strict_budget(
    rate_client: httpx.AsyncClient,
) -> None:
    async with rate_client as client:
        for _ in range(5):
            assert (await client.post("/api/v1/auth/customer/code")).status_code == 200
        assert (await client.post("/api/v1/auth/customer/code")).status_code == 429
