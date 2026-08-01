from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import AdminUserActionCallback, AdminUserListCallback
from app.bot.keyboards.inline.admin_users import (
    admin_user_detail_keyboard,
    admin_user_list_keyboard,
)
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.user import User
from app.db.repositories import order_repository, user_repository
from app.services.common import Page

router = Router(name="admin_users")

USERS_PAGE_SIZE = 15

Sender = Callable[..., Awaitable[object]]


async def render_users_list(
    send: Sender, session: AsyncSession, page: int, translator: Callable[..., str]
) -> None:
    users, total = await user_repository.list_all(session, page=page, limit=USERS_PAGE_SIZE)
    page_obj = Page(items=users, total=total, page=page, limit=USERS_PAGE_SIZE)
    await send(
        translator("admin.users_title"),
        reply_markup=admin_user_list_keyboard(page_obj, translator=translator),
    )


async def _render_user_detail(
    message: Message, session: AsyncSession, user: User, translator: Callable[..., str]
) -> None:
    _orders, orders_count = await order_repository.list_by_user(
        session, user.id, page=1, limit=1
    )
    name = f"{user.first_name} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else translator("admin.no_username")
    status = (
        translator("admin.user_blocked")
        if user.is_blocked
        else translator("admin.user_active_status")
    )
    text = translator(
        "admin.user_detail",
        name=name,
        username=username,
        phone=user.phone or "-",
        language=user.language,
        orders_count=orders_count,
        created_at=user.created_at.strftime("%Y-%m-%d"),
        status=status,
    )
    await message.edit_text(
        text, reply_markup=admin_user_detail_keyboard(user, translator=translator)
    )


async def _get_user_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    user_id: int,
    translator: Callable[..., str],
) -> User | None:
    user = await user_repository.get_by_id(session, user_id)
    if user is None:
        await callback.answer(translator("admin.user_not_found"), show_alert=True)
    return user


@router.callback_query(AdminUserListCallback.filter())
async def on_user_list(
    callback: CallbackQuery,
    callback_data: AdminUserListCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await render_users_list(edit, session, callback_data.page, _)
    await callback.answer()


@router.callback_query(AdminUserActionCallback.filter(F.action == "view"))
async def on_user_view(
    callback: CallbackQuery,
    callback_data: AdminUserActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    user = await _get_user_or_alert(callback, session, callback_data.user_id, _)
    if user is None:
        return
    await _render_user_detail(message, session, user, _)
    await callback.answer()


@router.callback_query(AdminUserActionCallback.filter(F.action.in_(("block", "unblock"))))
async def on_user_block_toggle(
    callback: CallbackQuery,
    callback_data: AdminUserActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    user = await _get_user_or_alert(callback, session, callback_data.user_id, _)
    if user is None:
        return

    blocked = callback_data.action == "block"
    await user_repository.set_blocked(session, user, blocked)
    await _render_user_detail(message, session, user, _)
    done_key = "admin.user_blocked_done" if blocked else "admin.user_unblocked_done"
    await callback.answer(_(done_key))
