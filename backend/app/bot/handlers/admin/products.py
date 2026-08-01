from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    AdminProductActionCallback,
    AdminProductDetailCallback,
    AdminProductListCallback,
)
from app.bot.keyboards.inline.admin_common import flat_category_picker_keyboard
from app.bot.keyboards.inline.admin_products import (
    admin_product_delete_confirm_keyboard,
    admin_product_detail_keyboard,
    admin_product_list_keyboard,
)
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.product import Product
from app.db.repositories import category_repository, product_repository
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE
from app.services.common import Page as PageType

router = Router(name="admin_products")

Sender = Callable[..., Awaitable[object]]


async def render_products_category_picker(
    send: Sender, session: AsyncSession, translator: Callable[..., str]
) -> None:
    categories = await category_repository.list_all(session, active_only=False)
    text = translator("admin.products_title")
    if not categories:
        text += "\n\n" + translator("admin.category_empty_list")
    await send(
        text,
        reply_markup=flat_category_picker_keyboard(
            categories,
            translator=translator,
            make_callback_data=lambda cid: AdminProductListCallback(
                category_id=cid, page=1
            ).pack(),
        ),
    )


async def render_product_list(
    send: Sender,
    session: AsyncSession,
    category_id: int,
    page: int,
    translator: Callable[..., str],
) -> None:
    result = await product_repository.list_by_category(
        session, category_id, page=page, limit=DEFAULT_CATALOG_PAGE_SIZE, active_only=False
    )
    items, total = result
    page_obj = PageType(items=items, total=total, page=page, limit=DEFAULT_CATALOG_PAGE_SIZE)
    text = translator("admin.products_title")
    if not items:
        text += "\n\n" + translator("admin.product_empty_list")
    await send(
        text,
        reply_markup=admin_product_list_keyboard(
            page_obj, category_id=category_id, translator=translator
        ),
    )


async def render_product_detail(
    send: Sender, session: AsyncSession, product: Product, translator: Callable[..., str]
) -> None:
    status = (
        translator("admin.product_active")
        if product.is_active
        else translator("admin.product_inactive")
    )
    unit_label = translator(f"units.{product.unit.value}")
    text = translator(
        "admin.product_card",
        name_uz=product.name_uz,
        name_ru=product.name_ru,
        sku=product.sku,
        price=f"{product.price:,.0f}".replace(",", " "),
        stock=product.stock_qty,
        unit=unit_label,
        status=status,
    )
    await send(
        text, reply_markup=admin_product_detail_keyboard(product, translator=translator)
    )


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


@router.callback_query(AdminProductListCallback.filter())
async def on_product_list(
    callback: CallbackQuery,
    callback_data: AdminProductListCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await render_product_list(edit, session, callback_data.category_id, callback_data.page, _)
    await callback.answer()


@router.callback_query(AdminProductDetailCallback.filter())
async def on_product_detail(
    callback: CallbackQuery,
    callback_data: AdminProductDetailCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    product = await _get_product_or_alert(callback, session, callback_data.product_id, _)
    if product is None:
        return
    await render_product_detail(message.edit_text, session, product, _)
    await callback.answer()


@router.callback_query(AdminProductActionCallback.filter(F.action == "toggle_active"))
async def on_product_toggle_active(
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
    product.is_active = not product.is_active
    await session.flush()
    await render_product_detail(message.edit_text, session, product, _)
    await callback.answer()


@router.callback_query(AdminProductActionCallback.filter(F.action == "delete_request"))
async def on_product_delete_request(
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
        _("admin.product_delete_confirm"),
        reply_markup=admin_product_delete_confirm_keyboard(product, translator=_),
    )
    await callback.answer()


@router.callback_query(AdminProductActionCallback.filter(F.action == "delete_confirm"))
async def on_product_delete_confirm(
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
    category_id = product.category_id
    await session.delete(product)
    await session.flush()

    await message.edit_text(_("admin.product_deleted"))
    await render_product_list(message.answer, session, category_id, 1, _)
    await callback.answer()
