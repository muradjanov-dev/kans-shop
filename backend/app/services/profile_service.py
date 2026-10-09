from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


async def update_profile(session: AsyncSession, user: User, patch: Mapping[str, Any]) -> User:
    for field in ("display_name", "phone", "language"):
        if field in patch:
            setattr(user, field, patch[field])
    await session.flush()
    return user
