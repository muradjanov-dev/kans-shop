from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.exceptions import OrderAlreadyProcessedError
from app.db.models.admin import Admin
from app.db.models.cart import Cart, CartItem
from app.db.models.category import Category
from app.db.models.enums import AdminRole, OrderStatus, OrderType, PaymentMethod
from app.db.models.order import Order
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.product import Product
from app.db.models.setting import Setting
from app.db.repositories import cart_repository, setting_repository
from app.services import cart_service, order_service, purchase_service


async def _prepare_api_cart(case, *, quantity: int = 2) -> None:
    await _prepare_user_cart(case, case.user_id, quantity=quantity)


async def _prepare_user_cart(case, user_id: int, *, quantity: int = 2) -> None:
    async with case.session_maker() as session:
        if not hasattr(case, "_previous_checkout_settings"):
            current_settings = await setting_repository.get_all(session)
            keys = (
                "is_shop_open",
                "min_order_amount",
                "delivery_fee",
                "free_delivery_from",
                "card_number",
                "card_holder",
            )
            case._previous_checkout_settings = {
                key: (key in current_settings, current_settings.get(key)) for key in keys
            }
        product = await session.get(Product, case.product_id)
        assert product is not None
        session.add(Cart(user_id=user_id, is_active=True))
        await session.flush()
        cart = await session.scalar(select(Cart).where(Cart.user_id == user_id))
        assert cart is not None
        session.add(
            CartItem(
                cart_id=cart.id,
                product_id=case.product_id,
                quantity=quantity,
                price_snapshot=product.price,
            )
        )
        for key, value in {
            "is_shop_open": True,
            "min_order_amount": 0,
            "delivery_fee": 0,
            "free_delivery_from": 0,
        }.items():
            await setting_repository.set_value(session, key, value)
        await session.commit()


async def _delete_case_orders(case) -> None:
    async with case.session_maker() as session:
        await session.execute(
            delete(Order).where(Order.user_id.in_([case.user_id, case.other_user_id]))
        )
        previous = getattr(case, "_previous_checkout_settings", None)
        if previous is not None:
            for key, (existed, value) in previous.items():
                if existed:
                    await setting_repository.set_value(session, key, value)
                else:
                    await session.execute(delete(Setting).where(Setting.key == key))
        await session.commit()


async def _api_quote(case, *, token: str, order_type: OrderType = OrderType.PICKUP) -> dict:
    response = await case.client.post(
        "/api/v1/orders/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={"order_type": order_type.value, "payment_method": PaymentMethod.CASH.value},
    )
    assert response.status_code == 200
    return response.json()


def _api_checkout_payload(
    quote: dict,
    *,
    name: str = "Test Buyer",
    order_type: OrderType = OrderType.PICKUP,
    address: str | None = None,
) -> dict:
    payload = {
        "order_type": order_type.value,
        "customer_name": name,
        "customer_phone": "+998901234567",
        "payment_method": PaymentMethod.CASH.value,
        "purchase_contract_version": 1,
        "expected_total": quote["total"],
        "expected_quote": quote["quote_fingerprint"],
    }
    if address is not None:
        payload["address"] = address
    return payload


def _api_headers(case, *, token: str, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key,
    }


