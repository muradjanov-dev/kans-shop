from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import ProductUpdateIn
from app.bot.handlers.admin.products import render_product_detail
from app.bot.handlers.admin.products_form import persist_product_images
from app.bot.keyboards.callback_data import (
    AdminImagesFinishCallback,
    AdminProductActionCallback,
    AdminProductFieldEditCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_products import (
    admin_stock_menu_keyboard,
    images_upload_keyboard,
)
from app.bot.states.admin_catalog import ProductEditStates, StockAdjustStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.core.exceptions import CatalogEditConflictError, SkuAlreadyExistsError
from app.db.models.admin import Admin
from app.db.models.product import Product
from app.db.repositories import product_repository
from app.services import admin_catalog_service

router = Router(name="admin_products_edit")


async def _get_product_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    product_id: int,
    translator: Callable[..., str],
    *,
    for_update: bool = False,
) -> Product | None:
    product = await product_repository.get_by_id(session, product_id, for_update=for_update)
    if product is None:
        await callback.answer(translator("admin.product_not_found"), show_alert=True)
    elif for_update:
        await session.refresh(product, attribute_names=["images"])
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
    await state.update_data(
        product_id=product.id,
        field=callback_data.field,
        edit_version=product.edit_version,
    )
    field_label = _(f"admin.product_field_{callback_data.field}")
    await message.edit_text(
        f"{field_label}\n\n{_('admin.product_enter_new_value')}",
        reply_markup=cancel_only_keyboard(_),
    )
    await callback.answer()


@router.message(ProductEditStates.editing_field, F.text)
async def on_field_value_entered(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(message, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    data = await state.get_data()
    field = data["field"]
    product = await product_repository.get_by_id(session, data["product_id"])
    if product is None:
        await state.clear()
        await message.answer(_("admin.product_not_found"))
        return

    raw = (message.text or "").strip()
    value: str | Decimal | None
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
    elif field == "lot_url":
        # "-" clears the link, so a product can be pulled out of tender checkout again.
        if raw == "-":
            value = None
        else:
            parsed = urlsplit(raw)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or len(raw) > 512
            ):
                await message.answer(
                    _("admin.product_invalid_url"), reply_markup=cancel_only_keyboard(_)
                )
                return
            value = raw
    elif field == "sku":
        if not raw or len(raw) > 64:
            await message.answer(
                _("admin.product_invalid_sku"), reply_markup=cancel_only_keyboard(_)
            )
            return
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

    assert admin is not None
    try:
        product = await admin_catalog_service.update_product(
            session,
            admin_id=admin.id,
            product_id=product.id,
            expected_edit_version=data["edit_version"],
            changes=ProductUpdateIn(
                expected_edit_version=data["edit_version"], **{field: value}
            ),
        )
    except CatalogEditConflictError:
        await state.clear()
        await message.answer(_("admin.catalog_edit_conflict"))
        return
    except SkuAlreadyExistsError:
        await message.answer(
            _("admin.product_sku_exists"), reply_markup=cancel_only_keyboard(_)
        )
        return
    await state.clear()

    await message.answer(_("admin.product_updated"))
    await render_product_detail(message.answer, session, product, _)


@router.callback_query(AdminProductActionCallback.filter(F.action == "manage_images"))
async def on_manage_images_start(
    callback: CallbackQuery,
    callback_data: AdminProductActionCallback,
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

    await state.set_state(ProductEditStates.uploading_images)
    await state.update_data(product_id=product.id)
    await message.edit_text(
        _("admin.product_images_current", count=len(product.images)),
        reply_markup=images_upload_keyboard(_),
    )
    await callback.answer()


@router.message(ProductEditStates.uploading_images, F.photo)
async def on_edit_image_uploaded(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(message, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    if not message.photo:
        return
    data = await state.get_data()
    product = await product_repository.get_by_id(session, data["product_id"])
    if product is None:
        await state.clear()
        await message.answer(_("admin.product_not_found"))
        return

    assert admin is not None
    await persist_product_images(
        bot, session, product, [message.photo[-1].file_id], admin_id=admin.id
    )
    await session.refresh(product, attribute_names=["images"])
    await message.answer(
        _("admin.product_images_current", count=len(product.images)),
        reply_markup=images_upload_keyboard(_),
    )


@router.callback_query(ProductEditStates.uploading_images, AdminImagesFinishCallback.filter())
async def on_edit_images_finish(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    data = await state.get_data()
    await state.clear()
    product = await product_repository.get_by_id(session, data["product_id"])
    if product is None:
        await callback.answer(_("admin.product_not_found"), show_alert=True)
        return

    await message.edit_text(_("admin.product_images_updated"))
    await render_product_detail(message.answer, session, product, _)
    await callback.answer()


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
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    product = await _get_product_or_alert(callback, session, callback_data.product_id, _)
    if product is None:
        return

    assert admin is not None
    product = await admin_catalog_service.adjust_product_stock(
        session,
        admin_id=admin.id,
        product_id=product.id,
        delta=STOCK_DELTAS[callback_data.action],
    )
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
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(message, admin, _, roles=MANAGEMENT_ROLES, session=session):
        return
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

    assert admin is not None
    product = await admin_catalog_service.adjust_product_stock(
        session,
        admin_id=admin.id,
        product_id=product.id,
        delta=delta,
    )
    await message.answer(_("admin.product_stock_updated", value=product.stock_qty))
    await render_product_detail(message.answer, session, product, _)
