from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline.language import language_keyboard
from app.bot.utils.i18n import menu_button_texts
from app.db.repositories import setting_repository

router = Router(name="menu")


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.about")))
async def show_about(message: Message, _: Callable) -> None:
    await message.answer(_("about.text"))


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.contact")))
async def show_contact(message: Message, session: AsyncSession, _: Callable) -> None:
    settings_map = await setting_repository.get_all(session)
    await message.answer(
        _(
            "contact.text",
            phone=settings_map.get("shop_phone", "-"),
            username=settings_map.get("support_username", "-"),
            work_hours=settings_map.get("work_hours", "-"),
        )
    )


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.settings")))
async def show_settings(message: Message, _: Callable) -> None:
    await message.answer(_("settings.text"), reply_markup=language_keyboard())
