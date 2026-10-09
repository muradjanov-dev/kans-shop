import html
from collections.abc import Callable
from uuid import UUID, uuid4

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
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
from app.db.models.enums import BroadcastTarget
from app.services.admin_broadcast_service import (
    BroadcastAudienceChangedError,
    BroadcastPreview,
    BroadcastPreviewChangedError,
    create_broadcast_draft,
    launch_broadcast,
    preview_broadcast,
)

router = Router(name="admin_broadcast")


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
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    data = await state.get_data()
    target = BroadcastTarget(callback_data.target)
    assert admin is not None
    preview = await preview_broadcast(
        session,
        admin_id=admin.id,
        target=target,
        text=data.get("content_text", ""),
        photo_storage_key=None,
        photo_file_id=data.get("photo_file_id"),
        button_text=data.get("button_text"),
        button_url=data.get("button_url"),
    )
    await state.update_data(
        target=target.value,
        preview_content_fingerprint=preview.preview_content_fingerprint,
        preview_fingerprint=preview.preview_fingerprint,
        preview_count=preview.preview_count,
        idempotency_key=str(uuid4()),
    )
    await state.set_state(BroadcastFormStates.confirming)

    button_markup = broadcast_content_button(data.get("button_text"), data.get("button_url"))
    preview_text = (
        f"{_('admin.broadcast_preview_title')}\n\n"
        f"{html.escape(data.get('content_text', ''))}"
    )
    if data.get("photo_file_id"):
        await message.answer_photo(
            data["photo_file_id"],
            caption=preview_text,
            reply_markup=button_markup,
            parse_mode="HTML",
        )
    else:
        await message.answer(preview_text, reply_markup=button_markup, parse_mode="HTML")

    await message.answer(
        _("admin.broadcast_preview_audience", count=preview.preview_count),
        reply_markup=broadcast_confirm_keyboard(_),
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
    BroadcastFormStates.confirming, BroadcastConfirmCallback.filter(F.action == "launch")
)
async def on_broadcast_send(
    callback: CallbackQuery,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    assert admin is not None

    assert admin is not None
    data = await state.get_data()
    try:
        preview = BroadcastPreview(
            target=BroadcastTarget(data["target"]),
            text=data.get("content_text", ""),
            photo_storage_key=None,
            photo_file_id=data.get("photo_file_id"),
            button_text=data.get("button_text"),
            button_url=data.get("button_url"),
            preview_content_fingerprint=data["preview_content_fingerprint"],
            preview_fingerprint=data["preview_fingerprint"],
            preview_count=data["preview_count"],
        )
        broadcast = await create_broadcast_draft(session, admin_id=admin.id, preview=preview)
        await launch_broadcast(
            session,
            admin_id=admin.id,
            broadcast_id=broadcast.id,
            preview_fingerprint=preview.preview_fingerprint,
            preview_count=preview.preview_count,
            idempotency_key=UUID(data["idempotency_key"]),
        )
    except (BroadcastAudienceChangedError, BroadcastPreviewChangedError):
        await state.set_state(BroadcastFormStates.choosing_target)
        await message.edit_text(
            _("admin.broadcast_preview_expired"), reply_markup=broadcast_target_keyboard(_)
        )
        return
    except (KeyError, TypeError, ValueError):
        await message.edit_text(_("admin.broadcast_preview_expired"))
        await state.clear()
        return

    await state.clear()
    await callback.answer()
    await message.edit_text(_("admin.broadcast_queued", count=preview.preview_count))
