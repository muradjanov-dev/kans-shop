from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OutOfStockError, ProductNotFoundError
from app.db.models.cart import Cart, CartItem
from app.db.models.product import Product
from app.db.repositories import cart_repository, product_repository


async def get_cart(session: AsyncSession, user_id: int) -> Cart:
    return await cart_repository.get_or_create_active_cart(session, user_id)


def calculate_subtotal(cart: Cart) -> Decimal:
    return sum((item.product.price * item.quantity for item in cart.items), Decimal("0"))


def calculate_items_count(cart: Cart) -> int:
    return sum(item.quantity for item in cart.items)


async def _get_active_product(session: AsyncSession, product_id: int) -> Product:
    product = await product_repository.get_by_id(session, product_id)
    if product is None or not product.is_active:
        raise ProductNotFoundError(f"Product {product_id} not found")
    return product


async def add_item(
    session: AsyncSession, user_id: int, product_id: int, quantity: int = 1
) -> CartItem:
    product = await _get_active_product(session, product_id)
    cart = await cart_repository.get_or_create_active_cart(session, user_id)
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
    cart = await cart_repository.get_or_create_active_cart(session, user_id)
    item = await cart_repository.get_item(session, cart.id, product_id)
    if item is None:
        return None

    if quantity <= 0:
        await cart_repository.remove_item(session, item)
        return None

    product = await _get_active_product(session, product_id)
    if quantity > product.stock_qty:
        raise OutOfStockError(
            f"Only {product.stock_qty} left for {product.sku}",
            details={"product_id": product.id, "available": product.stock_qty},
        )

    await cart_repository.update_item_quantity(session, item, quantity)
    return item


async def remove_item(session: AsyncSession, user_id: int, product_id: int) -> None:
    cart = await cart_repository.get_or_create_active_cart(session, user_id)
    item = await cart_repository.get_item(session, cart.id, product_id)
    if item is not None:
        await cart_repository.remove_item(session, item)


async def clear_cart(session: AsyncSession, user_id: int) -> None:
    cart = await cart_repository.get_or_create_active_cart(session, user_id)
    await cart_repository.clear(session, cart)
