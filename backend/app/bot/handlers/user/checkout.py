from collections.abc import Callable
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    CartActionCallback,
    CheckoutNavCallback,
    OrderTypeCallback,
    PaymentMethodCallback,
    SkipStepCallback,
    UseDefaultNameCallback,
)
from app.bot.keyboards.inline.checkout import (
    address_comment_step_keyboard,
    back_cancel_keyboard,
    comment_step_keyboard,
    confirm_keyboard,
    name_step_keyboard,
    order_type_keyboard,
    payment_method_keyboard,
)
from app.bot.keyboards.inline.main_menu import main_menu_inline_keyboard
from app.bot.keyboards.reply.checkout import location_request_keyboard, phone_request_keyboard
from app.bot.services.order_notifications import notify_admins_new_order
from app.bot.states.checkout import CheckoutStates
from app.bot.utils.helpers import is_valid_uz_phone, normalize_uz_phone
from app.bot.utils.messages import require_message
from app.core.config import settings
from app.core.exceptions import (
    CartEmptyError,
    MinOrderAmountError,
    OutOfStockError,
    PaymentNotConfiguredError,
)
from app.core.uploads import ALLOWED_RECEIPT_MIME_TYPES, MAX_RECEIPT_SIZE_BYTES
from app.db.models.enums import OrderType, PaymentMethod, PaymentProvider
from app.db.models.order import Order
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.services import cart_service, order_service, payment_service

router = Router(name="checkout")

PAYMENT_LABEL_KEYS = {
    PaymentMethod.CASH.value: "checkout.payment_cash",
    PaymentMethod.CARD_TRANSFER.value: "checkout.payment_card",
    PaymentMethod.CLICK.value: "checkout.payment_click",
    PaymentMethod.PAYME.value: "checkout.payment_payme",
    PaymentMethod.PAYNET.value: "checkout.payment_paynet",
    PaymentMethod.TENDER.value: "checkout.payment_tender",
}

ONLINE_PAYMENT_METHODS = {
    PaymentMethod.CLICK.value: PaymentProvider.CLICK,
    PaymentMethod.PAYME.value: PaymentProvider.PAYME,
    PaymentMethod.PAYNET.value: PaymentProvider.PAYNET,
}


async def _tender_available(session: AsyncSession, user_id: int) -> bool:
    cart = await cart_service.get_cart(session, user_id)
    return any(item.product.lot_url for item in cart.items)


def _enabled_online_providers() -> set[str]:
    return {
        method
        for method, provider in ONLINE_PAYMENT_METHODS.items()
        if payment_service.is_provider_configured(provider)
    }


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def _default_name(user: User) -> str:
    parts = [user.first_name, user.last_name]
    return " ".join(p for p in parts if p)


def _pay_link_keyboard(url: str, *, translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=translator("checkout.pay_button"), url=url))
    return builder.as_markup()


def _lot_links_keyboard(links: list[order_service.LotLink]) -> InlineKeyboardMarkup:
    """One button per ordered product, each opening that product's tender lot page."""
    builder = InlineKeyboardBuilder()
    for link in links:
        builder.row(InlineKeyboardButton(text=f"📄 {link.product_name}"[:64], url=link.url))
    return builder.as_markup()


async def _send_lot_links(
    message: Message,
    session: AsyncSession,
    order: Order,
    *,
    translator: Callable[..., str],
) -> None:
    links, missing = await order_service.lot_links(session, order)
    if links:
        await message.answer(
            translator("checkout.lot_links_intro"), reply_markup=_lot_links_keyboard(links)
        )
    if missing:
        await message.answer(
            translator("checkout.lot_links_missing", products=", ".join(missing))
        )


def _contact_manager_keyboard(
    support_username: str, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("checkout.contact_manager_button"),
            url=f"https://t.me/{support_username.lstrip('@')}",
        )
    )
    return builder.as_markup()


