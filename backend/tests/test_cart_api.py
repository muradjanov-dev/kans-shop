from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models.cart import Cart, CartItem
from app.db.models.product import Product

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


async def test_add_replay_applies_delta_once(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        key = str(uuid4())
        headers = {**_auth(case.token), "Idempotency-Key": key}
        payload = {"product_id": case.product_id, "quantity": 2}

        first = await case.client.post("/api/v1/cart/items", headers=headers, json=payload)
        replay = await case.client.post("/api/v1/cart/items", headers=headers, json=payload)

        assert first.status_code == 201
        assert replay.status_code == 201
        _assert_product_image(first.json(), quantity=2, subtotal="10000")
        _assert_product_image(replay.json(), quantity=2, subtotal="10000")

        # A lost response can be retried after another cart mutation; replay returns the
        # current cart while still avoiding a second application of the original delta.
        await case.client.post(
            "/api/v1/cart/items",
            headers=_auth(case.token),
            json={"product_id": case.product_id, "quantity": 1},
        )
        current = await case.client.post("/api/v1/cart/items", headers=headers, json=payload)
        assert current.status_code == 201
        _assert_product_image(current.json(), quantity=3, subtotal="15000")


async def test_add_key_payload_conflict(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        headers = {**_auth(case.token), "Idempotency-Key": str(uuid4())}
        original = await case.client.post(
            "/api/v1/cart/items",
            headers=headers,
            json={"product_id": case.product_id, "quantity": 1},
        )
        changed = await case.client.post(
            "/api/v1/cart/items",
            headers=headers,
            json={"product_id": case.product_id, "quantity": 2},
        )

        assert original.status_code == 201
        assert changed.status_code == 409
        assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

        other_key = str(uuid4())
        await case.client.post(
            "/api/v1/cart/items",
            headers={**_auth(case.token), "Idempotency-Key": other_key},
            json={"product_id": case.product_id, "quantity": 1},
        )
        product_conflict = await case.client.post(
            "/api/v1/cart/items",
            headers={**_auth(case.token), "Idempotency-Key": other_key},
            json={"product_id": case.product_id + 999_999, "quantity": 1},
        )
        assert product_conflict.status_code == 409
        assert product_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_add_key_is_scoped_to_user(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        key = str(uuid4())
        own = await case.client.post(
            "/api/v1/cart/items",
            headers={**_auth(case.token), "Idempotency-Key": key},
            json={"product_id": case.product_id, "quantity": 1},
        )
        other = await case.client.post(
            "/api/v1/cart/items",
            headers={**_auth(case.other_token), "Idempotency-Key": key},
            json={"product_id": case.product_id, "quantity": 2},
        )
        own_replay = await case.client.post(
            "/api/v1/cart/items",
            headers={**_auth(case.token), "Idempotency-Key": key},
            json={"product_id": case.product_id, "quantity": 1},
        )

        assert own.status_code == other.status_code == own_replay.status_code == 201
        _assert_product_image(own.json(), quantity=1, subtotal="5000")
        _assert_product_image(other.json(), quantity=2, subtotal="10000")
        _assert_product_image(own_replay.json(), quantity=1, subtotal="5000")


async def test_minimum_and_zero_quantity(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        async with case.session_maker() as session:
            product = await session.get(Product, case.product_id)
            assert product is not None
            product.min_order_qty = 3
            await session.commit()

        added = await case.client.post(
            "/api/v1/cart/items",
            headers=_auth(case.token),
            json={"product_id": case.product_id, "quantity": 1},
        )
        assert added.status_code == 201
        _assert_product_image(added.json(), quantity=3, subtotal="15000")

        below_minimum = await case.client.patch(
            f"/api/v1/cart/items/{case.product_id}",
            headers=_auth(case.token),
            json={"quantity": 2},
        )
        assert below_minimum.status_code == 400
        assert below_minimum.json()["error"]["code"] == "MIN_ORDER_QUANTITY"

        removed = await case.client.patch(
            f"/api/v1/cart/items/{case.product_id}",
            headers=_auth(case.token),
            json={"quantity": 0},
        )
        assert removed.status_code == 200
        _assert_empty_cart(removed.json())
