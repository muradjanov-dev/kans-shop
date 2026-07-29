import asyncio
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.exceptions import (
    CartEmptyError,
    MinOrderAmountError,
    OrderAlreadyProcessedError,
    OutOfStockError,
)
from app.db.models.admin import Admin
from app.db.models.category import Category
from app.db.models.enums import OrderStatus, OrderType, ProductUnit
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.services import cart_service, order_service


async def _checkout_delivery(session: AsyncSession, user_id: int, **overrides) -> Order:
    kwargs = dict(
        user_id=user_id,
        order_type=OrderType.DELIVERY,
        customer_name="Test Customer",
        customer_phone="+998901234567",
        address="Chilonzor 9",
    )
    kwargs.update(overrides)
    return await order_service.checkout(session, **kwargs)


async def test_checkout_empty_cart_raises(db_session: AsyncSession, user: User) -> None:
    with pytest.raises(CartEmptyError):
        await _checkout_delivery(db_session, user.id)


async def test_checkout_happy_path_creates_order_and_decrements_stock(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await cart_service.add_item(db_session, user.id, product.id, quantity=3)

    order = await _checkout_delivery(db_session, user.id)

    assert order.order_number.startswith("KANS-")
    assert order.status == OrderStatus.NEW
    assert len(order.items) == 1
    assert order.items[0].quantity == 3
    assert order.subtotal == Decimal("5000") * 3

    await db_session.refresh(product)
    assert product.stock_qty == 7
    assert product.sold_count == 3

    cart = await cart_service.get_cart(db_session, user.id)
    assert cart.items == []


async def test_checkout_below_min_order_amount_raises(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 1_000_000)
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)

    with pytest.raises(MinOrderAmountError):
        await _checkout_delivery(db_session, user.id)


async def test_checkout_free_delivery_above_threshold(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await setting_repository.set_value(db_session, "delivery_fee", 20_000)
    await setting_repository.set_value(db_session, "free_delivery_from", 10_000)
    await cart_service.add_item(db_session, user.id, product.id, quantity=3)  # 15000 subtotal

    order = await _checkout_delivery(db_session, user.id)

    assert order.delivery_fee == Decimal("0")
    assert order.total == order.subtotal


async def test_checkout_pickup_has_no_delivery_fee_or_address(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)

    order = await _checkout_delivery(
        db_session, user.id, order_type=OrderType.PICKUP, address=None
    )

    assert order.delivery_fee == Decimal("0")
    assert order.address is None


async def test_checkout_preorder_skips_min_order_amount(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 1_000_000)
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)

    order = await _checkout_delivery(
        db_session, user.id, order_type=OrderType.PREORDER, address=None
    )

    assert order.status == OrderStatus.NEW


async def test_confirm_order_then_reject_double_confirm(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)
    order = await _checkout_delivery(db_session, user.id)

    confirmed = await order_service.confirm_order(db_session, order, admin_id=admin.id)
    assert confirmed.status == OrderStatus.CONFIRMED
    assert confirmed.confirmed_at is not None

    with pytest.raises(OrderAlreadyProcessedError):
        await order_service.confirm_order(db_session, order, admin_id=admin.id)


async def test_cancel_order_restores_stock(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await cart_service.add_item(db_session, user.id, product.id, quantity=4)
    order = await _checkout_delivery(db_session, user.id)
    await db_session.refresh(product)
    assert product.stock_qty == 6

    cancelled = await order_service.cancel_order(
        db_session, order, admin_id=admin.id, reason="Mahsulot tugagan"
    )

    assert cancelled.status == OrderStatus.CANCELLED
    await db_session.refresh(product)
    assert product.stock_qty == 10


async def test_cancel_completed_order_raises(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)
    order = await _checkout_delivery(db_session, user.id)
    await order_service.confirm_order(db_session, order, admin_id=admin.id)
    await order_service.advance_status(
        db_session, order, OrderStatus.PREPARING, admin_id=admin.id
    )
    await order_service.advance_status(
        db_session, order, OrderStatus.COMPLETED, admin_id=admin.id
    )

    with pytest.raises(OrderAlreadyProcessedError):
        await order_service.cancel_order(
            db_session, order, admin_id=admin.id, reason="too late"
        )


async def test_invalid_status_transition_raises(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    await setting_repository.set_value(db_session, "min_order_amount", 0)
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)
    order = await _checkout_delivery(db_session, user.id)

    with pytest.raises(OrderAlreadyProcessedError):
        # Cannot jump straight from NEW to DELIVERING.
        await order_service.advance_status(
            db_session, order, OrderStatus.DELIVERING, admin_id=admin.id
        )


async def test_concurrent_checkouts_never_oversell_stock(test_engine: AsyncEngine) -> None:
    """Two customers race to buy the last unit of a product with stock_qty=1. Exactly one
    checkout must succeed and the other must fail with OutOfStockError — this is the
    'qoldiq yetmasa buyurtma yaratilmaydi (race condition)' requirement from the spec."""
    setup_maker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with setup_maker() as setup_session:
        category = Category(name_uz="Race", name_ru="Race", slug="race-cat")
        setup_session.add(category)
        await setup_session.flush()

        scarce_product = Product(
            category_id=category.id,
            name_uz="Yagona mahsulot",
            name_ru="Единственный товар",
            sku="RACE-SKU-1",
            price=Decimal("1000"),
            stock_qty=1,
            unit=ProductUnit.DONA,
        )
        setup_session.add(scarce_product)

        user_a = User(telegram_id=222222, first_name="A")
        user_b = User(telegram_id=333333, first_name="B")
        setup_session.add_all([user_a, user_b])
        await setup_session.flush()
        await setup_session.commit()

        await setting_repository.set_value(setup_session, "min_order_amount", 0)
        await cart_service.add_item(setup_session, user_a.id, scarce_product.id, quantity=1)
        await cart_service.add_item(setup_session, user_b.id, scarce_product.id, quantity=1)
        await setup_session.commit()

        product_id, user_a_id, user_b_id = scarce_product.id, user_a.id, user_b.id

    async def run_checkout(user_id: int) -> Order:
        async with setup_maker() as session:
            async with session.begin():
                order = await _checkout_delivery(session, user_id)
            return order

    results = await asyncio.gather(
        run_checkout(user_a_id), run_checkout(user_b_id), return_exceptions=True
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], OutOfStockError)

    async with setup_maker() as verify_session:
        refreshed = await verify_session.get(Product, product_id)
        assert refreshed is not None
        assert refreshed.stock_qty == 0
