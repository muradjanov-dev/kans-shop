from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.utils.admin_order_card import build_admin_order_keyboard, build_admin_order_text
from app.bot.utils.i18n import translate
from app.db.models.admin import Admin
from app.db.models.enums import OrderStatus, OrderType, PaymentMethod
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.services import cart_service, order_service

translator = partial(translate, "uz")


async def _make_order(
    session: AsyncSession, user: User, product: Product, **overrides
) -> Order:
    await setting_repository.set_value(session, "min_order_amount", 0)
    await cart_service.add_item(session, user.id, product.id, quantity=2)
    kwargs = dict(
        user_id=user.id,
        order_type=OrderType.DELIVERY,
        customer_name="Test Customer",
        customer_phone="+998901234567",
        address="Chilonzor 9",
    )
    kwargs.update(overrides)
    return await order_service.checkout(session, **kwargs)


def _flatten_callback_data(markup) -> list[str]:
    return [
        btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data
    ]


async def test_order_text_includes_key_fields(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    order = await _make_order(db_session, user, product)

    text = build_admin_order_text(order, user, translator=translator)

    assert order.order_number in text
    assert "Test Customer" in text
    assert "+998901234567" in text
    assert "Chilonzor 9" in text
    assert product.name_uz in text


async def test_order_text_shows_no_username_placeholder_when_missing(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    user.username = None
    order = await _make_order(db_session, user, product)

    text = build_admin_order_text(order, user, translator=translator)

    assert translator("admin.no_username") in text


async def test_keyboard_new_status_has_confirm_and_cancel(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    order = await _make_order(db_session, user, product)

    keyboard = build_admin_order_keyboard(order, translator=translator)

    packed = _flatten_callback_data(keyboard)
    assert any(cb.startswith("aconf:") for cb in packed)
    assert any(cb.startswith("acreq:") for cb in packed)


async def test_keyboard_preparing_pickup_shows_completed_not_delivering(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    order = await _make_order(
        db_session, user, product, order_type=OrderType.PICKUP, address=None
    )
    order = await order_service.confirm_order(db_session, order, admin_id=admin.id)
    order = await order_service.advance_status(
        db_session, order, OrderStatus.PREPARING, admin_id=admin.id
    )

    keyboard = build_admin_order_keyboard(order, translator=translator)

    packed = _flatten_callback_data(keyboard)
    assert f"aadv:{order.id}:completed" in packed
    assert f"aadv:{order.id}:delivering" not in packed


async def test_keyboard_preparing_delivery_shows_delivering(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    order = await _make_order(db_session, user, product)
    order = await order_service.confirm_order(db_session, order, admin_id=admin.id)
    order = await order_service.advance_status(
        db_session, order, OrderStatus.PREPARING, admin_id=admin.id
    )

    keyboard = build_admin_order_keyboard(order, translator=translator)

    packed = _flatten_callback_data(keyboard)
    assert f"aadv:{order.id}:delivering" in packed


async def test_keyboard_shows_receipt_button_only_for_card_with_receipt(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    order_no_receipt = await _make_order(db_session, user, product)
    keyboard = build_admin_order_keyboard(order_no_receipt, translator=translator)
    assert not any(cb.startswith("arcpt:") for cb in _flatten_callback_data(keyboard))

    order_with_card = await _make_order(
        db_session, user, product, payment_method=PaymentMethod.CARD_TRANSFER
    )
    order_with_card = await order_service.attach_receipt(
        db_session, order_with_card, file_id="AgAD1234", url="http://x/receipts/1.jpg"
    )
    keyboard_with_receipt = build_admin_order_keyboard(order_with_card, translator=translator)
    assert any(cb.startswith("arcpt:") for cb in _flatten_callback_data(keyboard_with_receipt))


async def test_keyboard_terminal_status_has_no_action_buttons(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    order = await _make_order(
        db_session, user, product, order_type=OrderType.PICKUP, address=None
    )
    order = await order_service.confirm_order(db_session, order, admin_id=admin.id)
    order = await order_service.advance_status(
        db_session, order, OrderStatus.PREPARING, admin_id=admin.id
    )
    order = await order_service.advance_status(
        db_session, order, OrderStatus.COMPLETED, admin_id=admin.id
    )

    keyboard = build_admin_order_keyboard(order, translator=translator)

    packed = _flatten_callback_data(keyboard)
    assert not any(cb.startswith(("aconf:", "aadv:", "acreq:")) for cb in packed)
    assert any(cb.startswith("amsg:") for cb in packed)
