from collections.abc import Awaitable, Callable
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import CartActionCallback, CartItemQtyCallback
from app.bot.keyboards.inline.cart import cart_clear_confirm_keyboard, cart_keyboard
from app.bot.utils.i18n import menu_button_texts
from app.bot.utils.messages import require_message
from app.core.exceptions import OutOfStockError
from app.db.models.cart import Cart
from app.db.models.user import User
from app.services import cart_service

router = Router(name="cart")

Sender = Callable[..., Awaitable[object]]


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def _cart_text(cart: Cart, *, lang: str, translator: Callable[..., str]) -> str:
    if not cart.items:
        return translator("cart.empty")
    lines = [translator("cart.title"), ""]
    for item in cart.items:
        name = item.product.name_uz if lang == "uz" else item.product.name_ru
        subtotal = item.product.price * item.quantity
        lines.append(
            translator(
                "cart.item_line",
                name=name,
                qty=item.quantity,
                price=_format_price(item.product.price),
                subtotal=_format_price(subtotal),
            )
        )
    total = cart_service.calculate_subtotal(cart)
    lines.append(translator("cart.total", total=_format_price(total)))
    return "\n".join(lines)


async def render_cart(
    send: Sender,
    session: AsyncSession,
    user_id: int,
    *,
    lang: str,
    translator: Callable[..., str],
) -> Cart:
    cart = await cart_service.get_cart(session, user_id)
    await send(
        _cart_text(cart, lang=lang, translator=translator),
        reply_markup=cart_keyboard(cart.items, lang=lang, translator=translator),
    )
    return cart


@router.message(StateFilter(None), F.text.in_(menu_button_texts("menu.cart")))
async def open_cart(
    message: Message, session: AsyncSession, user: User, lang: str, _: Callable
) -> None:
    await render_cart(message.answer, session, user.id, lang=lang, translator=_)


@router.callback_query(CartItemQtyCallback.filter())
async def on_cart_item_action(
    callback: CallbackQuery,
    callback_data: CartItemQtyCallback,
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

    if callback_data.action == "remove":
        await cart_service.remove_item(session, user.id, callback_data.product_id)
    else:
        cart = await cart_service.get_cart(session, user.id)
        item = next((i for i in cart.items if i.product_id == callback_data.product_id), None)
        current_qty = item.quantity if item else 0
        delta = 1 if callback_data.action == "inc" else -1
        try:
            await cart_service.update_item_quantity(
                session, user.id, callback_data.product_id, current_qty + delta
            )
        except OutOfStockError:
            await callback.answer(_("cart.out_of_stock_alert"), show_alert=True)
            return

    await render_cart(edit, session, user.id, lang=lang, translator=_)
    await callback.answer()


@router.callback_query(CartActionCallback.filter(F.action == "clear"))
async def on_cart_clear_request(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    cart = await cart_service.get_cart(session, user.id)
    if not cart.items:
        await callback.answer()
        return
    await message.edit_text(
        _("cart.clear_confirm"), reply_markup=cart_clear_confirm_keyboard(_)
    )
    await callback.answer()


@router.callback_query(CartActionCallback.filter(F.action == "clear_confirm"))
async def on_cart_clear_confirm(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await cart_service.clear_cart(session, user.id)
    await render_cart(edit, session, user.id, lang=lang, translator=_)
    await callback.answer(_("cart.cleared"))


@router.callback_query(CartActionCallback.filter(F.action == "clear_cancel"))
async def on_cart_clear_cancel(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await render_cart(edit, session, user.id, lang=lang, translator=_)
    await callback.answer()
