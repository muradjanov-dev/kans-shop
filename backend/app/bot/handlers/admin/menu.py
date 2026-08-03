from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.broadcast import render_broadcast_entry
from app.bot.handlers.admin.categories import render_categories_list
from app.bot.handlers.admin.orders_list import render_orders_list
from app.bot.handlers.admin.products import render_products_category_picker
from app.bot.handlers.admin.settings import render_settings
from app.bot.handlers.admin.stats import render_stats
from app.bot.handlers.admin.users import render_users_list
from app.bot.keyboards.callback_data import ROOT_CATEGORY_ID, AdminMenuCallback
from app.bot.keyboards.inline.admin_menu import admin_menu_keyboard
from app.bot.utils.admin_guard import require_admin
from app.bot.utils.i18n import menu_button_texts
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.enums import OrderStatus
from app.db.repositories import order_repository

router = Router(name="admin_menu")


async def _new_orders_count(session: AsyncSession) -> int:
    _orders, total = await order_repository.list_for_admin(
        session, status=OrderStatus.NEW, page=1, limit=1
    )
    return total


@router.message(Command("admin"))
@router.message(F.text.in_(menu_button_texts("admin.menu_title")))
async def cmd_admin(
    message: Message, session: AsyncSession, admin: Admin | None, _: Callable
) -> None:
    if not await require_admin(message, admin, _):
        return
    count = await _new_orders_count(session)
    await message.answer(
        _("admin.menu_title"), reply_markup=admin_menu_keyboard(_, new_orders_count=count)
    )


@router.callback_query(AdminMenuCallback.filter())
async def on_menu_section(
    callback: CallbackQuery,
    callback_data: AdminMenuCallback,
    session: AsyncSession,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    section = callback_data.section
    if section == "menu":
        count = await _new_orders_count(session)
        await edit(
            _("admin.menu_title"), reply_markup=admin_menu_keyboard(_, new_orders_count=count)
        )
    elif section == "orders":
        await render_orders_list(edit, session, "all", 1, _)
    elif section == "categories":
        await render_categories_list(edit, session, ROOT_CATEGORY_ID, translator=_)
    elif section == "products":
        await render_products_category_picker(edit, session, _)
    elif section == "stats":
        await render_stats(edit, session, "today", _)
    elif section == "broadcast":
        await render_broadcast_entry(message, state, _)
    elif section == "users":
        await render_users_list(edit, session, 1, _)
    elif section == "settings":
        await render_settings(edit, session, _)
    await callback.answer()
