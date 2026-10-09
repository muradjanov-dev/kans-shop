from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cart import Cart, CartItem
from app.db.models.category import Category
from app.db.models.enums import OrderType, PaymentMethod, PaymentProvider, ProductUnit
from app.db.models.product import Product
from app.db.models.setting import Setting
from app.db.repositories import setting_repository
from app.services import payment_service


def _quote_checkout_function():
    from app.services.checkout_quote import quote_checkout

    return quote_checkout


def _load_checkout_settings_function():
    from app.services.checkout_settings import load_checkout_settings

    return load_checkout_settings


async def _set_checkout_settings(session: AsyncSession, **settings: object) -> None:
    for key, value in {
        "is_shop_open": True,
        "min_order_amount": 0,
        "delivery_fee": 0,
        "free_delivery_from": 0,
        **settings,
    }.items():
        await setting_repository.set_value(session, key, value)


async def _replace_cart(
    session: AsyncSession,
    user_id: int,
    products: list[tuple[Product, int]],
) -> None:
    cart = await session.scalar(
        select(Cart).where(Cart.user_id == user_id, Cart.is_active.is_(True))
    )
    if cart is None:
        cart = Cart(user_id=user_id, is_active=True)
        session.add(cart)
        await session.flush()
    await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    for product, quantity in products:
        session.add(
            CartItem(
                cart_id=cart.id,
                product_id=product.id,
                quantity=quantity,
                price_snapshot=product.price,
            )
        )
    await session.flush()


async def test_quote_settings_validation(db_session, user, product) -> None:
    quote_checkout = _quote_checkout_function()
    load_checkout_settings = _load_checkout_settings_function()
    await _set_checkout_settings(db_session)
    await _replace_cart(db_session, user.id, [(product, 1)])

    # Each invalid source value is unavailable to delivery quotes; the API must not turn
    # absent or bad configuration into an implicit zero-fee checkout.
    invalid_values = (
        ("missing", None),
        ("null", None),
        ("malformed", "twenty thousand"),
        ("negative", -1),
    )
    for key in ("delivery_fee", "free_delivery_from", "min_order_amount"):
        for state, value in invalid_values:
            await _set_checkout_settings(db_session)
            if state == "missing":
                await db_session.execute(delete(Setting).where(Setting.key == key))
            else:
                await setting_repository.set_value(db_session, key, value)

            settings = await load_checkout_settings(db_session)
            assert settings.field_states[key] == state
            parsed = getattr(settings, key)
            assert (
                parsed is None
                if state in {"missing", "null", "malformed"}
                else parsed == Decimal("-1")
            )
            quote = await quote_checkout(
                db_session,
                user_id=user.id,
                order_type=OrderType.DELIVERY,
                payment_method=PaymentMethod.CASH,
            )
            assert not quote.ready, (key, state)
            assert any("CHECKOUT_UNAVAILABLE" in reason for reason in quote.reasons), (
                key,
                state,
            )

    await _set_checkout_settings(db_session)
    settings = await load_checkout_settings(db_session)
    assert settings.delivery_fee == Decimal("0")
    assert settings.free_delivery_from == Decimal("0")
    assert settings.min_order_amount == Decimal("0")
    zero_fee_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.DELIVERY,
        payment_method=PaymentMethod.CASH,
    )
    assert zero_fee_quote.ready
    assert zero_fee_quote.delivery_fee == Decimal("0")


async def test_quote_fee_boundary(db_session, user, product) -> None:
    quote_checkout = _quote_checkout_function()
    await _set_checkout_settings(
        db_session,
        min_order_amount=0,
        delivery_fee=20_000,
        free_delivery_from=10_001,
    )
    await _replace_cart(db_session, user.id, [(product, 2)])

    paid_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.DELIVERY,
        payment_method=PaymentMethod.CASH,
    )
    assert paid_quote.subtotal == Decimal("10000")
    assert paid_quote.delivery_fee == Decimal("20000")
    assert paid_quote.total == Decimal("30000")

    await setting_repository.set_value(db_session, "free_delivery_from", 10_000)
    free_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.DELIVERY,
        payment_method=PaymentMethod.CASH,
    )
    assert free_quote.subtotal == Decimal("10000")
    assert free_quote.delivery_fee == Decimal("0")
    assert free_quote.total == Decimal("10000")


