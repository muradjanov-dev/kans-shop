from collections.abc import Callable

from aiogram.types import CallbackQuery, InaccessibleMessage, Message


async def require_message(
    callback: CallbackQuery, translator: Callable[..., str]
) -> Message | None:
    """`CallbackQuery.message` can be None or an InaccessibleMessage (too old to edit) — this
    narrows to a real, editable Message or bails out with a localized alert."""
    if callback.message is None or isinstance(callback.message, InaccessibleMessage):
        await callback.answer(translator("common.error_generic"), show_alert=True)
        return None
    return callback.message
