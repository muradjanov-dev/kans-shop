"""Shared, live-authorized administration of staff accounts and browser sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import AdminChanges
from app.core.exceptions import (
    AdminAlreadyExistsError,
    AdminRoleRequiredError,
    ForbiddenError,
    LastSuperadminRequiredError,
    NotFoundError,
)
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole
from app.db.repositories import admin_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event
from app.services.common import Page
from app.services.notification_outbox_service import enqueue_outbox_event

# One database-wide key serializes every change that can affect the last-active-
# superadmin invariant. Keep it stable across processes and deployments.
TEAM_ADVISORY_LOCK_ID = 0x4B414E535445414D
SUPERADMIN_ONLY = frozenset({AdminRole.SUPERADMIN})


async def _acquire_team_lock(session: AsyncSession) -> None:
    await session.scalar(select(func.pg_advisory_xact_lock(TEAM_ADVISORY_LOCK_ID)))


async def _load_actor(session: AsyncSession, actor_admin_id: int) -> Admin:
    try:
        return await load_live_admin(
            session,
            admin_id=actor_admin_id,
            allowed_roles=SUPERADMIN_ONLY,
            lock=True,
        )
    except ForbiddenError as exc:
        raise AdminRoleRequiredError("A superadmin role is required") from exc


async def _load_target(session: AsyncSession, admin_id: int) -> Admin:
    admin = await admin_repository.get_by_id(session, admin_id, for_update=True)
    if admin is None:
        raise NotFoundError(f"Admin {admin_id} not found")
    return admin


async def _active_superadmin_count(session: AsyncSession) -> int:
    return await admin_repository.count_active_superadmins(session)


def _snapshot(admin: Admin) -> dict[str, object]:
    return {
        "id": admin.id,
        "telegram_id": admin.telegram_id,
        "full_name": admin.full_name,
        "role": admin.role,
        "is_active": admin.is_active,
        "notifications_enabled": admin.notifications_enabled,
    }


async def _revoke_sessions_and_advance_epoch(
    session: AsyncSession, admin: Admin, *, now: datetime
) -> int:
    admin.auth_epoch += 1
    result = await session.execute(
        update(AdminSession)
        .where(AdminSession.admin_id == admin.id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(AdminSession.id)
        .execution_options(synchronize_session=False)
    )
    await session.flush()
    return len(result.scalars().all())


async def _notify_current_admins(
    session: AsyncSession, *, actor_admin_id: int, audit_event: AdminAuditEvent
) -> None:
    """Queue one durable event per current, notifiable admin; never send in this transaction."""
    recipients = await session.scalars(
        select(Admin.id)
        .where(
            Admin.id != actor_admin_id,
            Admin.is_active.is_(True),
            Admin.notifications_enabled.is_(True),
        )
        .order_by(Admin.id)
    )
    aggregate_id = audit_event.resource_id or "0"
    for recipient_admin_id in recipients:
        await enqueue_outbox_event(
            session,
            event_type="admin.team.changed",
            aggregate_id=int(aggregate_id),
            payload_id=audit_event.id,
            recipient_admin_id=recipient_admin_id,
            dedupe_key=f"admin-team:{audit_event.id}:admin:{recipient_admin_id}",
        )


async def _audit_and_notify(
    session: AsyncSession,
    *,
    actor_admin_id: int,
    action: str,
    admin_id: int,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> AdminAuditEvent:
    audit_event = await _write_audit_event(
        session,
        actor_admin_id=actor_admin_id,
        action=action,
        admin_id=admin_id,
        before=before,
        after=after,
    )
    await _notify_current_admins(
        session, actor_admin_id=actor_admin_id, audit_event=audit_event
    )
    return audit_event


async def _write_audit_event(
    session: AsyncSession,
    *,
    actor_admin_id: int,
    action: str,
    admin_id: int,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> AdminAuditEvent:
    return await write_audit_event(
        session,
        admin_id=actor_admin_id,
        action=action,
        entity="team",
        entity_id=admin_id,
        request_id=uuid4().hex,
        before=before,
        after=after,
    )


async def list_admins(
    session: AsyncSession,
    *,
    admin_id: int,
    page: int = 1,
    limit: int = 20,
) -> Page[Admin]:
    await load_live_admin(session, admin_id=admin_id, allowed_roles=SUPERADMIN_ONLY)
    if page < 1 or not 1 <= limit <= 100:
        raise ValueError("page must be positive and limit must be between 1 and 100")
    total = await session.scalar(select(func.count()).select_from(Admin))
    items = list(
        (
            await session.scalars(
                select(Admin)
                .order_by(Admin.created_at.asc(), Admin.id.asc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
    )
    return Page(items=items, total=total or 0, page=page, limit=limit)


async def add_admin(
    session: AsyncSession,
    *,
    actor_admin_id: int,
    telegram_id: int,
    full_name: str,
    role: AdminRole,
) -> Admin:
    await _acquire_team_lock(session)
    actor = await _load_actor(session, actor_admin_id)
    await _active_superadmin_count(session)

    normalized_name = full_name.strip()
    if telegram_id <= 0:
        raise ValueError("telegram_id must be positive")
    if not normalized_name or len(normalized_name) > 128:
        raise ValueError("full_name must contain 1 to 128 characters")

    if await admin_repository.get_by_telegram_id(session, telegram_id) is not None:
        raise AdminAlreadyExistsError("This Telegram account is already an admin")
    admin = await admin_repository.create(
        session,
        telegram_id=telegram_id,
        full_name=normalized_name,
        role=role,
    )
    await _audit_and_notify(
        session,
        actor_admin_id=actor.id,
        action="admin.team.add",
        admin_id=admin.id,
        before=None,
        after=_snapshot(admin),
    )
    return admin


async def update_admin(
    session: AsyncSession,
    *,
    actor_admin_id: int,
    admin_id: int,
    changes: AdminChanges,
) -> Admin:
    await _acquire_team_lock(session)
    actor = await _load_actor(session, actor_admin_id)
    target = await _load_target(session, admin_id)
    active_superadmins = await _active_superadmin_count(session)
    before = _snapshot(target)
    proposed_after = _snapshot(target)

    if changes.full_name is not None:
        proposed_after["full_name"] = changes.full_name
    if changes.role is not None:
        proposed_after["role"] = changes.role
    if changes.is_active is not None:
        proposed_after["is_active"] = changes.is_active
    if changes.notifications_enabled is not None:
        proposed_after["notifications_enabled"] = changes.notifications_enabled

    desired_role = changes.role if changes.role is not None else target.role
    desired_active = changes.is_active if changes.is_active is not None else target.is_active
    loses_superadmin = (
        target.role == AdminRole.SUPERADMIN
        and target.is_active
        and (desired_role != AdminRole.SUPERADMIN or not desired_active)
    )
    if loses_superadmin and active_superadmins <= 1:
        raise LastSuperadminRequiredError("At least one active superadmin must remain")

    changed_fields = {
        key for key, value in before.items() if key != "id" and value != proposed_after[key]
    }
    if not changed_fields:
        return target

    audit_event = None
    if target.id == actor.id and target.is_active and proposed_after["is_active"] is False:
        # The shared audit helper must validate a live actor. For self-deactivation, record
        # the before/proposed-after snapshots before making the actor inactive; all writes
        # still commit or roll back together in the caller's transaction.
        audit_event = await _write_audit_event(
            session,
            actor_admin_id=actor.id,
            action="admin.team.update",
            admin_id=target.id,
            before=before,
            after=proposed_after,
        )

    if changes.full_name is not None:
        target.full_name = changes.full_name
    if changes.role is not None:
        target.role = changes.role
    if changes.is_active is not None:
        target.is_active = changes.is_active
    if changes.notifications_enabled is not None:
        target.notifications_enabled = changes.notifications_enabled

    if {"role", "is_active"} & changed_fields:
        await _revoke_sessions_and_advance_epoch(session, target, now=datetime.now(UTC))
    else:
        await session.flush()

    if audit_event is None:
        await _audit_and_notify(
            session,
            actor_admin_id=actor.id,
            action="admin.team.update",
            admin_id=target.id,
            before=before,
            after=_snapshot(target),
        )
    else:
        await _notify_current_admins(session, actor_admin_id=actor.id, audit_event=audit_event)
    return target


async def remove_admin(session: AsyncSession, *, actor_admin_id: int, admin_id: int) -> None:
    await _acquire_team_lock(session)
    actor = await _load_actor(session, actor_admin_id)
    if admin_id == actor.id:
        raise ForbiddenError("An admin cannot remove their own account")

    target = await _load_target(session, admin_id)
    active_superadmins = await _active_superadmin_count(session)
    if target.role == AdminRole.SUPERADMIN and target.is_active and active_superadmins <= 1:
        raise LastSuperadminRequiredError("At least one active superadmin must remain")

    before = _snapshot(target)
    await _revoke_sessions_and_advance_epoch(session, target, now=datetime.now(UTC))
    await session.delete(target)
    await session.flush()
    await _audit_and_notify(
        session,
        actor_admin_id=actor.id,
        action="admin.team.remove",
        admin_id=admin_id,
        before=before,
        after={"removed": True, "auth_epoch": target.auth_epoch},
    )


async def revoke_admin_sessions(
    session: AsyncSession, *, actor_admin_id: int, admin_id: int
) -> int:
    await _acquire_team_lock(session)
    actor = await _load_actor(session, actor_admin_id)
    target = await _load_target(session, admin_id)
    before: dict[str, object] = {"auth_epoch": target.auth_epoch}
    revoked_count = await _revoke_sessions_and_advance_epoch(
        session, target, now=datetime.now(UTC)
    )
    after: dict[str, object] = {
        "auth_epoch": target.auth_epoch,
        "revoked_sessions": revoked_count,
    }
    await _audit_and_notify(
        session,
        actor_admin_id=actor.id,
        action="admin.sessions.revoke",
        admin_id=target.id,
        before=before,
        after=after,
    )
    return revoked_count
