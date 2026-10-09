from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cart import Cart
from app.db.repositories import cart_repository, user_repository


async def lock_customer_cart(session: AsyncSession, user_id: int) -> Cart:
    """Lock a customer's user row and active cart, creating the cart if needed.

    Every cart mutation and checkout takes these locks in the same order before it locks
    products. The user lock also serializes creation of the first cart for that customer.
    The cart query refreshes any previously loaded ORM state after waiting for a lock.
    """
    user = await user_repository.get_by_id(session, user_id, for_update=True)
    if user is None:
        raise ValueError(f"Customer {user_id} does not exist")

    cart = await cart_repository.get_active_cart(session, user_id, for_update=True)
    if cart is None:
        cart = Cart(user_id=user_id, items=[])
        session.add(cart)
        await session.flush()
    return cart
