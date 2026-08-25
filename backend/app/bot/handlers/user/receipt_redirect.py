from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.receipt_redirect import ReceiptRedirectStates
from app.core.config import settings
from app.db.repositories import order_repository
from app.services import order_service

router = Router(name="receipt_redirect")


async def _persist_receipt(bot: Bot, order_id: int, file_id: str, is_document: bool) -> str:
    receipts_dir = settings.media_root_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    ext = "pdf" if is_document else "jpg"
    destination = receipts_dir / f"{order_id}.{ext}"
    await bot.download(file_id, destination=destination)
    return f"{settings.media_base_url}/receipts/{destination.name}"


async def _finish(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
    *,
    file_id: str,
    is_document: bool,
    translator: Callable[..., str],
) -> None:
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()
    if not order_id:
        return
    order = await order_repository.get_by_id(session, order_id)
    if order is None:
        return
    receipt_url = await _persist_receipt(bot, order.id, file_id, is_document)
    await order_service.attach_receipt(session, order, file_id=file_id, url=receipt_url)
    await message.answer(
        translator("checkout.receipt_uploaded_success", order_number=order.order_number)
    )


@router.message(ReceiptRedirectStates.uploading, F.photo)
async def on_photo(
    message: Message, session: AsyncSession, bot: Bot, state: FSMContext, _: Callable
) -> None:
    if not message.photo:
        return
    await _finish(
        message,
        session,
        bot,
        state,
        file_id=message.photo[-1].file_id,
        is_document=False,
        translator=_,
    )


@router.message(ReceiptRedirectStates.uploading, F.document)
async def on_document(
    message: Message, session: AsyncSession, bot: Bot, state: FSMContext, _: Callable
) -> None:
    doc = message.document
    if doc is None:
        return
    await _finish(
        message, session, bot, state, file_id=doc.file_id, is_document=True, translator=_
    )


@router.message(ReceiptRedirectStates.uploading)
async def on_invalid(message: Message, _: Callable) -> None:
    await message.answer(_("checkout.invalid_receipt"))
