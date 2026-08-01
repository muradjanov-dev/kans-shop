from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.products import render_product_detail
from app.bot.keyboards.callback_data import (
    AdminProductActionCallback,
    AdminProductFieldEditCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_products import admin_stock_menu_keyboard
from app.bot.states.admin_catalog import ProductEditStates, StockAdjustStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.product import Product
from app.db.repositories import product_repository

router = Router(name="admin_products_edit")


async def _get_product_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    product_id: int,
    translator: Callable[..., str],
) -> Product | None:
    product = await product_repository.get_by_id(session, product_id)
    if product is None:
        await callback.answer(translator("admin.product_not_found"), show_alert=True)
    return product


@router.callback_query(AdminProductFieldEditCallback.filter())
async def on_field_edit_start(
    callback: CallbackQuery,
    callback_data: AdminProductFieldEditCallback,
    session: AsyncSession,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    product = await _get_product_or_alert(callback, session, callback_data.product_id, _)
    if product is None:
        return

    await state.set_state(ProductEditStates.editing_field)
    await state.update_data(product_id=product.id, field=callback_data.field)
    field_label = _(f"admin.product_field_{callback_data.field}")
    await message.edit_text(
        f"{field_label}\n\n{_('admin.product_enter_new_value')}",
        reply_markup=cancel_only_keyboard(_),
    )
    await callback.answer()


@router.message(ProductEditStates.editing_field, F.text)
async def on_field_value_entered(
    message: Message, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    data = await state.get_data()
    field = data["field"]
    product = await product_repository.get_by_id(session, data["product_id"])
    if product is None:
        await state.clear()
        await message.answer(_("admin.product_not_found"))
        return

    raw = (message.text or "").strip()
    value: str | Decimal
    if field == "price":
        try:
            value = Decimal(raw.replace(" ", "").replace(",", "."))
            if value <= 0:
                raise InvalidOperation
        except InvalidOperation:
            await message.answer(
                _("admin.product_invalid_price"), reply_markup=cancel_only_keyboard(_)
            )
            return
    elif field == "sku":
        existing = await product_repository.get_by_sku(session, raw)
        if existing is not None and existing.id != product.id:
            await message.answer(
                _("admin.product_sku_exists"), reply_markup=cancel_only_keyboard(_)
            )
            return
        value = raw
    else:
        if not raw:
            return
        value = raw

    setattr(product, field, value)
    await session.flush()
    await state.clear()

    await message.answer(_("admin.product_updated"))
    await render_product_detail(message.answer, session, product, _)


@router.callback_query(AdminProductActionCallback.filter(F.action == "stock_menu"))
async def on_stock_menu(
    callback: CallbackQuery,
    callback_data: AdminProductActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    product = await _get_product_or_alert(callback, session, callback_data.product_id, _)
    if product is None:
        return
    await message.edit_text(
        _("admin.product_stock_label"),
        reply_markup=admin_stock_menu_keyboard(product, translator=_),
    )
    await callback.answer()


STOCK_DELTAS = {"stock_p10": 10, "stock_p50": 50, "stock_m1": -1}


@router.callback_query(AdminProductActionCallback.filter(F.action.in_(STOCK_DELTAS)))
async def on_stock_quick_adjust(
    callback: CallbackQuery,
    callback_data: AdminProductActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    product = await _get_product_or_alert(callback, session, callback_data.product_id, _)
    if product is None:
        return

    delta = STOCK_DELTAS[callback_data.action]
    delta = max(delta, -product.stock_qty)
    await product_repository.adjust_stock(session, product, delta)
    await render_product_detail(message.edit_text, session, product, _)
    await callback.answer(_("admin.product_stock_updated", value=product.stock_qty))


@router.callback_query(AdminProductActionCallback.filter(F.action == "stock_custom"))
async def on_stock_custom_start(
    callback: CallbackQuery,
    callback_data: AdminProductActionCallback,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(StockAdjustStates.entering_custom_amount)
    await state.update_data(product_id=callback_data.product_id)
    await message.edit_text(
        _("admin.product_stock_enter_custom"), reply_markup=cancel_only_keyboard(_)
    )
    await callback.answer()


@router.message(StockAdjustStates.entering_custom_amount, F.text)
async def on_stock_custom_entered(
    message: Message, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    raw = (message.text or "").strip()
    try:
        delta = int(raw)
    except ValueError:
        await message.answer(
            _("admin.product_invalid_stock"), reply_markup=cancel_only_keyboard(_)
        )
        return

    data = await state.get_data()
    product = await product_repository.get_by_id(session, data["product_id"])
    await state.clear()
    if product is None:
        await message.answer(_("admin.product_not_found"))
        return

    delta = max(delta, -product.stock_qty)
    await product_repository.adjust_stock(session, product, delta)
    await message.answer(_("admin.product_stock_updated", value=product.stock_qty))
    await render_product_detail(message.answer, session, product, _)
