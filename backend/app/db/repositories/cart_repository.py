from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.cart import Cart, CartItem
from app.db.models.product import Product


async def get_active_cart(session: AsyncSession, user_id: int) -> Cart | None:
    stmt = (
        select(Cart)
        .where(Cart.user_id == user_id, Cart.is_active.is_(True))
        .options(selectinload(Cart.items).selectinload(CartItem.product))
        # Without this, a Cart already in the identity map keeps its stale in-memory `items`
        # collection even after a sibling CartItem was deleted+flushed through a separate
        # query (e.g. remove_item/clear) — force this call to always reflect current DB state.
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def get_or_create_active_cart(session: AsyncSession, user_id: int) -> Cart:
    cart = await get_active_cart(session, user_id)
    if cart is not None:
        return cart
    cart = Cart(user_id=user_id)
    session.add(cart)
    await session.flush()
    return cart


async def get_item(session: AsyncSession, cart_id: int, product_id: int) -> CartItem | None:
    stmt = select(CartItem).where(
        CartItem.cart_id == cart_id, CartItem.product_id == product_id
    )
    return await session.scalar(stmt)


async def add_item(
    session: AsyncSession, cart: Cart, product: Product, quantity: int
) -> CartItem:
    item = CartItem(
        cart_id=cart.id,
        product_id=product.id,
        quantity=quantity,
        price_snapshot=product.price,
    )
    session.add(item)
    await session.flush()
    return item


async def update_item_quantity(session: AsyncSession, item: CartItem, quantity: int) -> None:
    item.quantity = quantity
    await session.flush()


async def update_item_price_snapshot(
    session: AsyncSession, item: CartItem, price: Decimal
) -> None:
    item.price_snapshot = price
    await session.flush()


async def remove_item(session: AsyncSession, item: CartItem) -> None:
    await session.delete(item)
    await session.flush()


async def clear(session: AsyncSession, cart: Cart) -> None:
    for item in list(cart.items):
        await session.delete(item)
    await session.flush()
