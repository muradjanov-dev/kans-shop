from collections.abc import Callable

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.user.catalog import send_category_level, send_product_detail
from app.bot.keyboards.callback_data import (
    ROOT_CATEGORY_ID,
    CategoryCallback,
    LanguageCallback,
)
from app.bot.keyboards.inline.language import language_keyboard
from app.bot.keyboards.reply.main_menu import main_menu_keyboard
from app.bot.utils.i18n import translate
from app.db.models.user import User
from app.db.repositories import user_repository

router = Router(name="start")


async def _handle_deeplink(
    message: Message, session: AsyncSession, *, lang: str, translator: Callable, payload: str
) -> None:
    if payload.startswith("product_"):
        try:
            product_id = int(payload.removeprefix("product_"))
        except ValueError:
            return
        back = CategoryCallback(category_id=ROOT_CATEGORY_ID).pack()
        await send_product_detail(
            message.answer,
            session,
            product_id,
            back_callback_data=back,
            lang=lang,
            translator=translator,
        )
    elif payload.startswith("category_"):
        try:
            category_id = int(payload.removeprefix("category_"))
        except ValueError:
            return
        await send_category_level(
            message.answer, session, category_id, lang=lang, translator=translator
        )
    # ref_XXX (referral) deep links are parsed but intentionally not acted upon: no referral
    # feature/schema exists in docs/DB_SCHEMA.md for this build (see docs/ASSUMPTIONS.md).


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: User,
    is_new_user: bool,
    lang: str,
    _: Callable,
    state: FSMContext,
) -> None:
    if command.args:
        await state.update_data(deeplink=command.args)

    if is_new_user:
        await message.answer(_("start.choose_language"), reply_markup=language_keyboard())
        return

    await message.answer(
        _("start.welcome", name=user.first_name), reply_markup=main_menu_keyboard(_)
    )
    if command.args:
        await _handle_deeplink(message, session, lang=lang, translator=_, payload=command.args)


@router.callback_query(LanguageCallback.filter())
async def on_language_selected(
    callback: CallbackQuery,
    callback_data: LanguageCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await user_repository.set_language(session, user, callback_data.code)

    def translator(key: str, **kwargs: object) -> str:
        return translate(callback_data.code, key, **kwargs)

    message = callback.message
    if message is not None and not isinstance(message, InaccessibleMessage):
        await message.edit_text(translator("start.language_set"))
        await message.answer(
            translator("start.welcome", name=user.first_name),
            reply_markup=main_menu_keyboard(translator),
        )
    else:
        message = None

    data = await state.get_data()
    deeplink = data.get("deeplink")
    await state.clear()
    if deeplink and message is not None:
        await _handle_deeplink(
            message,
            session,
            lang=callback_data.code,
            translator=translator,
            payload=deeplink,
        )
    await callback.answer()