async def test_quote_preorder_exemption(db_session, user, product) -> None:
    quote_checkout = _quote_checkout_function()
    await setting_repository.set_value(db_session, "is_shop_open", True)
    await _replace_cart(db_session, user.id, [(product, 2)])

    quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PREORDER,
        payment_method=PaymentMethod.CASH,
    )

    assert quote.ready
    assert quote.payment_methods == [PaymentMethod.CASH]
    assert quote.subtotal == Decimal("10000")
    assert quote.delivery_fee == Decimal("0")
    assert quote.total == Decimal("10000")


async def test_payment_method_readiness(
    db_session, user, product, category: Category, monkeypatch: pytest.MonkeyPatch
) -> None:
    quote_checkout = _quote_checkout_function()
    for key in (
        "click_service_id",
        "click_merchant_id",
        "click_merchant_user_id",
        "click_secret_key",
        "payme_merchant_id",
        "payme_secret_key",
        "paynet_merchant_id",
        "paynet_secret_key",
        "paynet_api_base_url",
    ):
        monkeypatch.setattr(payment_service.settings, key, "")
    monkeypatch.setattr(payment_service.settings, "click_service_id", "service")
    monkeypatch.setattr(payment_service.settings, "click_merchant_id", "merchant")
    monkeypatch.setattr(payment_service.settings, "click_merchant_user_id", "merchant-user")
    monkeypatch.setattr(payment_service.settings, "payme_merchant_id", "payme-merchant")
    monkeypatch.setattr(payment_service.settings, "paynet_merchant_id", "paynet-merchant")
    monkeypatch.setattr(
        payment_service.settings, "paynet_api_base_url", "https://paynet.example.test"
    )
    await _set_checkout_settings(db_session, card_number="8600 1111", card_holder=None)
    linked_product = Product(
        category_id=category.id,
        name_uz="Daftar",
        name_ru="Тетрадь",
        sku="QUOTE-LOT-LINK",
        price=Decimal("5000"),
        stock_qty=10,
        unit=ProductUnit.DONA,
        lot_url="https://lot.example.test/daftar",
    )
    db_session.add(linked_product)
    await db_session.flush()
    await _replace_cart(db_session, user.id, [(product, 1), (linked_product, 1)])

    cash_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CASH,
    )
    assert PaymentMethod.CASH in cash_quote.payment_methods
    assert PaymentMethod.CARD_TRANSFER not in cash_quote.payment_methods
    assert PaymentMethod.TENDER in cash_quote.payment_methods
    assert PaymentMethod.CLICK not in cash_quote.payment_methods
    assert PaymentMethod.PAYME not in cash_quote.payment_methods
    assert PaymentMethod.PAYNET not in cash_quote.payment_methods
    assert not payment_service.is_provider_configured(PaymentProvider.CLICK)
    assert not payment_service.is_provider_configured(PaymentProvider.PAYME)
    assert not payment_service.is_provider_configured(PaymentProvider.PAYNET)

    tender_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.TENDER,
    )
    assert tender_quote.ready
    assert any(product.name_uz in reason for reason in tender_quote.reasons)

    await setting_repository.set_value(db_session, "card_holder", "Kans Shop")
    monkeypatch.setattr(payment_service.settings, "click_service_id", "service")
    monkeypatch.setattr(payment_service.settings, "click_merchant_id", "merchant")
    monkeypatch.setattr(payment_service.settings, "click_merchant_user_id", "merchant-user")
    monkeypatch.setattr(payment_service.settings, "click_secret_key", "click-secret")
    monkeypatch.setattr(payment_service.settings, "payme_merchant_id", "payme-merchant")
    monkeypatch.setattr(payment_service.settings, "payme_secret_key", "payme-secret")
    monkeypatch.setattr(payment_service.settings, "paynet_merchant_id", "paynet-merchant")
    monkeypatch.setattr(payment_service.settings, "paynet_secret_key", "paynet-secret")
    monkeypatch.setattr(
        payment_service.settings, "paynet_api_base_url", "https://paynet.example.test"
    )

    ready_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CARD_TRANSFER,
    )
    assert ready_quote.ready
    assert PaymentMethod.CARD_TRANSFER in ready_quote.payment_methods
    assert PaymentMethod.CLICK in ready_quote.payment_methods
    assert PaymentMethod.PAYME in ready_quote.payment_methods
    assert PaymentMethod.PAYNET not in ready_quote.payment_methods
    assert payment_service.is_provider_configured(PaymentProvider.CLICK)
    assert payment_service.is_provider_configured(PaymentProvider.PAYME)
    assert not payment_service.is_provider_configured(PaymentProvider.PAYNET)


