from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OutOfStockError, ProductNotFoundError
from app.db.models.product import Product
from app.db.models.user import User
from app.services import cart_service


async def test_add_item_creates_cart_and_item(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    item = await cart_service.add_item(db_session, user.id, product.id, quantity=2)

    assert item.quantity == 2
    assert item.price_snapshot == product.price


async def test_add_item_twice_accumulates_quantity(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=2)
    item = await cart_service.add_item(db_session, user.id, product.id, quantity=3)

    assert item.quantity == 5


async def test_add_item_beyond_stock_raises(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    with pytest.raises(OutOfStockError):
        await cart_service.add_item(
            db_session, user.id, product.id, quantity=product.stock_qty + 1
        )


async def test_add_item_unknown_product_raises(db_session: AsyncSession, user: User) -> None:
    with pytest.raises(ProductNotFoundError):
        await cart_service.add_item(db_session, user.id, 999_999, quantity=1)


async def test_update_item_quantity_to_zero_removes_item(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=2)

    result = await cart_service.update_item_quantity(db_session, user.id, product.id, 0)

    assert result is None
    cart = await cart_service.get_cart(db_session, user.id)
    assert cart.items == []


async def test_update_item_quantity_beyond_stock_raises(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=2)

    with pytest.raises(OutOfStockError):
        await cart_service.update_item_quantity(
            db_session, user.id, product.id, product.stock_qty + 1
        )


async def test_remove_item(db_session: AsyncSession, user: User, product: Product) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)

    await cart_service.remove_item(db_session, user.id, product.id)

    cart = await cart_service.get_cart(db_session, user.id)
    assert cart.items == []


async def test_clear_cart_removes_all_items(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)

    await cart_service.clear_cart(db_session, user.id)

    cart = await cart_service.get_cart(db_session, user.id)
    assert cart.items == []


async def test_calculate_subtotal_uses_live_price_times_quantity(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=3)
    cart = await cart_service.get_cart(db_session, user.id)

    subtotal = cart_service.calculate_subtotal(cart)

    assert subtotal == Decimal("5000") * 3


async def test_calculate_items_count(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=4)
    cart = await cart_service.get_cart(db_session, user.id)

    assert cart_service.calculate_items_count(cart) == 4
