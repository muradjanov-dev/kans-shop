"""Transactional producers for system-wide notifications."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import Admin
from app.services.notification_outbox_service import enqueue_outbox_event


async def notify_admins_deploy(session: AsyncSession) -> None:
    """Queue a deploy notice for active notification-enabled admins."""
    deployment_id = uuid4().hex
    recipient_ids = await session.scalars(
        select(Admin.id)
        .where(Admin.is_active.is_(True), Admin.notifications_enabled.is_(True))
        .order_by(Admin.id)
    )
    for admin_id in recipient_ids:
        await enqueue_outbox_event(
            session,
            event_type="system.deploy",
            aggregate_id=0,
            recipient_admin_id=admin_id,
            dedupe_key=f"system-deploy:{deployment_id}:admin:{admin_id}",
        )
