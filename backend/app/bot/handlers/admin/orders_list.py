from collections.abc import Awaitable, Callable

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import AdminOrderFilterCallback
from app.bot.keyboards.inline.admin_orders_list import admin_order_list_keyboard
from app.bot.utils.admin_guard import require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.enums import OrderStatus
from app.services import admin_order_service

router = Router(name="admin_orders_list")

ORDERS_PAGE_SIZE = 10

Sender = Callable[..., Awaitable[object]]


async def render_orders_list(
    send: Sender,
    session: AsyncSession,
    admin_id: int,
    status: str,
    page: int,
    translator: Callable[..., str],
) -> None:
    status_enum = OrderStatus(status) if status != "all" else None
    page_obj = await admin_order_service.list_admin_orders(
        session,
        admin_id=admin_id,
        status=status_enum,
        query=None,
        date_from=None,
        date_to=None,
        page=page,
        limit=ORDERS_PAGE_SIZE,
    )
    text = translator("admin.orders_list_title")
    if not page_obj.items:
        text += "\n\n" + translator("admin.orders_empty")
    await send(
        text,
        reply_markup=admin_order_list_keyboard(page_obj, status=status, translator=translator),
    )


@router.callback_query(AdminOrderFilterCallback.filter())
async def on_order_filter(
    callback: CallbackQuery,
    callback_data: AdminOrderFilterCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, session=session):
        return
    assert admin is not None
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await render_orders_list(
        edit, session, admin.id, callback_data.status, callback_data.page, _
    )
    await callback.answer()
