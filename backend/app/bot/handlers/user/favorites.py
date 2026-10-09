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
from app.services import favorite_service

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
    page = await favorite_service.list_favorites(session, user_id)
    products = list(page.items)
    for page_number in range(2, page.total_pages + 1):
        next_page = await favorite_service.list_favorites(
            session, user_id, page=page_number, limit=page.limit
        )
        products.extend(next_page.items)
    if not products:
        await send(translator("favorites.empty"))
        return
    lines = [translator("favorites.title"), ""]
    for product in products:
        name = product.name_uz if lang == "uz" else product.name_ru
        lines.append(f"{name} — {_format_price(product.price)}")
    await send(
        "\n".join(lines),
        reply_markup=favorites_keyboard(products, lang=lang, translator=translator),
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

    await favorite_service.remove_favorite(session, user.id, callback_data.product_id)
    await render_favorites(edit, session, user.id, lang=lang, translator=_)
    await callback.answer(_("favorites.removed"))
