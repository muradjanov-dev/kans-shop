from sqlalchemy.ext.asyncio import AsyncEngine

from .api_helpers import IMAGE_URL, make_api_case


async def test_showcase_lists_active_products_with_their_main_image(
    test_engine: AsyncEngine,
) -> None:
    async with make_api_case(test_engine) as case:
        response = await case.client.get("/api/v1/catalog/showcase")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=60"
    item = next(entry for entry in response.json() if entry["id"] == case.product_id)
    assert item == {
        "id": case.product_id,
        "name_uz": "Test pen",
        "name_ru": "Test pen",
        "price": "5000.00",
        "old_price": None,
        "image_url": IMAGE_URL,
        "is_featured": False,
        "min_order_qty": 1,
        "available": True,
    }


async def test_showcase_limit_is_bounded(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        too_many = await case.client.get("/api/v1/catalog/showcase", params={"limit": 501})

    assert too_many.status_code == 422
