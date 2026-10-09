from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cart_mutation import CartMutation


async def get_by_user_and_key(
    session: AsyncSession, user_id: int, mutation_key: UUID
) -> CartMutation | None:
    statement = select(CartMutation).where(
        CartMutation.user_id == user_id,
        CartMutation.mutation_key == str(mutation_key),
    )
    return await session.scalar(statement)


async def create(
    session: AsyncSession,
    *,
    user_id: int,
    mutation_key: UUID,
    request_fingerprint: str,
) -> CartMutation:
    mutation = CartMutation(
        user_id=user_id,
        mutation_key=str(mutation_key),
        request_fingerprint=request_fingerprint,
    )
    session.add(mutation)
    await session.flush()
    return mutation
