import asyncio
import contextlib
from collections.abc import Callable, Sequence

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    BroadcastButtonChoiceCallback,
    BroadcastConfirmCallback,
    BroadcastTargetCallback,
)
from app.bot.keyboards.inline.admin_broadcast import (
    broadcast_button_choice_keyboard,
    broadcast_confirm_keyboard,
    broadcast_content_button,
    broadcast_target_keyboard,
)
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.states.admin_catalog import BroadcastFormStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.enums import BroadcastStatus, BroadcastTarget
from app.db.models.user import User
from app.db.repositories import broadcast_repository, user_repository

router = Router(name="admin_broadcast")

MESSAGES_PER_SECOND = 20
PROGRESS_UPDATE_EVERY = 20


async def render_broadcast_entry(
    message: Message, state: FSMContext, translator: Callable[..., str]
) -> None:
    await state.set_state(BroadcastFormStates.entering_content)
    await message.edit_text(
        translator("admin.broadcast_enter_content"),
        reply_markup=cancel_only_keyboard(translator),
    )


@router.message(BroadcastFormStates.entering_content, F.photo)
async def on_broadcast_photo(message: Message, state: FSMContext, _: Callable) -> None:
    if not message.photo:
        return
    await state.update_data(
        photo_file_id=message.photo[-1].file_id, content_text=message.caption or ""
    )
    await state.set_state(BroadcastFormStates.choosing_button)
    await message.answer(
        _("admin.broadcast_ask_button"), reply_markup=broadcast_button_choice_keyboard(_)
    )


@router.message(BroadcastFormStates.entering_content, F.text)
async def on_broadcast_text(message: Message, state: FSMContext, _: Callable) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    await state.update_data(photo_file_id=None, content_text=text)
    await state.set_state(BroadcastFormStates.choosing_button)
    await message.answer(
        _("admin.broadcast_ask_button"), reply_markup=broadcast_button_choice_keyboard(_)
    )


