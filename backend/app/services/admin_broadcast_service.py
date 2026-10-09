from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AdminRoleRequiredError,
    ForbiddenError,
    KansShopError,
    NotFoundError,
)
from app.db.models.admin import Admin
from app.db.models.broadcast import Broadcast
from app.db.models.broadcast_recipient import BroadcastRecipient
from app.db.models.enums import (
    AdminRole,
    BroadcastRecipientStatus,
    BroadcastStatus,
    BroadcastTarget,
)
from app.db.repositories import broadcast_repository, user_repository
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event

MANAGEMENT_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER})


class BroadcastAudienceChangedError(KansShopError):
    code = "BROADCAST_AUDIENCE_CHANGED"
    http_status = 409


class BroadcastPreviewChangedError(KansShopError):
    code = "BROADCAST_PREVIEW_CHANGED"
    http_status = 409


class BroadcastAlreadyLaunchedError(KansShopError):
    code = "BROADCAST_ALREADY_LAUNCHED"
    http_status = 409


class BroadcastNotFoundError(NotFoundError):
    code = "BROADCAST_NOT_FOUND"


class BroadcastValidationError(KansShopError):
    code = "VALIDATION_ERROR"
    http_status = 422


@dataclass(frozen=True)
class BroadcastPreview:
    target: BroadcastTarget
    text: str
    photo_storage_key: str | None
    photo_file_id: str | None
    button_text: str | None
    button_url: str | None
    preview_content_fingerprint: str
    preview_fingerprint: str
    preview_count: int


