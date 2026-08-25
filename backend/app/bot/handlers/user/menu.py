from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.user.cart import render_cart
from app.bot.handlers.user.catalog import send_category_level
from app.bot.handlers.user.favorites import render_favorites
from app.bot.handlers.user.orders import render_orders
from app.bot.keyboards.callback_data import ROOT_CATEGORY_ID, MenuCallback
from app.bot.keyboards.inline.language import language_keyboard
from app.bot.keyboards.inline.main_menu import main_menu_inline_keyboard
from app.bot.utils.i18n import menu_button_texts
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.user import User
from app.db.repositories import setting_repository

router = Router(name="menu")


async def send_main_menu(
    message: Message,
    *,
    translator: Callable[..., str],
    is_admin: bool = False,
    clear_reply_keyboard: bool = False,
) -> None:
    """Sends the inline main menu. `clear_reply_keyboard` dismisses the legacy persistent
    reply keyboard that users from before this change still have pinned to their input bar —
    ReplyKeyboardRemove only takes effect when attached to a message, hence the extra send."""
    if clear_reply_keyboard:
        await message.answer("⁣", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        translator("menu.choose_action"),
        reply_markup=main_menu_inline_keyboard(translator, is_admin=is_admin),
    )


async def _about_text(translator: Callable[..., str]) -> str:
    return translator("about.text")


async def _contact_text(session: AsyncSession, translator: Callable[..., str]) -> str:
    settings_map = await setting_repository.get_all(session)
    return translator(
        "contact.text",
        phone=settings_map.get("shop_phone", "-"),
        username=settings_map.get("support_username", "-"),
        work_hours=settings_map.get("work_hours", "-"),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, admin: Admin | None, _: Callable) -> None:
    await send_main_menu(
        message,
        translator=_,
        is_admin=admin is not None and admin.is_active,
        clear_reply_keyboard=True,
    )


@router.callback_query(MenuCallback.filter())
async def on_menu_action(
    callback: CallbackQuery,
    callback_data: MenuCallback,
    session: AsyncSession,
    user: User,
    admin: Admin | None,
    state: FSMContext,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    # A menu tap is an explicit "start over" — drop any half-finished checkout/search FSM
    # so the chosen section is not swallowed by a state filter.
    await state.clear()
    await callback.answer()

    action = callback_data.action
    if action == "catalog":
        await send_category_level(
            message.answer, session, ROOT_CATEGORY_ID, lang=lang, translator=_
        )
    elif action == "cart":
        await render_cart(message.answer, session, user.id, lang=lang, translator=_)
    elif action == "orders":
        await render_orders(message.answer, session, user.id, translator=_)
    elif action == "favorites":
        await render_favorites(message.answer, session, user.id, lang=lang, translator=_)
    elif action == "about":
        await message.answer(await _about_text(_))
    elif action == "contact":
        await message.answer(await _contact_text(session, _))
    elif action == "settings":
        await message.answer(_("settings.text"), reply_markup=language_keyboard())
    elif action == "admin":
        from app.bot.handlers.admin.menu import render_admin_menu

        await render_admin_menu(message.answer, session, admin, translator=_)
    elif action == "menu":
        await send_main_menu(
            message, translator=_, is_admin=admin is not None and admin.is_active
        )


# --- Legacy reply-keyboard entry points -------------------------------------------------
# Kept so users who still have the old persistent keyboard on screen (Telegram caches it
# client-side until a ReplyKeyboardRemove arrives) do not hit a dead button.


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.about")))
async def show_about(message: Message, _: Callable) -> None:
    await message.answer(await _about_text(_))


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.contact")))
async def show_contact(message: Message, session: AsyncSession, _: Callable) -> None:
    await message.answer(await _contact_text(session, _))


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.settings")))
async def show_settings(message: Message, _: Callable) -> None:
    await message.answer(_("settings.text"), reply_markup=language_keyboard())