async def test_same_total_different_cart_changes_quote(
    db_session, user, product, category
) -> None:
    quote_checkout = _quote_checkout_function()
    await _set_checkout_settings(db_session, min_order_amount=0)
    other_product = Product(
        category_id=category.id,
        name_uz="Ruchka katta",
        name_ru="Большая ручка",
        sku="QUOTE-EQUAL-TOTAL",
        price=Decimal("10000"),
        stock_qty=10,
        unit=ProductUnit.DONA,
    )
    db_session.add(other_product)
    await db_session.flush()

    await _replace_cart(db_session, user.id, [(product, 2)])
    first = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CASH,
    )
    await _replace_cart(db_session, user.id, [(other_product, 1)])
    second = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CASH,
    )

    assert first.total == second.total == Decimal("10000")
    assert first.quote_fingerprint != second.quote_fingerprint


async def test_quote_revalidates_stock_without_fingerprinting_stock(
    db_session, user, product
) -> None:
    quote_checkout = _quote_checkout_function()
    await _set_checkout_settings(db_session, min_order_amount=0)
    await _replace_cart(db_session, user.id, [(product, 2)])
    ready_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CASH,
    )

    product.stock_qty = 1
    await db_session.flush()
    out_of_stock_quote = await quote_checkout(
        db_session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        payment_method=PaymentMethod.CASH,
    )

    assert ready_quote.ready
    assert not out_of_stock_quote.ready
    assert out_of_stock_quote.quote_fingerprint == ready_quote.quote_fingerprint
    assert any("Insufficient stock" in reason for reason in out_of_stock_quote.reasons)


@pytest.mark.asyncio
async def test_quote_api_returns_decimal_strings_and_public_readiness(test_engine) -> None:
    from tests.api_helpers import make_api_case

    keys = {
        "is_shop_open",
        "min_order_amount",
        "delivery_fee",
        "free_delivery_from",
        "card_number",
        "card_holder",
    }
    async with make_api_case(test_engine) as case:
        previous_settings: dict[str, object] = {}
        try:
            async with case.session_maker() as session:
                existing = await setting_repository.get_all(session)
                previous_settings = {key: existing[key] for key in keys if key in existing}
                product_row = await session.get(Product, case.product_id)
                assert product_row is not None
                session.add(Cart(user_id=case.user_id, is_active=True))
                await session.flush()
                cart = await session.scalar(select(Cart).where(Cart.user_id == case.user_id))
                assert cart is not None
                session.add(
                    CartItem(
                        cart_id=cart.id,
                        product_id=product_row.id,
                        quantity=2,
                        price_snapshot=product_row.price,
                    )
                )
                for key, value in {
                    "is_shop_open": True,
                    "min_order_amount": 0,
                    "delivery_fee": 20_000,
                    "free_delivery_from": 10_001,
                    "card_number": "8600 1111",
                    "card_holder": "Kans Shop",
                }.items():
                    await setting_repository.set_value(session, key, value)
                await session.commit()

            response = await case.client.post(
                "/api/v1/orders/quote",
                headers={"Authorization": f"Bearer {case.token}"},
                json={"order_type": "delivery", "payment_method": "cash"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert isinstance(payload["subtotal"], str)
            assert isinstance(payload["delivery_fee"], str)
            assert isinstance(payload["total"], str)
            assert Decimal(payload["subtotal"]) == Decimal("10000")
            assert Decimal(payload["delivery_fee"]) == Decimal("20000")
            assert Decimal(payload["total"]) == Decimal("30000")
            assert payload["ready"] is True
            assert payload["quote_fingerprint"]

            public = await case.client.get("/api/v1/settings/public")
            assert public.status_code == 200
            public_settings = public.json()
            assert "payment_method_readiness" in public_settings
            assert "click_secret_key" not in public_settings
            assert "payme_secret_key" not in public_settings
        finally:
            async with case.session_maker() as session:
                for key in keys:
                    if key in previous_settings:
                        await setting_repository.set_value(
                            session, key, previous_settings[key]
                        )
                    else:
                        await session.execute(delete(Setting).where(Setting.key == key))
                await session.commit()
