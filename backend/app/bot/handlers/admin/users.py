from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import AdminUserDetail
from app.bot.keyboards.callback_data import AdminUserActionCallback, AdminUserListCallback
from app.bot.keyboards.inline.admin_users import (
    admin_user_detail_keyboard,
    admin_user_list_keyboard,
)
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.core.exceptions import AdminSessionRequiredError, ForbiddenError, UserNotFoundError
from app.db.models.admin import Admin
from app.db.models.user import User
from app.services import customer_admin_service

router = Router(name="admin_users")

USERS_PAGE_SIZE = 15

Sender = Callable[..., Awaitable[object]]


async def render_users_list(
    send: Sender,
    session: AsyncSession,
    page: int,
    translator: Callable[..., str],
    *,
    admin_id: int,
) -> None:
    page_obj = await customer_admin_service.list_admin_users(
        session,
        admin_id=admin_id,
        query=None,
        page=page,
        limit=USERS_PAGE_SIZE,
    )
    await send(
        translator("admin.users_title"),
        reply_markup=admin_user_list_keyboard(page_obj, translator=translator),
    )


async def _render_user_detail(
    message: Message,
    user: AdminUserDetail,
    translator: Callable[..., str],
) -> None:
    name = f"{user.first_name} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else translator("admin.no_username")
    first_touch_source = (
        f"{user.first_touch_source.name} ({user.first_touch_source.code})"
        if user.first_touch_source is not None
        else "-"
    )
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
        orders_count=user.orders_count,
        first_touch_source=first_touch_source,
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
    admin_id: int,
    translator: Callable[..., str],
) -> AdminUserDetail | None:
    try:
        return await customer_admin_service.get_admin_user(
            session, admin_id=admin_id, user_id=user_id
        )
    except UserNotFoundError:
        await callback.answer(translator("admin.user_not_found"), show_alert=True)
        return None
    except (AdminSessionRequiredError, ForbiddenError):
        await callback.answer(translator("admin.not_admin_alert"), show_alert=True)
        return None


@router.callback_query(AdminUserListCallback.filter())
async def on_user_list(
    callback: CallbackQuery,
    callback_data: AdminUserListCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    if admin is None:
        return
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await render_users_list(edit, session, callback_data.page, _, admin_id=admin.id)
    await callback.answer()


@router.callback_query(AdminUserActionCallback.filter(F.action == "view"))
async def on_user_view(
    callback: CallbackQuery,
    callback_data: AdminUserActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    if admin is None:
        return
    message = await require_message(callback, _)
    if message is None:
        return
    user = await _get_user_or_alert(callback, session, callback_data.user_id, admin.id, _)
    if user is None:
        return
    await _render_user_detail(message, user, _)
    await callback.answer()


@router.callback_query(AdminUserActionCallback.filter(F.action.in_(("block", "unblock"))))
async def on_user_block_toggle(
    callback: CallbackQuery,
    callback_data: AdminUserActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    if admin is None:
        return
    message = await require_message(callback, _)
    if message is None:
        return
    detail = await _get_user_or_alert(callback, session, callback_data.user_id, admin.id, _)
    if detail is None:
        return
    blocked = callback_data.action == "block"
    user: User
    try:
        user = await customer_admin_service.set_user_blocked(
            session,
            admin_id=admin.id,
            user_id=callback_data.user_id,
            blocked=blocked,
        )
    except UserNotFoundError:
        await callback.answer(_("admin.user_not_found"), show_alert=True)
        return
    except (AdminSessionRequiredError, ForbiddenError):
        await callback.answer(_("admin.not_admin_alert"), show_alert=True)
        return
    refreshed = await customer_admin_service.get_admin_user(
        session, admin_id=admin.id, user_id=user.id
    )
    await _render_user_detail(message, refreshed, _)
    done_key = "admin.user_blocked_done" if blocked else "admin.user_unblocked_done"
    await callback.answer(_(done_key))