async def _create_legacy_order(case, *, quantity: int = 1) -> int:
    await _prepare_api_cart(case, quantity=quantity)
    response = await case.client.post(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {case.token}"},
        json={
            "order_type": OrderType.PICKUP.value,
            "customer_name": "Test Buyer",
            "customer_phone": "+998901234567",
            "payment_method": PaymentMethod.CASH.value,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_checkout_replay(test_engine: AsyncEngine) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)
            quote = await case.client.post(
                "/api/v1/orders/quote",
                headers={"Authorization": f"Bearer {case.token}"},
                json={
                    "order_type": OrderType.PICKUP.value,
                    "payment_method": PaymentMethod.CASH.value,
                },
            )
            assert quote.status_code == 200
            quote_data = quote.json()
            payload = {
                "order_type": OrderType.PICKUP.value,
                "customer_name": " Test Buyer ",
                "customer_phone": "+998901234567",
                "payment_method": PaymentMethod.CASH.value,
                "purchase_contract_version": 1,
                "expected_total": quote_data["total"],
                "expected_quote": quote_data["quote_fingerprint"],
            }
            headers = {
                "Authorization": f"Bearer {case.token}",
                "Idempotency-Key": "11111111-1111-4111-8111-111111111111",
            }
            created = await case.client.post("/api/v1/orders", headers=headers, json=payload)
            replay = await case.client.post(
                "/api/v1/orders",
                headers=headers,
                json={
                    **payload,
                    "customer_name": "Test Buyer",
                    "customer_phone": "90 123 45 67",
                },
            )

            assert created.status_code == 201
            assert replay.status_code == 200
            assert created.json()["id"] == replay.json()["id"]
            assert created.json()["customer_name"] == "Test Buyer"
            async with case.session_maker() as session:
                stock = await session.scalar(
                    select(Product.stock_qty).where(Product.id == case.product_id)
                )
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
            assert stock == 8
            assert order_count == 1
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_fingerprint_conflict(test_engine: AsyncEngine) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)
            quote = await case.client.post(
                "/api/v1/orders/quote",
                headers={"Authorization": f"Bearer {case.token}"},
                json={
                    "order_type": OrderType.PICKUP.value,
                    "payment_method": PaymentMethod.CASH.value,
                },
            )
            assert quote.status_code == 200
            quote_data = quote.json()
            headers = {
                "Authorization": f"Bearer {case.token}",
                "Idempotency-Key": "22222222-2222-4222-8222-222222222222",
            }
            payload = {
                "order_type": OrderType.PICKUP.value,
                "customer_name": "Test Buyer",
                "customer_phone": "+998901234567",
                "payment_method": PaymentMethod.CASH.value,
                "purchase_contract_version": 1,
                "expected_total": quote_data["total"],
                "expected_quote": quote_data["quote_fingerprint"],
            }
            created = await case.client.post("/api/v1/orders", headers=headers, json=payload)
            changed = await case.client.post(
                "/api/v1/orders",
                headers=headers,
                json={**payload, "customer_name": "Different Buyer"},
            )

            assert created.status_code == 201
            assert changed.status_code == 409
            assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            async with case.session_maker() as session:
                stock = await session.scalar(
                    select(Product.stock_qty).where(Product.id == case.product_id)
                )
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
            assert stock == 8
            assert order_count == 1
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_contract_requires_version_quote_and_uuid(
    test_engine: AsyncEngine,
) -> None:
    from tests.api_helpers import make_api_case

    requests = (
        (
            {
                "order_type": OrderType.PICKUP.value,
                "customer_name": "Test Buyer",
                "customer_phone": "+998901234567",
                "purchase_contract_version": 2,
                "expected_total": "10000.00",
                "expected_quote": "a" * 64,
            },
            "11111111-1111-4111-8111-111111111111",
        ),
        (
            {
                "order_type": OrderType.PICKUP.value,
                "customer_name": "Test Buyer",
                "customer_phone": "+998901234567",
                "purchase_contract_version": 1,
                "expected_total": "10000.00",
            },
            "22222222-2222-4222-8222-222222222222",
        ),
        (
            {
                "order_type": OrderType.PICKUP.value,
                "customer_name": "Test Buyer",
                "customer_phone": "+998901234567",
                "purchase_contract_version": 1,
                "expected_total": "10000.00",
                "expected_quote": "a" * 64,
            },
            "not-a-uuid",
        ),
        (
            {
                "order_type": OrderType.PICKUP.value,
                "customer_name": "Test Buyer",
                "customer_phone": "+998901234567",
                "purchase_contract_version": 1,
                "expected_total": "10000.00",
                "expected_quote": "a" * 64,
            },
            None,
        ),
    )
    for payload, key in requests:
        async with make_api_case(test_engine) as case:
            try:
                await _prepare_api_cart(case)
                headers = {"Authorization": f"Bearer {case.token}"}
                if key is not None:
                    headers["Idempotency-Key"] = key
                response = await case.client.post(
                    "/api/v1/orders", headers=headers, json=payload
                )
                assert response.status_code == 422
                async with case.session_maker() as session:
                    stock = await session.scalar(
                        select(Product.stock_qty).where(Product.id == case.product_id)
                    )
                    cart_item_count = await session.scalar(
                        select(func.count())
                        .select_from(CartItem)
                        .join(Cart)
                        .where(Cart.user_id == case.user_id)
                    )
                    order_count = await session.scalar(
                        select(func.count())
                        .select_from(Order)
                        .where(Order.user_id == case.user_id)
                    )
                assert stock == 10
                assert cart_item_count == 1
                assert order_count == 0
            finally:
                await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_card_instructions_are_snapshotted(test_engine: AsyncEngine) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)
            async with case.session_maker() as session:
                await setting_repository.set_value(
                    session, "card_number", "8600 1234 5678 9012"
                )
                await setting_repository.set_value(session, "card_holder", "Kans Shop")
                await session.commit()
            quote = await case.client.post(
                "/api/v1/orders/quote",
                headers={"Authorization": f"Bearer {case.token}"},
                json={
                    "order_type": OrderType.PICKUP.value,
                    "payment_method": PaymentMethod.CARD_TRANSFER.value,
                },
            )
            assert quote.status_code == 200
            assert quote.json()["ready"] is True
            response = await case.client.post(
                "/api/v1/orders",
                headers=_api_headers(
                    case,
                    token=case.token,
                    key="99999999-9999-4999-8999-999999999999",
                ),
                json={
                    **_api_checkout_payload(quote.json(), name=" Test Buyer "),
                    "payment_method": PaymentMethod.CARD_TRANSFER.value,
                },
            )
            assert response.status_code == 201
            async with case.session_maker() as session:
                order = await session.get(Order, response.json()["id"])
            assert order is not None
            assert order.customer_name == "Test Buyer"
            assert order.checkout_key == "99999999-9999-4999-8999-999999999999"
            assert order.checkout_fingerprint is not None
            assert order.payment_instructions == {
                "card_number": "8600 1234 5678 9012",
                "card_holder": "Kans Shop",
            }
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_same_cart_concurrency(test_engine: AsyncEngine) -> None:
    import asyncio

    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)
            quote = await _api_quote(case, token=case.token)
            headers = _api_headers(
                case, token=case.token, key="33333333-3333-4333-8333-333333333333"
            )
            payload = _api_checkout_payload(quote)

            first, second = await asyncio.gather(
                case.client.post("/api/v1/orders", headers=headers, json=payload),
                case.client.post("/api/v1/orders", headers=headers, json=payload),
            )

            assert sorted((first.status_code, second.status_code)) == [200, 201]
            assert first.json()["id"] == second.json()["id"]
            async with case.session_maker() as session:
                product = await session.get(Product, case.product_id)
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
                cart_item_count = await session.scalar(
                    select(func.count())
                    .select_from(CartItem)
                    .join(Cart)
                    .where(Cart.user_id == case.user_id)
                )
            assert product is not None
            assert product.stock_qty == 8
            assert product.sold_count == 2
            assert order_count == 1
            assert cart_item_count == 0
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_last_unit_race(test_engine: AsyncEngine) -> None:
    import asyncio

    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_user_cart(case, case.user_id, quantity=1)
            await _prepare_user_cart(case, case.other_user_id, quantity=1)
            async with case.session_maker() as session:
                product = await session.get(Product, case.product_id)
                assert product is not None
                product.stock_qty = 1
                await session.commit()
            quote_a = await _api_quote(case, token=case.token)
            quote_b = await _api_quote(case, token=case.other_token)
            headers_a = _api_headers(
                case, token=case.token, key="44444444-4444-4444-8444-444444444444"
            )
            headers_b = _api_headers(
                case, token=case.other_token, key="55555555-5555-4555-8555-555555555555"
            )

            response_a, response_b = await asyncio.gather(
                case.client.post(
                    "/api/v1/orders",
                    headers=headers_a,
                    json=_api_checkout_payload(quote_a),
                ),
                case.client.post(
                    "/api/v1/orders",
                    headers=headers_b,
                    json=_api_checkout_payload(quote_b),
                ),
            )

            results = (response_a, response_b)
            assert sorted(response.status_code for response in results) == [201, 409]
            failed = next(response for response in results if response.status_code == 409)
            assert failed.json()["error"]["code"] == "OUT_OF_STOCK"
            async with case.session_maker() as session:
                product = await session.get(Product, case.product_id)
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id.in_([case.user_id, case.other_user_id]))
                )
                cart_counts = {
                    user_id: await session.scalar(
                        select(func.count())
                        .select_from(CartItem)
                        .join(Cart)
                        .where(Cart.user_id == user_id)
                    )
                    for user_id in (case.user_id, case.other_user_id)
                }
            assert product is not None
            assert product.stock_qty == 0
            assert product.sold_count == 1
            assert order_count == 1
            assert sorted(cart_counts.values()) == [0, 1]
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_same_total_quote_change(test_engine: AsyncEngine) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        other_product_id = None
        try:
            await _prepare_api_cart(case)
            quote = await _api_quote(case, token=case.token)
            async with case.session_maker() as session:
                original = await session.get(Product, case.product_id)
                assert original is not None
                alternate = Product(
                    category_id=original.category_id,
                    name_uz="Alternate pen",
                    name_ru="Alternate pen",
                    sku=f"ALT-{case.product_id}",
                    price=Decimal("10000"),
                    stock_qty=10,
                    unit=original.unit,
                )
                session.add(alternate)
                await session.flush()
                other_product_id = alternate.id
                cart = await session.scalar(select(Cart).where(Cart.user_id == case.user_id))
                assert cart is not None
                await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
                session.add(
                    CartItem(
                        cart_id=cart.id,
                        product_id=alternate.id,
                        quantity=1,
                        price_snapshot=alternate.price,
                    )
                )
                await session.commit()

            assert quote["total"] == "10000.00"
            response = await case.client.post(
                "/api/v1/orders",
                headers=_api_headers(
                    case,
                    token=case.token,
                    key="66666666-6666-4666-8666-666666666666",
                ),
                json=_api_checkout_payload(quote),
            )

            assert response.status_code == 409
            assert response.json()["error"]["code"] == "QUOTE_CHANGED"
            async with case.session_maker() as session:
                original = await session.get(Product, case.product_id)
                alternate = await session.get(Product, other_product_id)
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
                item = await session.scalar(
                    select(CartItem).join(Cart).where(Cart.user_id == case.user_id)
                )
            assert original is not None and original.stock_qty == 10
            assert alternate is not None and alternate.stock_qty == 10
            assert order_count == 0
            assert item is not None and item.product_id == other_product_id
        finally:
            await _delete_case_orders(case)
            if other_product_id is not None:
                async with case.session_maker() as session:
                    await session.execute(
                        delete(Product).where(Product.id == other_product_id)
                    )
                    await session.commit()


