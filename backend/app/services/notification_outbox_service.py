from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification_outbox import NotificationOutbox


async def enqueue_outbox_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: int,
    dedupe_key: str,
    recipient_user_id: int | None = None,
    recipient_admin_id: int | None = None,
    payload_id: int | None = None,
) -> NotificationOutbox:
    if (recipient_user_id is None) == (recipient_admin_id is None):
        raise ValueError("Exactly one outbox recipient is required")
    if not dedupe_key or len(dedupe_key) > 160:
        raise ValueError("dedupe_key must contain 1 to 160 characters")

    statement = (
        insert(NotificationOutbox)
        .values(
            recipient_user_id=recipient_user_id,
            recipient_admin_id=recipient_admin_id,
            event_type=event_type,
            aggregate_id=str(aggregate_id),
            payload_id=str(payload_id) if payload_id is not None else None,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(index_elements=[NotificationOutbox.dedupe_key])
        .returning(NotificationOutbox.id)
    )
    outbox_id = await session.scalar(statement)
    if outbox_id is None:
        event = await session.scalar(
            select(NotificationOutbox).where(NotificationOutbox.dedupe_key == dedupe_key)
        )
        if event is None:
            raise RuntimeError("Deduplicated notification disappeared before it could be read")
        return event

    event = await session.get(NotificationOutbox, outbox_id)
    if event is None:
        raise RuntimeError("Inserted notification could not be reloaded")
    return event
