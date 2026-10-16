import logging
from collections.abc import Awaitable, Callable

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyKeyboardRemove,
)

logger = logging.getLogger(__name__)


async def answer_with_inline_keyboard(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | bool:
    """Replace a legacy reply keyboard and attach inline choices to the same visible text."""
    sent_message = await message.answer(text, reply_markup=ReplyKeyboardRemove())
    if reply_markup is None:
        return sent_message
    try:
        return await sent_message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramAPIError as error:
        logger.warning(
            "inline keyboard attachment failed after message delivery",
            extra={"telegram_error_type": type(error).__name__},
        )
        return sent_message


def _is_expired_callback_query(error: TelegramBadRequest) -> bool:
    message = getattr(error, "message", str(error)).casefold()
    return any(
        marker in message
        for marker in (
            "query is too old",
            "query id is invalid",
            "query_id_invalid",
            "invalid query id",
        )
    )


async def answer_callback_safely(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    """Acknowledge a callback and report whether Telegram accepted the query.

    Only known expired/invalid callback-query errors are ignored. Other Telegram
    errors remain visible so handlers do not mask unrelated failures.
    """
    try:
        if text is None and not show_alert:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as error:
        if not _is_expired_callback_query(error):
            raise
        return False
    return True


async def edit_or_send_message(
    message: Message,
    text: str,
    *,
    reply_markup=None,
    photo: str | None = None,
    preserve_photo: bool = False,
) -> Message | bool:
    """Render text/photo content while respecting Telegram's message media rules.

    Text messages cannot be changed into photos (or back) with an edit method, so
    those transitions send a replacement and then remove the old bot message.
    Existing photos keep their message identity when only the caption changes.
    """
    current_photos = getattr(message, "photo", None) or ()
    current_file_id = current_photos[-1].file_id if current_photos else None

    if photo is None:
        if not current_photos:
            return await _edit_or_keep_message(
                message,
                lambda: message.edit_text(text, reply_markup=reply_markup),
            )
        replacement = await message.answer(text, reply_markup=reply_markup)
        await message.delete()
        return replacement

    if current_photos:
        if preserve_photo or current_file_id == photo:
            return await _edit_or_keep_message(
                message,
                lambda: message.edit_caption(caption=text, reply_markup=reply_markup),
            )
        return await _edit_or_keep_message(
            message,
            lambda: message.edit_media(
                media=InputMediaPhoto(media=photo, caption=text),
                reply_markup=reply_markup,
            ),
        )

    replacement = await message.answer_photo(
        photo=photo, caption=text, reply_markup=reply_markup
    )
    await message.delete()
    return replacement


async def _edit_or_keep_message(
    message: Message, edit: Callable[[], Awaitable[Message | bool]]
) -> Message | bool:
    try:
        return await edit()
    except TelegramBadRequest as error:
        error_message = getattr(error, "message", str(error)).casefold().strip()
        if error_message.startswith("bad request:"):
            error_message = error_message.removeprefix("bad request:").strip()
        if error_message.startswith("message is not modified"):
            return message
        raise


async def require_message(
    callback: CallbackQuery, translator: Callable[..., str]
) -> Message | None:
    """`CallbackQuery.message` can be None or an InaccessibleMessage (too old to edit) — this
    narrows to a real, editable Message or bails out with a localized alert."""
    if callback.message is None or isinstance(callback.message, InaccessibleMessage):
        await answer_callback_safely(
            callback, translator("common.error_generic"), show_alert=True
        )
        return None
    return callback.message