@pytest.mark.asyncio
async def test_checkout_stock_error_preserves_cart(test_engine: AsyncEngine) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)
            quote = await _api_quote(case, token=case.token)
            async with case.session_maker() as session:
                product = await session.get(Product, case.product_id)
                assert product is not None
                product.stock_qty = 1
                await session.commit()

            response = await case.client.post(
                "/api/v1/orders",
                headers=_api_headers(
                    case,
                    token=case.token,
                    key="77777777-7777-4777-8777-777777777777",
                ),
                json=_api_checkout_payload(quote),
            )

            assert response.status_code == 409
            assert response.json()["error"]["code"] == "OUT_OF_STOCK"
            async with case.session_maker() as session:
                stock = await session.scalar(
                    select(Product.stock_qty).where(Product.id == case.product_id)
                )
                cart_item = await session.scalar(
                    select(CartItem).join(Cart).where(Cart.user_id == case.user_id)
                )
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
            assert stock == 1
            assert cart_item is not None and cart_item.quantity == 2
            assert order_count == 0
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_failure_rolls_back(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)

            async def fail_history(*args, **kwargs) -> None:
                raise RuntimeError("test failure after order, item, and stock writes")

            monkeypatch.setattr(
                "app.services.purchase_service.order_repository.add_status_history",
                fail_history,
            )
            with pytest.raises(RuntimeError, match="test failure"):
                async with case.session_maker() as session:
                    async with session.begin():
                        await purchase_service.submit_checkout(
                            session,
                            user_id=case.user_id,
                            command=purchase_service.CheckoutCommand(
                                order_type=OrderType.PICKUP,
                                customer_name="Test Buyer",
                                customer_phone="+998901234567",
                            ),
                            checkout_key=None,
                            expected_quote=None,
                            expected_total=None,
                            source="bot",
                            lang="uz",
                        )

            async with case.session_maker() as session:
                product = await session.get(Product, case.product_id)
                cart_item = await session.scalar(
                    select(CartItem).join(Cart).where(Cart.user_id == case.user_id)
                )
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
            assert product is not None
            assert product.stock_qty == 10
            assert product.sold_count == 0
            assert cart_item is not None and cart_item.quantity == 2
            assert order_count == 0
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_checkout_total_matches_rounded_delivery_fee(test_engine: AsyncEngine) -> None:
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case, quantity=1)
            async with case.session_maker() as session:
                await setting_repository.set_value(session, "delivery_fee", "20.005")
                await setting_repository.set_value(session, "free_delivery_from", "999999")
                await session.commit()

            quote = await _api_quote(case, token=case.token, order_type=OrderType.DELIVERY)
            assert quote["delivery_fee"] == "20.01"
            assert quote["total"] == "5020.01"
            created = await case.client.post(
                "/api/v1/orders",
                headers=_api_headers(
                    case,
                    token=case.token,
                    key="88888888-8888-4888-8888-888888888888",
                ),
                json=_api_checkout_payload(
                    quote, order_type=OrderType.DELIVERY, address="Chilonzor 9"
                ),
            )
            assert created.status_code == 201
            assert Decimal(created.json()["total"]) == Decimal("5020.01")
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_concurrent_cancel_and_checkout_restore_stock_once(
    test_engine: AsyncEngine,
) -> None:
    import asyncio

    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            order_id = await _create_legacy_order(case, quantity=3)
            await _prepare_user_cart(case, case.other_user_id, quantity=2)
            barrier = asyncio.Barrier(3)

            async def cancel_order() -> object:
                async with case.session_maker() as session, session.begin():
                    order = await order_service.get_order(session, order_id)
                    await barrier.wait()
                    return await order_service.cancel_order(
                        session, order, admin_id=None, reason="Race test"
                    )

            async def checkout_other_customer() -> object:
                async with case.session_maker() as session, session.begin():
                    await barrier.wait()
                    return await purchase_service.submit_checkout(
                        session,
                        user_id=case.other_user_id,
                        command=purchase_service.CheckoutCommand(
                            order_type=OrderType.PICKUP,
                            customer_name="Other Buyer",
                            customer_phone="+998901234567",
                        ),
                        checkout_key=None,
                        expected_quote=None,
                        expected_total=None,
                        source="bot",
                        lang="uz",
                    )

            results = await asyncio.wait_for(
                asyncio.gather(
                    cancel_order(),
                    cancel_order(),
                    checkout_other_customer(),
                    return_exceptions=True,
                ),
                timeout=10,
            )

            cancel_results = [
                result for result in results[:2] if not isinstance(result, Exception)
            ]
            cancel_errors = [result for result in results[:2] if isinstance(result, Exception)]
            assert len(cancel_results) == 1
            assert len(cancel_errors) == 1
            assert isinstance(cancel_errors[0], OrderAlreadyProcessedError)
            assert not isinstance(results[2], Exception)
            async with case.session_maker() as session:
                order = await order_service.get_order(session, order_id)
                product = await session.get(Product, case.product_id)
                cancelled_events = await session.scalar(
                    select(func.count())
                    .select_from(OrderStatusHistory)
                    .where(
                        OrderStatusHistory.order_id == order_id,
                        OrderStatusHistory.to_status == OrderStatus.CANCELLED,
                    )
                )
                other_orders = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.other_user_id)
                )
            assert order.status == OrderStatus.CANCELLED
            assert product is not None
            assert product.stock_qty == 8
            assert product.sold_count == 2
            assert cancelled_events == 1
            assert other_orders == 1
        finally:
            await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_concurrent_confirm_and_cancel_reload_order_status(
    test_engine: AsyncEngine,
) -> None:
    import asyncio

    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        admin_id = None
        try:
            order_id = await _create_legacy_order(case, quantity=3)
            async with case.session_maker() as session:
                admin = Admin(
                    telegram_id=9_876_543_210,
                    full_name="Checkout race admin",
                    role=AdminRole.SUPERADMIN,
                )
                session.add(admin)
                await session.commit()
                admin_id = admin.id
            barrier = asyncio.Barrier(2)

            async def confirm_stale_order() -> object:
                async with case.session_maker() as session, session.begin():
                    order = await order_service.get_order(session, order_id)
                    await barrier.wait()
                    return await order_service.confirm_order(session, order, admin_id=admin_id)

            async def cancel_stale_order() -> object:
                async with case.session_maker() as session, session.begin():
                    order = await order_service.get_order(session, order_id)
                    await barrier.wait()
                    return await order_service.cancel_order(
                        session, order, admin_id=None, reason="Race test"
                    )

            confirmed, cancelled = await asyncio.wait_for(
                asyncio.gather(
                    confirm_stale_order(), cancel_stale_order(), return_exceptions=True
                ),
                timeout=10,
            )
            confirm_succeeded = not isinstance(confirmed, Exception)
            assert confirm_succeeded or isinstance(confirmed, OrderAlreadyProcessedError)
            assert not isinstance(cancelled, Exception)

            async with case.session_maker() as session:
                order = await order_service.get_order(session, order_id)
                product = await session.get(Product, case.product_id)
                history = list(
                    (
                        await session.scalars(
                            select(OrderStatusHistory).where(
                                OrderStatusHistory.order_id == order_id
                            )
                        )
                    ).all()
                )
            assert order.status == OrderStatus.CANCELLED
            assert sum(event.to_status == OrderStatus.CANCELLED for event in history) == 1
            assert sum(event.to_status == OrderStatus.CONFIRMED for event in history) == int(
                confirm_succeeded
            )
            assert product is not None
            assert product.stock_qty == 10
            assert product.sold_count == 0
        finally:
            await _delete_case_orders(case)
            if admin_id is not None:
                async with case.session_maker() as session:
                    admin = await session.get(Admin, admin_id)
                    if admin is not None:
                        await session.delete(admin)
                        await session.commit()