async def _cancel_checkout(
    message: Message, state: FSMContext, translator: Callable[..., str]
) -> None:
    await state.clear()
    await message.answer(translator("checkout.cancelled"), reply_markup=ReplyKeyboardRemove())
    await message.answer(
        translator("menu.choose_action"),
        reply_markup=main_menu_inline_keyboard(translator),
    )


async def _build_summary(
    session: AsyncSession, data: dict, *, lang: str, translator: Callable[..., str]
) -> tuple[str, Decimal, Decimal, Decimal]:
    cart = await cart_service.get_cart(session, data["user_id"])
    subtotal = cart_service.calculate_subtotal(cart)
    order_type = OrderType(data["order_type"])
    delivery_fee = await order_service.calculate_delivery_fee(session, order_type, subtotal)
    total = subtotal + delivery_fee

    lines = [translator("checkout.summary_title"), ""]
    lines.append(
        translator(
            "checkout.summary_type", value=translator(f"checkout.type_{order_type.value}")
        )
    )
    lines.append(translator("checkout.summary_name", value=data["name"]))
    lines.append(translator("checkout.summary_phone", value=data["phone"]))
    if data.get("address"):
        lines.append(translator("checkout.summary_address", value=data["address"]))
    elif data.get("latitude") is not None:
        lines.append(translator("checkout.summary_address", value="📍"))
    if data.get("comment"):
        lines.append(translator("checkout.summary_comment", value=data["comment"]))
    if data.get("payment_method"):
        pay_label = translator(PAYMENT_LABEL_KEYS[data["payment_method"]])
        lines.append(translator("checkout.summary_payment", value=pay_label))

    lines.append("")
    lines.append(translator("checkout.summary_items_header"))
    for idx, item in enumerate(cart.items, start=1):
        name = item.product.name_uz if lang == "uz" else item.product.name_ru
        item_subtotal = item.product.price * item.quantity
        lines.append(
            translator(
                "checkout.summary_item_line",
                index=idx,
                name=name,
                price=_format_price(item.product.price),
                qty=item.quantity,
                subtotal=_format_price(item_subtotal),
            )
        )

    lines.append("")
    lines.append(translator("checkout.summary_subtotal", value=_format_price(subtotal)))
    if order_type == OrderType.DELIVERY:
        lines.append(
            translator("checkout.summary_delivery", value=_format_price(delivery_fee))
        )
    lines.append(translator("checkout.summary_total", value=_format_price(total)))
    if order_type == OrderType.PREORDER:
        lines.append(translator("checkout.preorder_note"))

    return "\n".join(lines), subtotal, delivery_fee, total


def _build_order_summary(order, *, translator: Callable[..., str]) -> str:
    """Post-checkout summary sourced from the persisted Order/OrderItem snapshots rather than
    the cart, since order_service.checkout() has already cleared the cart by this point."""
    lines = [translator("checkout.summary_title"), ""]
    lines.append(
        translator(
            "checkout.summary_type",
            value=translator(f"checkout.type_{order.order_type.value}"),
        )
    )
    lines.append(translator("checkout.summary_name", value=order.customer_name))
    lines.append(translator("checkout.summary_phone", value=order.customer_phone))
    if order.address:
        lines.append(translator("checkout.summary_address", value=order.address))
    elif order.latitude is not None:
        lines.append(translator("checkout.summary_address", value="📍"))
    if order.comment:
        lines.append(translator("checkout.summary_comment", value=order.comment))
    pay_label = translator(PAYMENT_LABEL_KEYS[order.payment_method.value])
    lines.append(translator("checkout.summary_payment", value=pay_label))

    lines.append("")
    lines.append(translator("checkout.summary_items_header"))
    for idx, item in enumerate(order.items, start=1):
        lines.append(
            translator(
                "checkout.summary_item_line",
                index=idx,
                name=item.product_name_snapshot,
                price=_format_price(item.price),
                qty=item.quantity,
                subtotal=_format_price(item.total),
            )
        )

    lines.append("")
    lines.append(translator("checkout.summary_subtotal", value=_format_price(order.subtotal)))
    if order.order_type == OrderType.DELIVERY:
        lines.append(
            translator("checkout.summary_delivery", value=_format_price(order.delivery_fee))
        )
    lines.append(translator("checkout.summary_total", value=_format_price(order.total)))
    if order.order_type == OrderType.PREORDER:
        lines.append(translator("checkout.preorder_note"))

    return "\n".join(lines)


