from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.receipt_redirect import ReceiptRedirectStates
from app.bot.utils.receipt_upload import download_telegram_receipt
from app.core.config import settings
from app.core.exceptions import (
    ForbiddenError,
    InvalidFileError,
    OrderAlreadyProcessedError,
    OrderNotFoundError,
)
from app.db.models.user import User
from app.services.receipt_service import attach_card_transfer_receipt
from app.services.receipt_storage import PrivateReceiptStorage

router = Router(name="receipt_redirect")


async def _finish(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
    user: User,
    *,
    file_id: str,
    declared_content_type: str,
    translator: Callable[..., str],
) -> None:
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        return
    try:
        content = await download_telegram_receipt(bot, file_id, declared_content_type)
        order = await attach_card_transfer_receipt(
            session,
            PrivateReceiptStorage(settings.private_media_root_path),
            order_id=order_id,
            owner_user_id=user.id,
            content=content,
            declared_content_type=declared_content_type,
            telegram_file_id=file_id,
        )
    except InvalidFileError as exc:
        key = (
            "checkout.receipt_too_large"
            if exc.details.get("max_bytes") is not None
            else "checkout.receipt_bad_type"
        )
        await message.answer(translator(key))
        return
    except (ForbiddenError, OrderAlreadyProcessedError, OrderNotFoundError):
        await state.clear()
        await message.answer(translator("checkout.invalid_receipt"))
        return

    await state.clear()
    await message.answer(
        translator("checkout.receipt_uploaded_success", order_number=order.order_number)
    )


@router.message(ReceiptRedirectStates.uploading, F.photo)
async def on_photo(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
    user: User,
    _: Callable,
) -> None:
    if not message.photo:
        return
    await _finish(
        message,
        session,
        bot,
        state,
        user,
        file_id=message.photo[-1].file_id,
        declared_content_type="image/jpeg",
        translator=_,
    )


@router.message(ReceiptRedirectStates.uploading, F.document)
async def on_document(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
    user: User,
    _: Callable,
) -> None:
    doc = message.document
    if doc is None:
        return
    await _finish(
        message,
        session,
        bot,
        state,
        user,
        file_id=doc.file_id,
        declared_content_type=doc.mime_type or "",
        translator=_,
    )


@router.message(ReceiptRedirectStates.uploading)
async def on_invalid(message: Message, _: Callable) -> None:
    await message.answer(_("checkout.invalid_receipt"))
