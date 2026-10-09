import hashlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IdempotencyConflictError
from app.db.models.cart import Cart
from app.db.repositories import cart_mutation_repository, cart_repository
from app.services import cart_service
from app.services.purchase_locks import lock_customer_cart


def _request_fingerprint(product_id: int, quantity: int) -> str:
    normalized_request = f"product_id={int(product_id)}&quantity={int(quantity)}"
    return hashlib.sha256(normalized_request.encode("utf-8")).hexdigest()


async def add_item_once(
    session: AsyncSession,
    *,
    user_id: int,
    product_id: int,
    quantity: int,
    mutation_key: UUID | None,
) -> Cart:
    """Apply an add delta once per user/key and return the customer's current cart."""
    if mutation_key is None:
        await cart_service.add_item(session, user_id, product_id, quantity)
        cart = await cart_repository.get_active_cart(session, user_id)
        assert cart is not None
        return cart

    cart = await lock_customer_cart(session, user_id)
    fingerprint = _request_fingerprint(product_id, quantity)
    existing = await cart_mutation_repository.get_by_user_and_key(
        session, user_id, mutation_key
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise IdempotencyConflictError(
                "This Idempotency-Key was already used with a different cart add request"
            )
        return cart

    await cart_service.add_item_to_locked_cart(session, cart, product_id, quantity)
    await cart_mutation_repository.create(
        session,
        user_id=user_id,
        mutation_key=mutation_key,
        request_fingerprint=fingerprint,
    )

    current_cart = await cart_repository.get_active_cart(session, user_id)
    assert current_cart is not None
    return current_cart
