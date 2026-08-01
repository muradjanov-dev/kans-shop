from collections.abc import Callable
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    AdminFormSaveCallback,
    AdminImagesFinishCallback,
    AdminMenuCallback,
    AdminProductActionCallback,
    AdminProductCategoryChooseCallback,
    AdminProductDetailCallback,
    AdminProductFieldEditCallback,
    AdminProductListCallback,
    AdminUnitCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_button
from app.db.models.enums import ProductUnit
from app.db.models.product import Product
from app.services.common import Page

EDITABLE_FIELDS = ("name_uz", "name_ru", "description_uz", "description_ru", "price", "sku")


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def admin_product_list_keyboard(
    page: Page[Product], *, category_id: int, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in page.items:
        marker = "" if product.is_active else "🔴 "
        builder.row(
            InlineKeyboardButton(
                text=f"{marker}{product.name_uz} — {_format_price(product.price)}",
                callback_data=AdminProductDetailCallback(product_id=product.id).pack(),
            )
        )
    nav_row = []
    if page.has_prev:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=AdminProductListCallback(
                    category_id=category_id, page=page.page - 1
                ).pack(),
            )
        )
    if page.total:
        nav_row.append(
            InlineKeyboardButton(
                text=translator(
                    "catalog.page_indicator", page=page.page, total_pages=page.total_pages
                ),
                callback_data="noop",
            )
        )
    if page.has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=AdminProductListCallback(
                    category_id=category_id, page=page.page + 1
                ).pack(),
            )
        )
    if nav_row:
        builder.row(*nav_row)
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_add_button"),
            callback_data=AdminProductCategoryChooseCallback(category_id=category_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.back_to_menu"),
            callback_data=AdminMenuCallback(section="products").pack(),
        )
    )
    return builder.as_markup()


def admin_product_detail_keyboard(
    product: Product, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field in EDITABLE_FIELDS:
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {translator(f'admin.product_field_{field}')}",
                callback_data=AdminProductFieldEditCallback(
                    product_id=product.id, field=field
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_stock_label"),
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="stock_menu"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_manage_images", count=len(product.images)),
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="manage_images"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_toggle_active"),
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="toggle_active"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_delete_button"),
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="delete_request"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminProductListCallback(
                category_id=product.category_id, page=1
            ).pack(),
        )
    )
    return builder.as_markup()


def admin_product_delete_confirm_keyboard(
    product: Product, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_delete_confirm_yes"),
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="delete_confirm"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminProductDetailCallback(product_id=product.id).pack(),
        )
    )
    return builder.as_markup()


def admin_stock_menu_keyboard(
    product: Product, *, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="+10",
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="stock_p10"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="+50",
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="stock_p50"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="-1",
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="stock_m1"
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_stock_custom"),
            callback_data=AdminProductActionCallback(
                product_id=product.id, action="stock_custom"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=AdminProductDetailCallback(product_id=product.id).pack(),
        )
    )
    return builder.as_markup()


def unit_picker_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for unit in ProductUnit:
        builder.row(
            InlineKeyboardButton(
                text=translator(f"units.{unit.value}"),
                callback_data=AdminUnitCallback(value=unit.value).pack(),
            )
        )
    builder.row(cancel_button(translator))
    return builder.as_markup()


def images_upload_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_finish_upload"),
            callback_data=AdminImagesFinishCallback().pack(),
        )
    )
    builder.row(cancel_button(translator))
    return builder.as_markup()


def review_keyboard(translator: Callable[..., str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=translator("admin.product_save_button"),
            callback_data=AdminFormSaveCallback().pack(),
        )
    )
    builder.row(cancel_button(translator))
    return builder.as_markup()
