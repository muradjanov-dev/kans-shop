import asyncio
from decimal import Decimal
from secrets import randbelow, token_hex

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.models.category import Category
from app.db.models.enums import OrderType, ProductUnit
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.setting import Setting
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.services import cart_service, order_service


async def test_cart_mutations_serialize_with_checkout(test_engine: AsyncEngine) -> None:
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = token_hex(6)
    checkout_setting_keys = (
        "is_shop_open",
        "min_order_amount",
        "delivery_fee",
        "free_delivery_from",
    )
    async with session_maker() as setup_session:
        existing_settings = await setting_repository.get_all(setup_session)
        previous_settings = {
            key: (key in existing_settings, existing_settings.get(key))
            for key in checkout_setting_keys
        }
        category = Category(
            name_uz="Checkout lock", name_ru="Checkout lock", slug=f"checkout-lock-{suffix}"
        )
        user = User(
            telegram_id=8_100_000_000_000_000 + randbelow(100_000_000),
            first_name="Checkout lock test",
        )
        setup_session.add_all([category, user])
        await setup_session.flush()
        product = Product(
            category_id=category.id,
            name_uz="Test pen",
            name_ru="Test pen",
            sku=f"CHECKOUT-LOCK-{suffix}",
            price=Decimal("1000"),
            stock_qty=10,
            unit=ProductUnit.DONA,
        )
        setup_session.add(product)
        await setup_session.flush()
        for key, value in {
            "is_shop_open": True,
            "min_order_amount": 0,
            "delivery_fee": 0,
            "free_delivery_from": 0,
        }.items():
            await setting_repository.set_value(setup_session, key, value)
        await cart_service.add_item(setup_session, user.id, product.id, quantity=1)
        await setup_session.commit()
        user_id, product_id, category_id = user.id, product.id, category.id

    add_started = asyncio.Event()

    async def add_after_checkout() -> None:
        async with session_maker() as session, session.begin():
            add_started.set()
            await cart_service.add_item(session, user_id, product_id, quantity=1)

    checkout_order_id: int | None = None
    add_task: asyncio.Task | None = None
    blocked_before_checkout_commit = False
    try:
        async with session_maker() as checkout_session:
            transaction = await checkout_session.begin()
            order = await order_service.checkout(
                checkout_session,
                user_id=user_id,
                order_type=OrderType.PICKUP,
                customer_name="Checkout lock test",
                customer_phone="+998901234567",
            )
            checkout_order_id = order.id
            add_task = asyncio.create_task(add_after_checkout())
            await add_started.wait()

            # The add must wait on the customer/cart lock held by checkout until its
            # transaction commits, then observe and mutate the post-checkout cart.
            await asyncio.sleep(0.1)
            blocked_before_checkout_commit = not add_task.done()
            await transaction.commit()
            await asyncio.wait_for(add_task, timeout=3)

        async with session_maker() as verify_session:
            cart = await cart_service.get_cart(verify_session, user_id)
            assert len(cart.items) == 1
            assert cart.items[0].product_id == product_id
            assert cart.items[0].quantity == 1
        assert blocked_before_checkout_commit
    finally:
        async with session_maker() as cleanup_session:
            if checkout_order_id is not None:
                order = await cleanup_session.get(Order, checkout_order_id)
                if order is not None:
                    await cleanup_session.delete(order)
            for order in (
                await cleanup_session.scalars(select(Order).where(Order.user_id == user_id))
            ).all():
                await cleanup_session.delete(order)
            user = await cleanup_session.get(User, user_id)
            if user is not None:
                await cleanup_session.delete(user)
            product = await cleanup_session.get(Product, product_id)
            if product is not None:
                await cleanup_session.delete(product)
            category = await cleanup_session.get(Category, category_id)
            if category is not None:
                await cleanup_session.delete(category)
            for key, (existed, value) in previous_settings.items():
                if existed:
                    await setting_repository.set_value(cleanup_session, key, value)
                else:
                    await cleanup_session.execute(delete(Setting).where(Setting.key == key))
            await cleanup_session.commit()
