from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models.cart import Cart, CartItem

from .api_helpers import IMAGE_URL, ApiCase, make_api_case


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_empty_cart(payload: dict) -> None:
    assert payload["items"] == []
    assert payload["items_count"] == 0
    assert Decimal(payload["subtotal"]) == Decimal("0")


def _assert_product_image(payload: dict, *, quantity: int, subtotal: str) -> None:
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["quantity"] == quantity
    assert Decimal(item["product"]["price"]) == Decimal("5000")
    assert item["product"]["images"][0]["url"] == IMAGE_URL
    assert payload["items_count"] == quantity
    assert Decimal(payload["subtotal"]) == Decimal(subtotal)


async def _seed_cart(case: ApiCase) -> None:
    """Commit cart data before HTTP requests so each request reads in a fresh session."""
    async with case.session_maker() as session:
        cart = Cart(user_id=case.user_id)
        session.add(cart)
        await session.flush()
        session.add(
            CartItem(
                cart_id=cart.id,
                product_id=case.product_id,
                quantity=2,
                price_snapshot=Decimal("5000"),
            )
        )
        await session.commit()


async def test_cart_api_serializes_images_in_fresh_sessions(
    test_engine: AsyncEngine,
) -> None:
    async with make_api_case(test_engine) as case:
        added = await case.client.post(
            "/api/v1/cart/items",
            headers=_auth(case.token),
            json={"product_id": case.product_id, "quantity": 2},
        )
        assert added.status_code == 201
        _assert_product_image(added.json(), quantity=2, subtotal="10000")

        fresh_get = await case.client.get("/api/v1/cart", headers=_auth(case.token))
        assert fresh_get.status_code == 200
        _assert_product_image(fresh_get.json(), quantity=2, subtotal="10000")

        updated = await case.client.patch(
            f"/api/v1/cart/items/{case.product_id}",
            headers=_auth(case.token),
            json={"quantity": 3},
        )
        assert updated.status_code == 200
        _assert_product_image(updated.json(), quantity=3, subtotal="15000")

        removed = await case.client.delete(
            f"/api/v1/cart/items/{case.product_id}", headers=_auth(case.token)
        )
        assert removed.status_code == 200
        _assert_empty_cart(removed.json())

        added_again = await case.client.post(
            "/api/v1/cart/items",
            headers=_auth(case.token),
            json={"product_id": case.product_id, "quantity": 1},
        )
        assert added_again.status_code == 201
        _assert_product_image(added_again.json(), quantity=1, subtotal="5000")

        cleared = await case.client.delete("/api/v1/cart", headers=_auth(case.token))
        assert cleared.status_code == 200
        _assert_empty_cart(cleared.json())


async def test_new_empty_cart_serializes(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        response = await case.client.get("/api/v1/cart", headers=_auth(case.token))

        assert response.status_code == 200
        _assert_empty_cart(response.json())


async def test_cart_api_isolates_users(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        await _seed_cart(case)

        own_cart = await case.client.get("/api/v1/cart", headers=_auth(case.token))
        assert own_cart.status_code == 200
        _assert_product_image(own_cart.json(), quantity=2, subtotal="10000")

        other_cart = await case.client.get("/api/v1/cart", headers=_auth(case.other_token))
        assert other_cart.status_code == 200
        _assert_empty_cart(other_cart.json())
