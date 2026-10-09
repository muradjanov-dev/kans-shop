from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    MANAGEMENT_ROLES,
    get_current_admin,
    get_db,
    require_admin_roles,
)
from app.api.schemas.admin import (
    BroadcastDraftIn,
    BroadcastLaunchIn,
    BroadcastOut,
    BroadcastPhotoOut,
    BroadcastPreviewIn,
    BroadcastPreviewOut,
)
from app.core.exceptions import BroadcastMediaTooLargeError, UnsupportedMediaTypeError
from app.db.models.admin import Admin
from app.db.models.broadcast import Broadcast
from app.db.models.enums import BroadcastRecipientStatus
from app.services import admin_broadcast_service, broadcast_media_service

router = APIRouter(
    prefix="/admin/broadcasts",
    tags=["admin-broadcasts"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


async def _response(session: AsyncSession, broadcast: Broadcast) -> BroadcastOut:
    counts = await admin_broadcast_service.broadcast_recipient_counts(session, broadcast.id)
    return BroadcastOut(
        id=broadcast.id,
        text=broadcast.text,
        photo_file_id=broadcast.photo_file_id,
        photo_storage_key=broadcast.photo_storage_key,
        button_text=broadcast.button_text,
        button_url=broadcast.button_url,
        target=broadcast.target,
        status=broadcast.status,
        sent_count=broadcast.sent_count,
        failed_count=broadcast.failed_count,
        pending_count=counts[BroadcastRecipientStatus.PENDING],
        sending_count=counts[BroadcastRecipientStatus.SENDING],
        cancelled_count=counts[BroadcastRecipientStatus.CANCELLED],
        created_at=broadcast.created_at,
        launched_at=broadcast.launched_at,
    )


def _as_preview(payload: BroadcastDraftIn) -> admin_broadcast_service.BroadcastPreview:
    return admin_broadcast_service.BroadcastPreview(
        target=payload.target,
        text=payload.text,
        photo_storage_key=payload.photo_storage_key,
        photo_file_id=payload.photo_file_id,
        button_text=payload.button_text,
        button_url=payload.button_url,
        preview_content_fingerprint=payload.preview_content_fingerprint,
        preview_fingerprint=payload.preview_fingerprint,
        preview_count=payload.preview_count,
    )


@router.post("/media", response_model=BroadcastPhotoOut, status_code=201)
async def upload_broadcast_photo(
    file: UploadFile = File(...),
    admin: Admin = Depends(get_current_admin),
) -> BroadcastPhotoOut:
    if file.content_type not in broadcast_media_service.SUPPORTED_BROADCAST_IMAGE_TYPES:
        raise UnsupportedMediaTypeError("Broadcast photo must be JPEG, PNG, or WebP")
    content = await file.read(broadcast_media_service.MAX_BROADCAST_PHOTO_BYTES + 1)
    if len(content) > broadcast_media_service.MAX_BROADCAST_PHOTO_BYTES:
        raise BroadcastMediaTooLargeError(
            "Broadcast photo exceeds the upload limit",
            details={"max_bytes": broadcast_media_service.MAX_BROADCAST_PHOTO_BYTES},
        )
    storage_key = broadcast_media_service.store_broadcast_photo(
        content=content,
        content_type=file.content_type or "",
    )
    return BroadcastPhotoOut(photo_storage_key=storage_key)


@router.post("/preview", response_model=BroadcastPreviewOut)
async def preview_broadcast(
    payload: BroadcastPreviewIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> BroadcastPreviewOut:
    preview = await admin_broadcast_service.preview_broadcast(
        session,
        admin_id=admin.id,
        target=payload.target,
        text=payload.text,
        photo_storage_key=payload.photo_storage_key,
        photo_file_id=payload.photo_file_id,
        button_text=payload.button_text,
        button_url=payload.button_url,
    )
    return BroadcastPreviewOut(
        preview_fingerprint=preview.preview_fingerprint,
        preview_content_fingerprint=preview.preview_content_fingerprint,
        preview_count=preview.preview_count,
    )


@router.post("", response_model=BroadcastOut, status_code=201)
async def create_broadcast_draft(
    payload: BroadcastDraftIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> BroadcastOut:
    preview = _as_preview(payload)
    broadcast = await admin_broadcast_service.create_broadcast_draft(
        session, admin_id=admin.id, preview=preview
    )
    return await _response(session, broadcast)


@router.get("/{broadcast_id}", response_model=BroadcastOut)
async def get_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
) -> BroadcastOut:
    broadcast = await admin_broadcast_service.get_broadcast(session, broadcast_id=broadcast_id)
    return await _response(session, broadcast)


@router.post("/{broadcast_id}/launch", response_model=BroadcastOut, status_code=202)
async def launch_broadcast(
    broadcast_id: int,
    payload: BroadcastLaunchIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> BroadcastOut:
    broadcast = await admin_broadcast_service.launch_broadcast(
        session,
        admin_id=admin.id,
        broadcast_id=broadcast_id,
        preview_fingerprint=payload.preview_fingerprint,
        preview_count=payload.preview_count,
        idempotency_key=payload.idempotency_key,
    )
    return await _response(session, broadcast)


@router.post("/{broadcast_id}/cancel", response_model=BroadcastOut)
async def cancel_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(get_current_admin),
) -> BroadcastOut:
    broadcast = await admin_broadcast_service.cancel_broadcast(
        session, admin_id=admin.id, broadcast_id=broadcast_id
    )
    return await _response(session, broadcast)
