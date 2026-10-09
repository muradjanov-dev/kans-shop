from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.broadcast import Broadcast
from app.db.models.enums import BroadcastStatus, BroadcastTarget


async def get_by_id(session: AsyncSession, broadcast_id: int) -> Broadcast | None:
    return await session.get(Broadcast, broadcast_id)


async def get_for_update(session: AsyncSession, broadcast_id: int) -> Broadcast | None:
    return await session.scalar(
        select(Broadcast)
        .where(Broadcast.id == broadcast_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def create(
    session: AsyncSession,
    *,
    admin_id: int,
    text: str,
    photo_file_id: str | None,
    photo_storage_key: str | None = None,
    preview_content_fingerprint: str | None = None,
    button_text: str | None,
    button_url: str | None,
    target: BroadcastTarget,
) -> Broadcast:
    broadcast = Broadcast(
        admin_id=admin_id,
        text=text,
        photo_file_id=photo_file_id,
        photo_storage_key=photo_storage_key,
        preview_content_fingerprint=preview_content_fingerprint,
        button_text=button_text,
        button_url=button_url,
        target=target,
        status=BroadcastStatus.DRAFT,
    )
    session.add(broadcast)
    await session.flush()
    return broadcast


async def mark_sending(session: AsyncSession, broadcast: Broadcast) -> None:
    broadcast.status = BroadcastStatus.SENDING
    await session.flush()


async def finish(
    session: AsyncSession,
    broadcast: Broadcast,
    *,
    sent: int,
    failed: int,
    status: BroadcastStatus,
) -> None:
    broadcast.sent_count = sent
    broadcast.failed_count = failed
    broadcast.status = status
    await session.flush()
