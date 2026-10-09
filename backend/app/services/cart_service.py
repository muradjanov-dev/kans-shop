from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    MinimumOrderQuantityError,
    OutOfStockError,
    ProductNotFoundError,
)
from app.db.models.cart import Cart, CartItem
from app.db.models.product import Product
from app.db.repositories import cart_repository, product_repository
from app.services.purchase_locks import lock_customer_cart


async def get_cart(session: AsyncSession, user_id: int) -> Cart:
    cart = await cart_repository.get_active_cart(session, user_id)
    if cart is not None:
        return cart
    return await lock_customer_cart(session, user_id)


def calculate_subtotal(cart: Cart) -> Decimal:
    return sum((item.product.price * item.quantity for item in cart.items), Decimal("0"))


def calculate_items_count(cart: Cart) -> int:
    return sum(item.quantity for item in cart.items)


async def _get_active_product(
    session: AsyncSession, product_id: int, *, for_update: bool = False
) -> Product:
    product = await product_repository.get_by_id(session, product_id, for_update=for_update)
    if product is None or not product.is_active:
        raise ProductNotFoundError(f"Product {product_id} not found")
    if await product_repository.get_public_by_id(session, product_id) is None:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return product


async def add_item(
    session: AsyncSession, user_id: int, product_id: int, quantity: int = 1
) -> CartItem:
    cart = await lock_customer_cart(session, user_id)
    return await add_item_to_locked_cart(session, cart, product_id, quantity)


async def add_item_to_locked_cart(
    session: AsyncSession, cart: Cart, product_id: int, quantity: int
) -> CartItem:
    """Apply an add delta after the caller has taken the customer/cart locks."""
    product = await _get_active_product(session, product_id, for_update=True)
    existing = await cart_repository.get_item(session, cart.id, product_id)

    new_quantity = (
        existing.quantity + quantity if existing else max(quantity, product.min_order_qty)
    )
    if new_quantity > product.stock_qty:
        raise OutOfStockError(
            f"Only {product.stock_qty} left for {product.sku}",
            details={"product_id": product.id, "available": product.stock_qty},
        )

    if existing:
        await cart_repository.update_item_quantity(session, existing, new_quantity)
        await cart_repository.update_item_price_snapshot(session, existing, product.price)
        return existing
    return await cart_repository.add_item(session, cart, product, new_quantity)


async def update_item_quantity(
    session: AsyncSession, user_id: int, product_id: int, quantity: int
) -> CartItem | None:
    cart = await lock_customer_cart(session, user_id)
    item = await cart_repository.get_item(session, cart.id, product_id)
    if item is None:
        return None

    if quantity <= 0:
        await cart_repository.remove_item(session, item)
        return None

    product = await _get_active_product(session, product_id, for_update=True)
    if quantity < product.min_order_qty:
        raise MinimumOrderQuantityError(
            f"Minimum order quantity for {product.sku} is {product.min_order_qty}",
            details={"product_id": product.id, "minimum": product.min_order_qty},
        )
    if quantity > product.stock_qty:
        raise OutOfStockError(
            f"Only {product.stock_qty} left for {product.sku}",
            details={"product_id": product.id, "available": product.stock_qty},
        )

    await cart_repository.update_item_quantity(session, item, quantity)
    return item


async def remove_item(session: AsyncSession, user_id: int, product_id: int) -> None:
    cart = await lock_customer_cart(session, user_id)
    item = await cart_repository.get_item(session, cart.id, product_id)
    if item is not None:
        await cart_repository.remove_item(session, item)


async def clear_cart(session: AsyncSession, user_id: int) -> None:
    cart = await lock_customer_cart(session, user_id)
    await cart_repository.clear(session, cart)
