"""Admin section: managing the admin team itself — add by Telegram ID, change role,
deactivate, remove. Superadmin only.

Adding an admin here only writes the `admins` row; the new admin's `users` row (and the
`admin` object handlers receive) is resolved by UserRegistrationMiddleware on their next
message, so they get access the moment they touch the bot — they do not need to have used it
before being added.
"""

from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    AdminManageActionCallback,
    AdminManageAddCallback,
    AdminManageDetailCallback,
    AdminRoleChooseCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_manage import (
    ROLE_LABEL_KEYS,
    admin_detail_keyboard,
    admin_remove_confirm_keyboard,
    admins_list_keyboard,
    role_picker_keyboard,
)
from app.bot.states.admin_catalog import AdminManageFormStates
from app.bot.utils.admin_guard import require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.repositories import admin_repository, user_repository

router = Router(name="admin_manage")

Sender = Callable[..., Awaitable[object]]

# Only a superadmin may change who has access at all.
SUPERADMIN_ONLY = (AdminRole.SUPERADMIN,)


async def render_admins_list(
    send: Sender, session: AsyncSession, *, translator: Callable[..., str]
) -> None:
    admins = await admin_repository.list_all(session)
    await send(
        translator("admin.admins_title"),
        reply_markup=admins_list_keyboard(admins, translator=translator),
    )


async def render_admin_detail(
    send: Sender,
    session: AsyncSession,
    target: Admin,
    *,
    translator: Callable[..., str],
    is_self: bool,
) -> None:
    user = await user_repository.get_by_telegram_id(session, target.telegram_id)
    username = (
        f"@{user.username}" if user and user.username else translator("admin.no_username")
    )
    status_key = (
        "admin.admin_status_active" if target.is_active else "admin.admin_status_inactive"
    )
    text = translator(
        "admin.admin_detail",
        name=target.full_name,
        telegram_id=target.telegram_id,
        username=username,
        role=translator(ROLE_LABEL_KEYS[target.role]),
        status=translator(status_key),
        created_at=target.created_at.strftime("%Y-%m-%d"),
    )
    await send(
        text,
        reply_markup=admin_detail_keyboard(target, translator=translator, is_self=is_self),
    )


async def _get_target_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    admin_id: int,
    translator: Callable[..., str],
) -> Admin | None:
    target = await admin_repository.get_by_id(session, admin_id)
    if target is None:
        await callback.answer(translator("admin.admin_not_found"), show_alert=True)
    return target