@pytest.mark.asyncio
async def test_hidden_ancestor_cannot_be_added_or_checked_out(
    db_session: AsyncSession, user, category: Category, product: Product
) -> None:
    from app.core.exceptions import CheckoutUnavailableError, ProductNotFoundError
    from app.services.checkout_quote import quote_checkout
    from app.services.purchase_service import CheckoutCommand, submit_checkout

    root = Category(
        name_uz="Hidden root",
        name_ru="Hidden root",
        slug="hidden-root",
        is_active=False,
    )
    db_session.add(root)
    await db_session.flush()
    category.parent_id = root.id
    await db_session.flush()

    with pytest.raises(ProductNotFoundError):
        await cart_service.add_item(db_session, user.id, product.id, quantity=1)

    cart = await cart_repository.get_active_cart(db_session, user.id)
    assert cart is not None
    db_session.add(
        CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=1,
            price_snapshot=product.price,
        )
    )
    for key, value in {
        "is_shop_open": True,
        "min_order_amount": 0,
    }.items():
        await setting_repository.set_value(db_session, key, value)

    quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CASH,
    )
    assert not quote.ready
    assert quote.quote_fingerprint is None
    with pytest.raises(CheckoutUnavailableError):
        await submit_checkout(
            db_session,
            user_id=user.id,
            command=CheckoutCommand(
                order_type=OrderType.PICKUP,
                customer_name="Test Buyer",
                customer_phone="+998901234567",
            ),
            checkout_key=None,
            expected_quote=None,
            expected_total=None,
            source="bot",
            lang="uz",
        )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart.id)
        )
        == 1
    )
    await db_session.refresh(product)
    assert product.stock_qty == 10
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Order).where(Order.user_id == user.id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_checkout_rejects_invalid_customer_fields(
    test_engine: AsyncEngine, db_session: AsyncSession, user
) -> None:
    from app.core.exceptions import CheckoutValidationError
    from app.services.purchase_service import CheckoutCommand, submit_checkout
    from tests.api_helpers import make_api_case

    invalid_payloads = (
        {
            "order_type": OrderType.DELIVERY.value,
            "customer_name": "   ",
            "customer_phone": "+998901234567",
            "address": "Chilonzor 9",
        },
        {
            "order_type": OrderType.DELIVERY.value,
            "customer_name": "B" * 129,
            "customer_phone": "+998901234567",
            "address": "Chilonzor 9",
        },
        {
            "order_type": OrderType.DELIVERY.value,
            "customer_name": "Test Buyer",
            "customer_phone": "+998000000000",
            "address": "Chilonzor 9",
        },
        {
            "order_type": OrderType.DELIVERY.value,
            "customer_name": "Test Buyer",
            "customer_phone": "+998901234567",
        },
    )
    for payload in invalid_payloads:
        with pytest.raises(CheckoutValidationError):
            await submit_checkout(
                db_session,
                user_id=user.id,
                command=CheckoutCommand(
                    order_type=OrderType(payload["order_type"]),
                    customer_name=payload["customer_name"],
                    customer_phone=payload["customer_phone"],
                    address=payload.get("address"),
                ),
                checkout_key=None,
                expected_quote=None,
                expected_total=None,
                source="bot",
                lang="uz",
            )

    for payload in invalid_payloads:
        async with make_api_case(test_engine) as case:
            try:
                await _prepare_api_cart(case)
                response = await case.client.post(
                    "/api/v1/orders",
                    headers={"Authorization": f"Bearer {case.token}"},
                    json=payload,
                )
                assert response.status_code == 422
                async with case.session_maker() as session:
                    stock = await session.scalar(
                        select(Product.stock_qty).where(Product.id == case.product_id)
                    )
                    cart_item = await session.scalar(
                        select(CartItem).join(Cart).where(Cart.user_id == case.user_id)
                    )
                    order_count = await session.scalar(
                        select(func.count())
                        .select_from(Order)
                        .where(Order.user_id == case.user_id)
                    )
                assert stock == 10
                assert cart_item is not None and cart_item.quantity == 2
                assert order_count == 0
            finally:
                await _delete_case_orders(case)


@pytest.mark.asyncio
async def test_legacy_card_requires_reload(test_engine: AsyncEngine) -> None:
    """A legacy client cannot create a card-transfer order from a stale quote."""
    from tests.api_helpers import make_api_case

    async with make_api_case(test_engine) as case:
        try:
            await _prepare_api_cart(case)

            response = await case.client.post(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {case.token}"},
                json={
                    "order_type": "pickup",
                    "customer_name": "Test Buyer",
                    "customer_phone": "+998901234567",
                    "payment_method": "card_transfer",
                },
            )

            assert response.status_code == 409
            assert response.json()["error"]["code"] == "CLIENT_UPDATE_REQUIRED"
            async with case.session_maker() as session:
                stock = await session.scalar(
                    select(Product.stock_qty).where(Product.id == case.product_id)
                )
                cart_items = await session.scalar(
                    select(func.count())
                    .select_from(CartItem)
                    .join(Cart)
                    .where(Cart.user_id == case.user_id)
                )
                order_count = await session.scalar(
                    select(func.count())
                    .select_from(Order)
                    .where(Order.user_id == case.user_id)
                )
            assert stock == 10
            assert cart_items == 1
            assert order_count == 0
        finally:
            await _delete_case_orders(case)
