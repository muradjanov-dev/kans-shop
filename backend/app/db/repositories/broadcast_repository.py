from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.broadcast import Broadcast
from app.db.models.enums import BroadcastStatus, BroadcastTarget


async def create(
    session: AsyncSession,
    *,
    admin_id: int,
    text: str,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
    target: BroadcastTarget,
) -> Broadcast:
    broadcast = Broadcast(
        admin_id=admin_id,
        text=text,
        photo_file_id=photo_file_id,
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