@router.callback_query(AdminManageDetailCallback.filter())
async def on_admin_detail(
    callback: CallbackQuery,
    callback_data: AdminManageDetailCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    target = await _get_target_or_alert(callback, session, callback_data.admin_id, _)
    if target is None:
        return
    await render_admin_detail(
        message.edit_text,
        session,
        target,
        translator=_,
        is_self=admin is not None and target.id == admin.id,
    )
    await callback.answer()


# --- Add an admin: Telegram ID -> name -> role ---------------------------------------------


@router.callback_query(AdminManageAddCallback.filter())
async def on_admin_add(
    callback: CallbackQuery, admin: Admin | None, state: FSMContext, _: Callable
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(AdminManageFormStates.entering_telegram_id)
    await message.edit_text(
        _("admin.admin_enter_telegram_id"), reply_markup=cancel_only_keyboard(_)
    )
    await callback.answer()


@router.message(AdminManageFormStates.entering_telegram_id, F.text)
async def on_admin_telegram_id_entered(
    message: Message, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    raw = (message.text or "").strip().removeprefix("@")
    try:
        telegram_id = int(raw)
    except ValueError:
        await message.answer(
            _("admin.admin_invalid_telegram_id"), reply_markup=cancel_only_keyboard(_)
        )
        return

    if await admin_repository.get_by_telegram_id(session, telegram_id) is not None:
        await message.answer(
            _("admin.admin_already_exists"), reply_markup=cancel_only_keyboard(_)
        )
        return

    # If this person has already used the bot, offer their real name as the default so the
    # superadmin usually just taps through.
    existing_user = await user_repository.get_by_telegram_id(session, telegram_id)
    suggested = ""
    if existing_user is not None:
        suggested = f"{existing_user.first_name} {existing_user.last_name or ''}".strip()

    await state.update_data(telegram_id=telegram_id, suggested_name=suggested)
    await state.set_state(AdminManageFormStates.entering_name)
    await message.answer(
        _("admin.admin_enter_name", suggested=suggested or "-"),
        reply_markup=cancel_only_keyboard(_),
    )


@router.message(AdminManageFormStates.entering_name, F.text)
async def on_admin_name_entered(message: Message, state: FSMContext, _: Callable) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    # "-" accepts the name pulled from their existing users row.
    name = data.get("suggested_name", "") if raw == "-" else raw
    if not name:
        await message.answer(
            _("admin.admin_enter_name", suggested="-"), reply_markup=cancel_only_keyboard(_)
        )
        return

    await state.update_data(full_name=name[:128])
    await state.set_state(AdminManageFormStates.choosing_role)
    await message.answer(
        _("admin.admin_choose_role"),
        reply_markup=role_picker_keyboard(admin_id=0, translator=_),
    )


@router.callback_query(
    AdminManageFormStates.choosing_role, AdminRoleChooseCallback.filter(F.admin_id == 0)
)
async def on_admin_role_chosen_for_new(
    callback: CallbackQuery,
    callback_data: AdminRoleChooseCallback,
    session: AsyncSession,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return

    data = await state.get_data()
    await state.clear()
    telegram_id = data.get("telegram_id")
    if telegram_id is None:
        await callback.answer(_("common.error_generic"), show_alert=True)
        return

    # Re-check: another superadmin may have added the same id while this form was open.
    if await admin_repository.get_by_telegram_id(session, telegram_id) is not None:
        await callback.answer(_("admin.admin_already_exists"), show_alert=True)
        await render_admins_list(message.edit_text, session, translator=_)
        return

    target = await admin_repository.create(
        session,
        telegram_id=telegram_id,
        full_name=data.get("full_name", str(telegram_id)),
        role=AdminRole(callback_data.role),
    )
    await callback.answer(_("admin.admin_created"))
    await render_admin_detail(message.edit_text, session, target, translator=_, is_self=False)


# --- Change role of an existing admin -------------------------------------------------------


@router.callback_query(AdminManageActionCallback.filter(F.action == "role_menu"))
async def on_admin_role_menu(
    callback: CallbackQuery,
    callback_data: AdminManageActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    target = await _get_target_or_alert(callback, session, callback_data.admin_id, _)
    if target is None:
        return
    await message.edit_text(
        _("admin.admin_choose_role"),
        reply_markup=role_picker_keyboard(admin_id=target.id, translator=_),
    )
    await callback.answer()


@router.callback_query(AdminRoleChooseCallback.filter(F.admin_id != 0))
async def on_admin_role_changed(
    callback: CallbackQuery,
    callback_data: AdminRoleChooseCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    target = await _get_target_or_alert(callback, session, callback_data.admin_id, _)
    if target is None:
        return

    new_role = AdminRole(callback_data.role)
    if not await _may_demote(session, target, new_role=new_role, is_active=target.is_active):
        await callback.answer(_("admin.admin_last_superadmin"), show_alert=True)
        return

    await admin_repository.set_role(session, target, new_role)
    await render_admin_detail(
        message.edit_text,
        session,
        target,
        translator=_,
        is_self=admin is not None and target.id == admin.id,
    )
    await callback.answer()


async def _may_demote(
    session: AsyncSession, target: Admin, *, new_role: AdminRole, is_active: bool
) -> bool:
    """Blocks the change that would leave the shop with no active superadmin — nobody could
    then add admins, edit settings, or restore access without direct database surgery."""
    still_superadmin = new_role == AdminRole.SUPERADMIN and is_active
    if still_superadmin:
        return True
    was_superadmin = target.role == AdminRole.SUPERADMIN and target.is_active
    if not was_superadmin:
        return True
    return await admin_repository.count_active_superadmins(session) > 1


# --- Activate / deactivate / remove ----------------------------------------------------------


@router.callback_query(AdminManageActionCallback.filter(F.action == "toggle"))
async def on_admin_toggle(
    callback: CallbackQuery,
    callback_data: AdminManageActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    target = await _get_target_or_alert(callback, session, callback_data.admin_id, _)
    if target is None:
        return

    new_active = not target.is_active
    if not await _may_demote(session, target, new_role=target.role, is_active=new_active):
        await callback.answer(_("admin.admin_last_superadmin"), show_alert=True)
        return

    await admin_repository.set_active(session, target, new_active)
    await render_admin_detail(
        message.edit_text,
        session,
        target,
        translator=_,
        is_self=admin is not None and target.id == admin.id,
    )
    await callback.answer()


@router.callback_query(AdminManageActionCallback.filter(F.action == "remove_request"))
async def on_admin_remove_request(
    callback: CallbackQuery,
    callback_data: AdminManageActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    target = await _get_target_or_alert(callback, session, callback_data.admin_id, _)
    if target is None:
        return
    await message.edit_text(
        _("admin.admin_remove_confirm", name=target.full_name),
        reply_markup=admin_remove_confirm_keyboard(target, translator=_),
    )
    await callback.answer()


@router.callback_query(AdminManageActionCallback.filter(F.action == "remove_confirm"))
async def on_admin_remove_confirm(
    callback: CallbackQuery,
    callback_data: AdminManageActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=SUPERADMIN_ONLY):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    target = await _get_target_or_alert(callback, session, callback_data.admin_id, _)
    if target is None:
        return
    if admin is not None and target.id == admin.id:
        await callback.answer(_("admin.admin_cannot_remove_self"), show_alert=True)
        return
    if not await _may_demote(session, target, new_role=target.role, is_active=False):
        await callback.answer(_("admin.admin_last_superadmin"), show_alert=True)
        return

    await admin_repository.delete(session, target)
    await callback.answer(_("admin.admin_removed"))
    await render_admins_list(message.edit_text, session, translator=_)
