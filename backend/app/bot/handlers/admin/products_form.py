from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.products import render_product_detail
from app.bot.keyboards.callback_data import (
    AdminFormSaveCallback,
    AdminImagesFinishCallback,
    AdminProductCategoryChooseCallback,
    AdminUnitCallback,
    SkipStepCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_products import (
    images_upload_keyboard,
    review_keyboard,
    unit_picker_keyboard,
)
from app.bot.keyboards.inline.checkout import comment_step_keyboard
from app.bot.states.admin_catalog import ProductFormStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.core.config import settings
from app.db.models.admin import Admin
from app.db.models.enums import ProductUnit
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.repositories import category_repository, product_repository

router = Router(name="admin_products_form")


@router.callback_query(AdminProductCategoryChooseCallback.filter())
async def on_start_add_product(
    callback: CallbackQuery,
    callback_data: AdminProductCategoryChooseCallback,
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
    category = await category_repository.get_by_id(session, callback_data.category_id)
    if category is None:
        await callback.answer(_("admin.category_not_found"), show_alert=True)
        return

    await state.set_state(ProductFormStates.entering_name_uz)
    await state.update_data(category_id=category.id, images=[])
    await message.edit_text(
        _("admin.product_enter_name_uz"), reply_markup=cancel_only_keyboard(_)
    )
    await callback.answer()


@router.message(ProductFormStates.entering_name_uz, F.text)
async def on_name_uz(message: Message, state: FSMContext, _: Callable) -> None:
    name = (message.text or "").strip()
    if not name:
        return
    await state.update_data(name_uz=name, name_ru=name)
    await state.set_state(ProductFormStates.entering_description_uz)
    await message.answer(
        _("admin.product_enter_description_uz"),
        reply_markup=comment_step_keyboard(_, show_back=False),
    )


async def _advance_to_sku(target: Message, state: FSMContext, _: Callable) -> None:
    await state.set_state(ProductFormStates.entering_sku)
    await target.answer(_("admin.product_enter_sku"), reply_markup=cancel_only_keyboard(_))


@router.message(ProductFormStates.entering_description_uz, F.text)
async def on_description_uz(message: Message, state: FSMContext, _: Callable) -> None:
    description = (message.text or "").strip() or None
    await state.update_data(description_uz=description, description_ru=description)
    await _advance_to_sku(message, state, _)


@router.callback_query(
    ProductFormStates.entering_description_uz, SkipStepCallback.filter(F.step == "comment")
)
async def on_description_uz_skip(
    callback: CallbackQuery, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(description_uz=None, description_ru=None)
    await _advance_to_sku(message, state, _)
    await callback.answer()


@router.message(ProductFormStates.entering_sku, F.text)
async def on_sku(
    message: Message, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    sku = (message.text or "").strip()
    if not sku:
        return
    if await product_repository.get_by_sku(session, sku) is not None:
        await message.answer(
            _("admin.product_sku_exists"), reply_markup=cancel_only_keyboard(_)
        )
        return
    await state.update_data(sku=sku)
    await state.set_state(ProductFormStates.entering_price)
    await message.answer(_("admin.product_enter_price"), reply_markup=cancel_only_keyboard(_))


@router.message(ProductFormStates.entering_price, F.text)
async def on_price(message: Message, state: FSMContext, _: Callable) -> None:
    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        price = Decimal(raw)
        if price <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer(
            _("admin.product_invalid_price"), reply_markup=cancel_only_keyboard(_)
        )
        return
    await state.update_data(price=str(price))
    await state.set_state(ProductFormStates.entering_stock)
    await message.answer(_("admin.product_enter_stock"), reply_markup=cancel_only_keyboard(_))


@router.message(ProductFormStates.entering_stock, F.text)
async def on_stock(message: Message, state: FSMContext, _: Callable) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(
            _("admin.product_invalid_stock"), reply_markup=cancel_only_keyboard(_)
        )
        return
    await state.update_data(stock_qty=int(raw))
    await state.set_state(ProductFormStates.choosing_unit)
    await message.answer(_("admin.product_choose_unit"), reply_markup=unit_picker_keyboard(_))


@router.callback_query(ProductFormStates.choosing_unit, AdminUnitCallback.filter())
async def on_unit_chosen(
    callback: CallbackQuery, callback_data: AdminUnitCallback, state: FSMContext, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.update_data(unit=callback_data.value)
    await state.set_state(ProductFormStates.uploading_images)
    await message.edit_text(
        _("admin.product_upload_images"), reply_markup=images_upload_keyboard(_)
    )
    await callback.answer()


@router.message(ProductFormStates.uploading_images, F.photo)
async def on_image_uploaded(message: Message, state: FSMContext, _: Callable) -> None:
    if not message.photo:
        return
    data = await state.get_data()
    images = list(data.get("images", []))
    images.append(message.photo[-1].file_id)
    await state.update_data(images=images)
    await message.answer(f"📷 {len(images)}", reply_markup=images_upload_keyboard(_))


@router.callback_query(ProductFormStates.uploading_images, AdminImagesFinishCallback.filter())
async def on_images_finish(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str, _: Callable
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(ProductFormStates.reviewing)
    text = await _build_review_text(session, state, lang, _)
    await message.edit_text(text, reply_markup=review_keyboard(_))
    await callback.answer()


async def _build_review_text(
    session: AsyncSession, state: FSMContext, lang: str, translator: Callable[..., str]
) -> str:
    data = await state.get_data()
    category = await category_repository.get_by_id(session, data["category_id"])
    unit_label = translator(f"units.{data['unit']}")
    header = translator("admin.product_review_title")
    card = translator(
        "admin.product_card",
        name_uz=data["name_uz"],
        name_ru=data["name_ru"],
        sku=data["sku"],
        price=data["price"],
        stock=data["stock_qty"],
        unit=unit_label,
        status=translator("admin.product_active"),
    )
    category_line = f"\n\n🗂 {category.name_uz if category else '-'}"
    images_line = f"\n📷 {len(data.get('images', []))}"
    return f"{header}\n\n{card}{category_line}{images_line}"


@router.callback_query(ProductFormStates.reviewing, AdminFormSaveCallback.filter())
async def on_save_product(
    callback: CallbackQuery,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    state: FSMContext,
    lang: str,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return

    data = await state.get_data()
    await state.clear()

    product = Product(
        category_id=data["category_id"],
        name_uz=data["name_uz"],
        name_ru=data["name_ru"],
        description_uz=data.get("description_uz"),
        description_ru=data.get("description_ru"),
        sku=data["sku"],
        price=Decimal(data["price"]),
        stock_qty=data["stock_qty"],
        unit=ProductUnit(data["unit"]),
    )
    session.add(product)
    await session.flush()

    await persist_product_images(bot, session, product, data.get("images", []))

    category = await category_repository.get_by_id(session, product.category_id)
    if category is not None:
        category.products_count = category.products_count + 1
        await session.flush()

    # product.images was never loaded on this freshly-created instance (only
    # get_by_id() eager-loads it) - refetch so the detail keyboard's sync access
    # to .images doesn't trigger a lazy-load outside the awaited context.
    reloaded = await product_repository.get_by_id(session, product.id)
    assert reloaded is not None  # just flushed in this same transaction
    await render_product_detail(message.edit_text, session, reloaded, _)
    await callback.answer(_("admin.product_created"))


async def persist_product_images(
    bot: Bot,
    session: AsyncSession,
    product: Product,
    file_ids: list[str],
    *,
    start_index: int = 0,
) -> None:
    """Downloads Telegram photo file_ids to MEDIA_ROOT/products/{id}/ and creates ProductImage
    rows. `start_index` lets callers append to a product that already has images (the first-ever
    image, index 0, is the only one auto-marked `is_main`)."""
    if not file_ids:
        return
    product_dir = settings.media_root_path / "products" / str(product.id)
    product_dir.mkdir(parents=True, exist_ok=True)
    for offset, file_id in enumerate(file_ids):
        index = start_index + offset
        destination = product_dir / f"{index}.jpg"
        await bot.download(file_id, destination=destination)
        url = f"{settings.media_base_url}/products/{product.id}/{destination.name}"
        session.add(
            ProductImage(
                product_id=product.id,
                url=url,
                telegram_file_id=file_id,
                is_main=(index == 0),
                sort_order=index,
            )
        )
    await session.flush()