def fingerprint_broadcast_preview(
    recipient_ids: list[int] | tuple[int, ...],
    *,
    target: BroadcastTarget,
    text: str,
    photo_storage_key: str | None,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
) -> str:
    """Hash the immutable campaign content and a canonical, sorted audience snapshot."""
    content = _content_payload(
        target=target,
        text=text,
        photo_storage_key=photo_storage_key,
        photo_file_id=photo_file_id,
        button_text=button_text,
        button_url=button_url,
    )
    canonical = json.dumps(
        {"recipient_ids": sorted(recipient_ids), "content": content},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_broadcast_content(
    *,
    target: BroadcastTarget,
    text: str,
    photo_storage_key: str | None,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
) -> str:
    canonical = json.dumps(
        _content_payload(
            target=target,
            text=text,
            photo_storage_key=photo_storage_key,
            photo_file_id=photo_file_id,
            button_text=button_text,
            button_url=button_url,
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _content_payload(
    *,
    target: BroadcastTarget,
    text: str,
    photo_storage_key: str | None,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
) -> dict[str, str | None]:
    return {
        "target": target.value,
        "text": text,
        "photo_storage_key": photo_storage_key,
        "photo_file_id": photo_file_id,
        "button_text": button_text,
        "button_url": button_url,
    }


def _validate_content(
    *,
    text: str,
    photo_storage_key: str | None,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
) -> None:
    if not text.strip() and not (photo_storage_key or photo_file_id):
        raise BroadcastValidationError("Broadcast text must not be blank")
    if len(text) > (1024 if photo_storage_key or photo_file_id else 4096):
        raise BroadcastValidationError("Broadcast text is too long for Telegram")
    if photo_storage_key is not None and photo_file_id is not None:
        raise BroadcastValidationError("Choose one broadcast photo source")
    if (button_text is None) != (button_url is None):
        raise BroadcastValidationError("Button text and URL must be provided together")
    if button_text is not None and not button_text.strip():
        raise BroadcastValidationError("Button text must not be blank")
    if button_url is not None:
        parsed = urlsplit(button_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise BroadcastValidationError("Broadcast button URL must be an HTTPS URL")


async def _load_actor(session: AsyncSession, admin_id: int) -> Admin:
    try:
        return await load_live_admin(
            session,
            admin_id=admin_id,
            allowed_roles=MANAGEMENT_ROLES,
            lock=True,
        )
    except ForbiddenError as exc:
        raise AdminRoleRequiredError("Broadcast management requires manager access") from exc


async def _audience_ids(session: AsyncSession, target: BroadcastTarget) -> list[int]:
    audience = await user_repository.list_for_broadcast(session, target.value)
    return sorted(user.id for user in audience)


async def _preview(
    session: AsyncSession,
    *,
    target: BroadcastTarget,
    text: str,
    photo_storage_key: str | None,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
) -> BroadcastPreview:
    _validate_content(
        text=text,
        photo_storage_key=photo_storage_key,
        photo_file_id=photo_file_id,
        button_text=button_text,
        button_url=button_url,
    )
    if photo_storage_key is not None:
        from app.services.broadcast_media_service import read_broadcast_photo

        try:
            read_broadcast_photo(photo_storage_key)
        except FileNotFoundError:
            raise BroadcastValidationError("Uploaded broadcast photo was not found") from None
    recipient_ids = await _audience_ids(session, target)
    fingerprint = fingerprint_broadcast_preview(
        recipient_ids,
        target=target,
        text=text,
        photo_storage_key=photo_storage_key,
        photo_file_id=photo_file_id,
        button_text=button_text,
        button_url=button_url,
    )
    return BroadcastPreview(
        target=target,
        text=text,
        photo_storage_key=photo_storage_key,
        photo_file_id=photo_file_id,
        button_text=button_text,
        button_url=button_url,
        preview_content_fingerprint=fingerprint_broadcast_content(
            target=target,
            text=text,
            photo_storage_key=photo_storage_key,
            photo_file_id=photo_file_id,
            button_text=button_text,
            button_url=button_url,
        ),
        preview_fingerprint=fingerprint,
        preview_count=len(recipient_ids),
    )


async def _audit(
    session: AsyncSession,
    *,
    admin_id: int,
    action: str,
    broadcast_id: int | None,
    after: dict[str, object],
) -> None:
    await write_audit_event(
        session,
        admin_id=admin_id,
        action=action,
        entity="broadcast",
        entity_id=broadcast_id,
        request_id=uuid4().hex,
        before=None,
        after=after,
    )


async def preview_broadcast(
    session: AsyncSession,
    *,
    admin_id: int,
    target: BroadcastTarget,
    text: str,
    photo_storage_key: str | None,
    photo_file_id: str | None,
    button_text: str | None,
    button_url: str | None,
) -> BroadcastPreview:
    await _load_actor(session, admin_id)
    preview = await _preview(
        session,
        target=target,
        text=text,
        photo_storage_key=photo_storage_key,
        photo_file_id=photo_file_id,
        button_text=button_text,
        button_url=button_url,
    )
    await _audit(
        session,
        admin_id=admin_id,
        action="broadcast.preview",
        broadcast_id=None,
        after={
            "target": target.value,
            "preview_count": preview.preview_count,
            "preview_fingerprint": preview.preview_fingerprint,
        },
    )
    return preview


async def create_broadcast_draft(
    session: AsyncSession, *, admin_id: int, preview: BroadcastPreview
) -> Broadcast:
    await _load_actor(session, admin_id)
    current = await _preview(
        session,
        target=preview.target,
        text=preview.text,
        photo_storage_key=preview.photo_storage_key,
        photo_file_id=preview.photo_file_id,
        button_text=preview.button_text,
        button_url=preview.button_url,
    )
    if current.preview_count != preview.preview_count:
        raise BroadcastAudienceChangedError("Broadcast audience changed since preview")
    if current.preview_content_fingerprint != preview.preview_content_fingerprint:
        raise BroadcastPreviewChangedError("Broadcast content changed since preview")
    if current.preview_fingerprint != preview.preview_fingerprint:
        raise BroadcastAudienceChangedError("Broadcast audience changed since preview")

    broadcast = await broadcast_repository.create(
        session,
        admin_id=admin_id,
        text=preview.text,
        photo_file_id=preview.photo_file_id,
        photo_storage_key=preview.photo_storage_key,
        preview_content_fingerprint=preview.preview_content_fingerprint,
        button_text=preview.button_text,
        button_url=preview.button_url,
        target=preview.target,
    )
    await _audit(
        session,
        admin_id=admin_id,
        action="broadcast.draft_created",
        broadcast_id=broadcast.id,
        after={"target": preview.target.value, "status": BroadcastStatus.DRAFT.value},
    )
    return broadcast


def _launch_lock_idempotency_key(key: UUID) -> int:
    return int.from_bytes(hashlib.sha256(key.bytes).digest()[:8], "big", signed=True)


async def launch_broadcast(
    session: AsyncSession,
    *,
    admin_id: int,
    broadcast_id: int,
    preview_fingerprint: str,
    preview_count: int,
    idempotency_key: UUID,
) -> Broadcast:
    if preview_count < 0 or len(preview_fingerprint) != 64:
        raise BroadcastValidationError("Invalid broadcast preview")
    await session.scalar(
        select(func.pg_advisory_xact_lock(_launch_lock_idempotency_key(idempotency_key)))
    )

    existing_key = await session.scalar(
        select(Broadcast).where(Broadcast.launch_idempotency_key == idempotency_key)
    )
    if existing_key is not None:
        if existing_key.id == broadcast_id:
            return existing_key
        raise BroadcastAlreadyLaunchedError("Launch idempotency key was already used")

    broadcast = await broadcast_repository.get_for_update(session, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"Broadcast {broadcast_id} not found")
    if broadcast.launch_idempotency_key is not None:
        raise BroadcastAlreadyLaunchedError("Broadcast has already been launched")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise BroadcastAlreadyLaunchedError("Broadcast is no longer a draft")
    actor = await _load_actor(session, admin_id)

    recipient_ids = await _audience_ids(session, broadcast.target)
    current_content_fingerprint = fingerprint_broadcast_content(
        target=broadcast.target,
        text=broadcast.text,
        photo_storage_key=broadcast.photo_storage_key,
        photo_file_id=broadcast.photo_file_id,
        button_text=broadcast.button_text,
        button_url=broadcast.button_url,
    )
    if (
        broadcast.preview_content_fingerprint is None
        or current_content_fingerprint != broadcast.preview_content_fingerprint
    ):
        raise BroadcastPreviewChangedError("Broadcast content changed since preview")
    if len(recipient_ids) != preview_count:
        raise BroadcastAudienceChangedError("Broadcast audience changed since preview")
    current_fingerprint = fingerprint_broadcast_preview(
        recipient_ids,
        target=broadcast.target,
        text=broadcast.text,
        photo_storage_key=broadcast.photo_storage_key,
        photo_file_id=broadcast.photo_file_id,
        button_text=broadcast.button_text,
        button_url=broadcast.button_url,
    )
    if current_fingerprint != preview_fingerprint:
        raise BroadcastAudienceChangedError("Broadcast audience changed since preview")

    existing_recipients = await session.scalar(
        select(func.count())
        .select_from(BroadcastRecipient)
        .where(BroadcastRecipient.broadcast_id == broadcast_id)
    )
    if existing_recipients:
        raise BroadcastAlreadyLaunchedError("Broadcast already has recipient checkpoints")

    now = datetime.now(UTC)
    session.add_all(
        BroadcastRecipient(broadcast_id=broadcast_id, user_id=user_id)
        for user_id in recipient_ids
    )
    broadcast.admin_id = actor.id
    broadcast.status = BroadcastStatus.SENDING if recipient_ids else BroadcastStatus.COMPLETED
    broadcast.launch_idempotency_key = idempotency_key
    broadcast.launch_fingerprint = current_fingerprint
    broadcast.launch_count = len(recipient_ids)
    broadcast.launcher_auth_epoch = actor.auth_epoch
    broadcast.launched_at = now
    await session.flush()
    await _audit(
        session,
        admin_id=admin_id,
        action="broadcast.launched",
        broadcast_id=broadcast.id,
        after={
            "target": broadcast.target.value,
            "status": broadcast.status.value,
            "launch_count": len(recipient_ids),
            "launch_fingerprint": current_fingerprint,
        },
    )
    return broadcast


async def cancel_broadcast(
    session: AsyncSession, *, admin_id: int, broadcast_id: int
) -> Broadcast:
    broadcast = await broadcast_repository.get_for_update(session, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"Broadcast {broadcast_id} not found")
    await _load_actor(session, admin_id)
    if broadcast.status in {BroadcastStatus.DRAFT, BroadcastStatus.SENDING}:
        await session.execute(
            update(BroadcastRecipient)
            .where(
                BroadcastRecipient.broadcast_id == broadcast_id,
                BroadcastRecipient.status == BroadcastRecipientStatus.PENDING,
            )
            .values(
                status=BroadcastRecipientStatus.CANCELLED,
                last_error="cancelled_by_admin",
            )
        )
        broadcast.status = BroadcastStatus.CANCELLED
        await session.flush()
        await _audit(
            session,
            admin_id=admin_id,
            action="broadcast.cancelled",
            broadcast_id=broadcast_id,
            after={"status": BroadcastStatus.CANCELLED.value},
        )
    return broadcast


async def broadcast_recipient_counts(
    session: AsyncSession, broadcast_id: int
) -> dict[BroadcastRecipientStatus, int]:
    rows = (
        await session.execute(
            select(BroadcastRecipient.status, func.count())
            .where(BroadcastRecipient.broadcast_id == broadcast_id)
            .group_by(BroadcastRecipient.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    for status in BroadcastRecipientStatus:
        counts.setdefault(status, 0)
    return counts


async def get_broadcast(session: AsyncSession, *, broadcast_id: int) -> Broadcast:
    broadcast = await broadcast_repository.get_by_id(session, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"Broadcast {broadcast_id} not found")
    return broadcast