# --- Entry point ---


@router.callback_query(CartActionCallback.filter(F.action == "checkout"))
async def start_checkout(
    callback: CallbackQuery, session: AsyncSession, user: User, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    cart = await cart_service.get_cart(session, user.id)
    if not cart.items:
        await callback.answer(_("checkout.cart_empty"), show_alert=True)
        return

    await state.set_state(CheckoutStates.choosing_type)
    await state.update_data(user_id=user.id)
    await message.answer(_("checkout.choose_type"), reply_markup=order_type_keyboard(_))
    await callback.answer()


# --- Step: order type ---


@router.callback_query(CheckoutStates.choosing_type, OrderTypeCallback.filter())
async def on_order_type_chosen(
    callback: CallbackQuery,
    callback_data: OrderTypeCallback,
    state: FSMContext,
    user: User,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(order_type=callback_data.value)
    await state.set_state(CheckoutStates.entering_name)
    await message.answer(
        _("checkout.enter_name"), reply_markup=name_step_keyboard(_, _default_name(user))
    )
    await callback.answer()


@router.callback_query(
    CheckoutStates.entering_name, CheckoutNavCallback.filter(F.action == "back")
)
async def on_name_back(callback: CallbackQuery, state: FSMContext, _: Callable) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(CheckoutStates.choosing_type)
    await message.answer(_("checkout.choose_type"), reply_markup=order_type_keyboard(_))
    await callback.answer()


# --- Step: name ---


async def _advance_to_phone(message: Message, state: FSMContext, _: Callable) -> None:
    await state.set_state(CheckoutStates.entering_phone)
    await message.answer(_("checkout.enter_phone"), reply_markup=phone_request_keyboard(_))


@router.callback_query(CheckoutStates.entering_name, UseDefaultNameCallback.filter())
async def on_use_default_name(
    callback: CallbackQuery, state: FSMContext, user: User, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(name=_default_name(user))
    await _advance_to_phone(message, state, _)
    await callback.answer()


@router.message(CheckoutStates.entering_name, F.text)
async def on_name_entered(message: Message, state: FSMContext, _: Callable) -> None:
    name = (message.text or "").strip()
    if not name:
        return
    await state.update_data(name=name)
    await _advance_to_phone(message, state, _)


# --- Step: phone ---


async def _advance_from_phone(message: Message, state: FSMContext, _: Callable) -> None:
    data = await state.get_data()
    if data.get("order_type") == OrderType.DELIVERY.value:
        await state.set_state(CheckoutStates.entering_address)
        await message.answer(
            _("checkout.enter_address"),
            reply_markup=location_request_keyboard(_),
        )
    else:
        await state.set_state(CheckoutStates.entering_comment)
        await message.answer("✅", reply_markup=ReplyKeyboardRemove())
        await message.answer(
            _("checkout.enter_comment"), reply_markup=comment_step_keyboard(_, show_back=False)
        )


async def _submit_phone(message: Message, state: FSMContext, raw: str, _: Callable) -> None:
    normalized = normalize_uz_phone(raw)
    if not is_valid_uz_phone(normalized):
        await message.answer(
            _("checkout.invalid_phone"), reply_markup=phone_request_keyboard(_)
        )
        return
    await state.update_data(phone=normalized)
    await _advance_from_phone(message, state, _)


@router.message(CheckoutStates.entering_phone, F.contact)
async def on_phone_contact(message: Message, state: FSMContext, _: Callable) -> None:
    if message.contact is None:
        return
    await _submit_phone(message, state, message.contact.phone_number, _)


@router.message(CheckoutStates.entering_phone, F.text)
async def on_phone_text(message: Message, state: FSMContext, _: Callable) -> None:
    text = (message.text or "").strip()
    if text == _("checkout.cancel_button"):
        await _cancel_checkout(message, state, _)
        return
    if not text:
        return
    await _submit_phone(message, state, text, _)


# --- Step: address (delivery only) ---


@router.message(CheckoutStates.entering_address, F.location)
async def on_address_location(message: Message, state: FSMContext, _: Callable) -> None:
    if message.location is None:
        return
    await state.update_data(
        address=None, latitude=message.location.latitude, longitude=message.location.longitude
    )
    await state.set_state(CheckoutStates.entering_address_comment)
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        _("checkout.enter_address_comment"), reply_markup=address_comment_step_keyboard(_)
    )


@router.message(CheckoutStates.entering_address, F.text)
async def on_address_text(message: Message, state: FSMContext, _: Callable) -> None:
    text = (message.text or "").strip()
    if text == _("checkout.cancel_button"):
        await _cancel_checkout(message, state, _)
        return
    if not text:
        return
    await state.update_data(address=text, latitude=None, longitude=None)
    await state.set_state(CheckoutStates.entering_address_comment)
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        _("checkout.enter_address_comment"), reply_markup=address_comment_step_keyboard(_)
    )


async def _advance_to_comment(message: Message, state: FSMContext, _: Callable) -> None:
    await state.set_state(CheckoutStates.entering_comment)
    await message.answer(
        _("checkout.enter_comment"), reply_markup=comment_step_keyboard(_, show_back=True)
    )


@router.message(CheckoutStates.entering_address_comment, F.text)
async def on_address_comment_entered(message: Message, state: FSMContext, _: Callable) -> None:
    await state.update_data(address_comment=(message.text or "").strip() or None)
    await _advance_to_comment(message, state, _)


@router.callback_query(
    CheckoutStates.entering_address_comment,
    SkipStepCallback.filter(F.step == "address_comment"),
)
async def on_address_comment_skip(
    callback: CallbackQuery, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(address_comment=None)
    await _advance_to_comment(message, state, _)
    await callback.answer()


@router.callback_query(
    CheckoutStates.entering_address_comment, CheckoutNavCallback.filter(F.action == "back")
)
async def on_address_comment_back(
    callback: CallbackQuery, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(CheckoutStates.entering_address)
    await message.answer(
        _("checkout.enter_address"), reply_markup=location_request_keyboard(_)
    )
    await callback.answer()


# --- Step: comment ---


async def _advance_from_comment(
    message: Message, session: AsyncSession, state: FSMContext, *, lang: str, _: Callable
) -> None:
    data = await state.get_data()
    if data.get("order_type") == OrderType.PREORDER.value:
        await _show_confirmation(message, session, state, lang=lang, _=_)
        return
    await state.set_state(CheckoutStates.choosing_payment)
    await message.answer(
        _("checkout.choose_payment"),
        reply_markup=payment_method_keyboard(
            _,
            enabled_providers=_enabled_online_providers(),
            tender_available=True,
        ),
    )


@router.message(CheckoutStates.entering_comment, F.text)
async def on_comment_entered(
    message: Message, session: AsyncSession, state: FSMContext, lang: str, _: Callable
) -> None:
    await state.update_data(comment=(message.text or "").strip() or None)
    await _advance_from_comment(message, session, state, lang=lang, _=_)


@router.callback_query(
    CheckoutStates.entering_comment, SkipStepCallback.filter(F.step == "comment")
)
async def on_comment_skip(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(comment=None)
    await _advance_from_comment(message, session, state, lang=lang, _=_)
    await callback.answer()


@router.callback_query(
    CheckoutStates.entering_comment, CheckoutNavCallback.filter(F.action == "back")
)
async def on_comment_back(callback: CallbackQuery, state: FSMContext, _: Callable) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    data = await state.get_data()
    if data.get("order_type") == OrderType.DELIVERY.value:
        await state.set_state(CheckoutStates.entering_address_comment)
        await message.answer(
            _("checkout.enter_address_comment"), reply_markup=address_comment_step_keyboard(_)
        )
    await callback.answer()


# --- Step: payment method ---


@router.callback_query(CheckoutStates.choosing_payment, PaymentMethodCallback.filter())
async def on_payment_method_chosen(
    callback: CallbackQuery,
    callback_data: PaymentMethodCallback,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(payment_method=callback_data.value)

    if callback_data.value in ONLINE_PAYMENT_METHODS:
        await _show_confirmation(message, session, state, lang=lang, _=_)
    elif callback_data.value == PaymentMethod.CARD_TRANSFER.value:
        settings_map = await setting_repository.get_all(session)
        data = await state.get_data()
        cart = await cart_service.get_cart(session, data["user_id"])
        subtotal = cart_service.calculate_subtotal(cart)
        delivery_fee = await order_service.calculate_delivery_fee(
            session, OrderType(data["order_type"]), subtotal
        )
        await state.set_state(CheckoutStates.uploading_receipt)
        await message.answer(
            _(
                "checkout.card_details",
                card_number=settings_map.get("card_number", "-"),
                card_holder=settings_map.get("card_holder", "-"),
                total=_format_price(subtotal + delivery_fee),
            ),
            reply_markup=back_cancel_keyboard(_),
        )
    else:
        await _show_confirmation(message, session, state, lang=lang, _=_)
    await callback.answer()


@router.callback_query(
    CheckoutStates.choosing_payment, CheckoutNavCallback.filter(F.action == "back")
)
async def on_payment_back(callback: CallbackQuery, state: FSMContext, _: Callable) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(CheckoutStates.entering_comment)
    await message.answer(
        _("checkout.enter_comment"), reply_markup=comment_step_keyboard(_, show_back=True)
    )
    await callback.answer()


# --- Step: receipt upload ---


@router.message(CheckoutStates.uploading_receipt, F.photo)
async def on_receipt_photo(
    message: Message, session: AsyncSession, state: FSMContext, lang: str, _: Callable
) -> None:
    if not message.photo:
        return
    file_id = message.photo[-1].file_id
    await state.update_data(receipt_file_id=file_id, receipt_is_document=False)
    await _show_confirmation(message, session, state, lang=lang, _=_)


@router.message(CheckoutStates.uploading_receipt, F.document)
async def on_receipt_document(
    message: Message, session: AsyncSession, state: FSMContext, lang: str, _: Callable
) -> None:
    doc = message.document
    if doc is None:
        return
    if doc.mime_type not in ALLOWED_RECEIPT_MIME_TYPES:
        await message.answer(
            _("checkout.receipt_bad_type"), reply_markup=back_cancel_keyboard(_)
        )
        return
    if doc.file_size and doc.file_size > MAX_RECEIPT_SIZE_BYTES:
        await message.answer(
            _("checkout.receipt_too_large"), reply_markup=back_cancel_keyboard(_)
        )
        return
    await state.update_data(receipt_file_id=doc.file_id, receipt_is_document=True)
    await _show_confirmation(message, session, state, lang=lang, _=_)


@router.callback_query(
    CheckoutStates.uploading_receipt, CheckoutNavCallback.filter(F.action == "back")
)
async def on_receipt_back(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(CheckoutStates.choosing_payment)
    await message.answer(
        _("checkout.choose_payment"),
        reply_markup=payment_method_keyboard(
            _,
            enabled_providers=_enabled_online_providers(),
            tender_available=True,
        ),
    )
    await callback.answer()


@router.message(CheckoutStates.uploading_receipt)
async def on_receipt_invalid(message: Message, _: Callable) -> None:
    await message.answer(_("checkout.invalid_receipt"), reply_markup=back_cancel_keyboard(_))


# --- Step: confirmation ---


async def _show_confirmation(
    message: Message, session: AsyncSession, state: FSMContext, *, lang: str, _: Callable
) -> None:
    await state.set_state(CheckoutStates.confirming)
    data = await state.get_data()
    summary, _subtotal, _fee, _total = await _build_summary(
        session, data, lang=lang, translator=_
    )
    await message.answer(summary, reply_markup=confirm_keyboard(_))


@router.callback_query(
    CheckoutStates.confirming, CheckoutNavCallback.filter(F.action == "confirm")
)
async def on_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    bot: Bot,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    data = await state.get_data()
    try:
        order = await order_service.checkout(
            session,
            user_id=user.id,
            order_type=OrderType(data["order_type"]),
            customer_name=data["name"],
            customer_phone=data["phone"],
            payment_method=PaymentMethod(data.get("payment_method", PaymentMethod.CASH.value)),
            address=data.get("address"),
            address_comment=data.get("address_comment"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            comment=data.get("comment"),
            source="bot",
            lang=lang,
        )
    except CartEmptyError:
        await callback.answer(_("checkout.cart_empty"), show_alert=True)
        await state.clear()
        return
    except MinOrderAmountError as exc:
        await callback.answer(
            _(
                "checkout.min_order_amount_error",
                min_amount=exc.details.get("min_amount", "-"),
                subtotal=exc.details.get("subtotal", "-"),
            ),
            show_alert=True,
        )
        return
    except OutOfStockError:
        await callback.answer(_("checkout.out_of_stock_error"), show_alert=True)
        return

    receipt_file_id = data.get("receipt_file_id")
    if receipt_file_id:
        receipt_url = await _persist_receipt(
            bot, order.id, receipt_file_id, data.get("receipt_is_document", False)
        )
        await order_service.attach_receipt(
            session, order, file_id=receipt_file_id, url=receipt_url
        )

    await notify_admins_new_order(bot, session, order)

    summary = _build_order_summary(order, translator=_)
    await state.clear()
    await message.answer(
        _("checkout.success", order_number=order.order_number, summary=summary),
        reply_markup=ReplyKeyboardRemove(),
    )

    if order.payment_method == PaymentMethod.TENDER:
        await _send_lot_links(message, session, order, translator=_)

    online_provider = ONLINE_PAYMENT_METHODS.get(order.payment_method.value)
    if online_provider is not None:
        try:
            pay_url = payment_service.build_pay_url(order, online_provider)
        except PaymentNotConfiguredError:
            pay_url = None
        if pay_url:
            await message.answer(
                _("checkout.pay_now"), reply_markup=_pay_link_keyboard(pay_url, translator=_)
            )

    support_username = await setting_repository.get_value(session, "support_username", None)
    if support_username:
        await message.answer(
            _("checkout.contact_manager_button"),
            reply_markup=_contact_manager_keyboard(support_username, translator=_),
        )
    await message.answer(_("menu.choose_action"), reply_markup=main_menu_inline_keyboard(_))
    await callback.answer()


async def _persist_receipt(bot: Bot, order_id: int, file_id: str, is_document: bool) -> str:
    receipts_dir = settings.media_root_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    ext = "pdf" if is_document else "jpg"
    destination = receipts_dir / f"{order_id}.{ext}"
    await bot.download(file_id, destination=destination)
    return f"{settings.media_base_url}/receipts/{destination.name}"


@router.callback_query(
    CheckoutStates.confirming, CheckoutNavCallback.filter(F.action == "edit")
)
async def on_edit(callback: CallbackQuery, state: FSMContext, user: User, _: Callable) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(CheckoutStates.choosing_type)
    await state.update_data(user_id=user.id)
    await message.answer(_("checkout.choose_type"), reply_markup=order_type_keyboard(_))
    await callback.answer()


@router.callback_query(CheckoutNavCallback.filter(F.action == "cancel"))
async def on_cancel(callback: CallbackQuery, state: FSMContext, _: Callable) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await _cancel_checkout(message, state, _)
    await callback.answer()