@router.callback_query(
    BroadcastFormStates.choosing_button, BroadcastButtonChoiceCallback.filter()
)
async def on_button_choice(
    callback: CallbackQuery,
    callback_data: BroadcastButtonChoiceCallback,
    state: FSMContext,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    if callback_data.add_button:
        await state.set_state(BroadcastFormStates.entering_button_text)
        await message.edit_text(
            _("admin.broadcast_enter_button_text"), reply_markup=cancel_only_keyboard(_)
        )
    else:
        await state.update_data(button_text=None, button_url=None)
        await state.set_state(BroadcastFormStates.choosing_target)
        await message.edit_text(
            _("admin.broadcast_choose_target"), reply_markup=broadcast_target_keyboard(_)
        )
    await callback.answer()


@router.message(BroadcastFormStates.entering_button_text, F.text)
async def on_button_text_entered(message: Message, state: FSMContext, _: Callable) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    await state.update_data(button_text=text)
    await state.set_state(BroadcastFormStates.entering_button_url)
    await message.answer(
        _("admin.broadcast_enter_button_url"), reply_markup=cancel_only_keyboard(_)
    )


@router.message(BroadcastFormStates.entering_button_url, F.text)
async def on_button_url_entered(message: Message, state: FSMContext, _: Callable) -> None:
    url = (message.text or "").strip()
    if not url.startswith(("https://", "http://")):
        await message.answer(
            _("admin.broadcast_invalid_url"), reply_markup=cancel_only_keyboard(_)
        )
        return
    await state.update_data(button_url=url)
    await state.set_state(BroadcastFormStates.choosing_target)
    await message.answer(
        _("admin.broadcast_choose_target"), reply_markup=broadcast_target_keyboard(_)
    )


@router.callback_query(BroadcastFormStates.choosing_target, BroadcastTargetCallback.filter())
async def on_target_chosen(
    callback: CallbackQuery,
    callback_data: BroadcastTargetCallback,
    state: FSMContext,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(target=callback_data.target)
    await state.set_state(BroadcastFormStates.confirming)
    data = await state.get_data()

    button_markup = broadcast_content_button(data.get("button_text"), data.get("button_url"))
    preview_text = f"{_('admin.broadcast_preview_title')}\n\n{data.get('content_text', '')}"
    if data.get("photo_file_id"):
        await message.answer_photo(
            data["photo_file_id"], caption=preview_text, reply_markup=button_markup
        )
    else:
        await message.answer(preview_text, reply_markup=button_markup)

    await message.answer(
        _("admin.broadcast_choose_target"), reply_markup=broadcast_confirm_keyboard(_)
    )
    await callback.answer()


@router.callback_query(
    BroadcastFormStates.confirming, BroadcastConfirmCallback.filter(F.action == "cancel")
)
async def on_broadcast_cancel(callback: CallbackQuery, state: FSMContext, _: Callable) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.clear()
    await message.edit_text(_("admin.broadcast_cancelled"))
    await callback.answer()


@router.callback_query(
    BroadcastFormStates.confirming, BroadcastConfirmCallback.filter(F.action == "send")
)
async def on_broadcast_send(
    callback: CallbackQuery,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    assert admin is not None

    data = await state.get_data()
    await state.clear()

    broadcast = await broadcast_repository.create(
        session,
        admin_id=admin.id,
        text=data.get("content_text", ""),
        photo_file_id=data.get("photo_file_id"),
        button_text=data.get("button_text"),
        button_url=data.get("button_url"),
        target=BroadcastTarget(data["target"]),
    )
    await broadcast_repository.mark_sending(session, broadcast)
    await callback.answer()

    audience = await user_repository.list_for_broadcast(session, data["target"])
    button_markup = broadcast_content_button(data.get("button_text"), data.get("button_url"))
    progress_message = await message.edit_text(
        _("admin.broadcast_sending", sent=0, total=len(audience))
    )
    assert isinstance(progress_message, Message)

    sent, failed = await _run_broadcast(
        bot,
        session,
        audience,
        text=data.get("content_text", ""),
        photo_file_id=data.get("photo_file_id"),
        button_markup=button_markup,
        progress_message=progress_message,
        translator=_,
    )

    status = BroadcastStatus.COMPLETED if failed < len(audience) else BroadcastStatus.FAILED
    await broadcast_repository.finish(
        session, broadcast, sent=sent, failed=failed, status=status
    )
    await progress_message.edit_text(_("admin.broadcast_done", sent=sent, failed=failed))


async def _send_one(
    bot: Bot,
    session: AsyncSession,
    user: User,
    *,
    text: str,
    photo_file_id: str | None,
    button_markup: InlineKeyboardMarkup | None,
) -> bool:
    try:
        if photo_file_id:
            await bot.send_photo(
                user.telegram_id, photo_file_id, caption=text, reply_markup=button_markup
            )
        else:
            await bot.send_message(user.telegram_id, text, reply_markup=button_markup)
        return True
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            if photo_file_id:
                await bot.send_photo(
                    user.telegram_id, photo_file_id, caption=text, reply_markup=button_markup
                )
            else:
                await bot.send_message(user.telegram_id, text, reply_markup=button_markup)
            return True
        except (TelegramForbiddenError, TelegramRetryAfter):
            return False
    except TelegramForbiddenError:
        await user_repository.set_blocked(session, user, True)
        return False


async def _run_broadcast(
    bot: Bot,
    session: AsyncSession,
    audience: Sequence[User],
    *,
    text: str,
    photo_file_id: str | None,
    button_markup: InlineKeyboardMarkup | None,
    progress_message: Message,
    translator: Callable[..., str],
) -> tuple[int, int]:
    sent = 0
    failed = 0
    total = len(audience)
    for index, user in enumerate(audience, start=1):
        ok = await _send_one(
            bot,
            session,
            user,
            text=text,
            photo_file_id=photo_file_id,
            button_markup=button_markup,
        )
        if ok:
            sent += 1
        else:
            failed += 1
        if index % PROGRESS_UPDATE_EVERY == 0 or index == total:
            # e.g. "message is not modified" when the count didn't change since last edit —
            # never let a cosmetic progress-update failure abort the send loop.
            with contextlib.suppress(TelegramBadRequest):
                await progress_message.edit_text(
                    translator("admin.broadcast_sending", sent=index, total=total)
                )
        await asyncio.sleep(1 / MESSAGES_PER_SECOND)
    await session.commit()
    return sent, failed
