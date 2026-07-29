from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.setting import Setting


async def get(session: AsyncSession, key: str) -> Setting | None:
    return await session.scalar(select(Setting).where(Setting.key == key))


async def get_value(session: AsyncSession, key: str, default: Any = None) -> Any:
    setting = await get(session, key)
    return setting.value if setting is not None else default


async def get_all(session: AsyncSession) -> dict[str, Any]:
    settings = (await session.scalars(select(Setting))).all()
    return {s.key: s.value for s in settings}


async def set_value(session: AsyncSession, key: str, value: Any) -> Setting:
    setting = await get(session, key)
    if setting is None:
        setting = Setting(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value
    await session.flush()
    return setting
