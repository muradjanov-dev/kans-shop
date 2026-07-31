from collections.abc import Awaitable, Callable
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import FavoriteRemoveCallback
from app.bot.keyboards.inline.favorites import favorites_keyboard
from app.bot.utils.i18n import menu_button_texts
from app.bot.utils.messages import require_message
from app.db.models.user import User
from app.db.repositories import favorite_repository

router = Router(name="favorites")

Sender = Callable[..., Awaitable[object]]


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


async def render_favorites(
    send: Sender,
    session: AsyncSession,
    user_id: int,
    *,
    lang: str,
    translator: Callable[..., str],
) -> None:
    favorites = await favorite_repository.list_by_user(session, user_id)
    if not favorites:
        await send(translator("favorites.empty"))
        return
    lines = [translator("favorites.title"), ""]
    for fav in favorites:
        name = fav.product.name_uz if lang == "uz" else fav.product.name_ru
        lines.append(f"{name} — {_format_price(fav.product.price)}")
    await send(
        "\n".join(lines),
        reply_markup=favorites_keyboard(favorites, lang=lang, translator=translator),
    )


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.favorites")))
async def open_favorites(
    message: Message, session: AsyncSession, user: User, lang: str, _: Callable
) -> None:
    await render_favorites(message.answer, session, user.id, lang=lang, translator=_)


@router.callback_query(FavoriteRemoveCallback.filter())
async def on_favorite_remove(
    callback: CallbackQuery,
    callback_data: FavoriteRemoveCallback,
    session: AsyncSession,
    user: User,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await favorite_repository.remove(session, user.id, callback_data.product_id)
    await render_favorites(edit, session, user.id, lang=lang, translator=_)
    await callback.answer(_("favorites.removed"))
