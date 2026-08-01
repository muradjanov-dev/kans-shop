from aiogram import Bot
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_db
from app.api.schemas.order import CheckoutIn, OrderOut
from app.bot.services.order_notifications import notify_admins_new_order
from app.core.config import settings
from app.core.exceptions import ForbiddenError, InvalidFileError
from app.core.uploads import (
    ALLOWED_RECEIPT_MIME_TYPES,
    MAX_RECEIPT_SIZE_BYTES,
    MIME_EXTENSIONS,
)
from app.db.models.user import User
from app.db.repositories import order_repository
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
async def checkout(
    payload: CheckoutIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    bot: Bot = Depends(get_bot),
) -> OrderOut:
    order = await order_service.checkout(
        session,
        user_id=user.id,
        order_type=payload.order_type,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        payment_method=payload.payment_method,
        address=payload.address,
        address_comment=payload.address_comment,
        latitude=payload.latitude,
        longitude=payload.longitude,
        comment=payload.comment,
        source="webapp",
        lang=user.language,
    )
    await notify_admins_new_order(bot, session, order)
    return OrderOut.model_validate(order)


@router.get("", response_model=list[OrderOut])
async def list_my_orders(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[OrderOut]:
    orders, _total = await order_repository.list_by_user(session, user.id, page=1, limit=50)
    return [OrderOut.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await order_service.get_order(session, order_id)
    if order.user_id != user.id:
        raise ForbiddenError("Not your order")
    return OrderOut.model_validate(order)


@router.post("/{order_id}/receipt", response_model=OrderOut)
async def upload_receipt(
    order_id: int,
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrderOut:
    order = await order_service.get_order(session, order_id)
    if order.user_id != user.id:
        raise ForbiddenError("Not your order")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_RECEIPT_MIME_TYPES:
        raise InvalidFileError("Unsupported file type", details={"content_type": content_type})
    data = await file.read()
    if len(data) > MAX_RECEIPT_SIZE_BYTES:
        raise InvalidFileError("File too large", details={"max_bytes": MAX_RECEIPT_SIZE_BYTES})

    ext = MIME_EXTENSIONS[content_type]
    receipts_dir = settings.media_root_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    destination = receipts_dir / f"{order.id}.{ext}"
    destination.write_bytes(data)
    url = f"{settings.media_base_url}/receipts/{destination.name}"

    order = await order_service.attach_receipt(session, order, file_id=None, url=url)
    return OrderOut.model_validate(order)
