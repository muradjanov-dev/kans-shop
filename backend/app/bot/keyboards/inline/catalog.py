from collections.abc import Callable, Sequence
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.callback_data import (
    CategoryCallback,
    ProductCallback,
    ProductListCallback,
    SearchPageCallback,
    SearchProductCallback,
)
from app.db.models.category import Category
from app.db.models.product import Product
from app.services.common import Page


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def _product_label(product: Product, lang: str) -> str:
    name = product.name_uz if lang == "uz" else product.name_ru
    return f"{name} — {_format_price(product.price)}"


def _pagination_row(
    page: Page, *, translator: Callable[..., str], make_page_callback: Callable[[int], str]
) -> list[InlineKeyboardButton]:
    row = []
    if page.has_prev:
        row.append(
            InlineKeyboardButton(text="◀️", callback_data=make_page_callback(page.page - 1))
        )
    row.append(
        InlineKeyboardButton(
            text=translator(
                "catalog.page_indicator", page=page.page, total_pages=page.total_pages
            ),
            callback_data="noop",
        )
    )
    if page.has_next:
        row.append(
            InlineKeyboardButton(text="▶️", callback_data=make_page_callback(page.page + 1))
        )
    return row


def categories_keyboard(
    categories: Sequence[Category],
    *,
    lang: str,
    translator: Callable[..., str],
    back_target: int | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        name = category.name_uz if lang == "uz" else category.name_ru
        builder.row(
            InlineKeyboardButton(
                text=name, callback_data=CategoryCallback(category_id=category.id).pack()
            )
        )
    if back_target is not None:
        builder.row(
            InlineKeyboardButton(
                text=translator("common.back"),
                callback_data=CategoryCallback(category_id=back_target).pack(),
            )
        )
    return builder.as_markup()


def product_list_keyboard(
    page: Page[Product],
    *,
    category_id: int,
    lang: str,
    translator: Callable[..., str],
    back_target: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in page.items:
        builder.row(
            InlineKeyboardButton(
                text=_product_label(product, lang),
                callback_data=ProductCallback(
                    product_id=product.id, category_id=category_id, page=page.page
                ).pack(),
            )
        )
    builder.row(
        *_pagination_row(
            page,
            translator=translator,
            make_page_callback=lambda p: ProductListCallback(
                category_id=category_id, page=p
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=translator("common.back"),
            callback_data=CategoryCallback(category_id=back_target).pack(),
        )
    )
    return builder.as_markup()


def search_results_keyboard(
    page: Page[Product], *, lang: str, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in page.items:
        builder.row(
            InlineKeyboardButton(
                text=_product_label(product, lang),
                callback_data=SearchProductCallback(
                    product_id=product.id, page=page.page
                ).pack(),
            )
        )
    builder.row(
        *_pagination_row(
            page,
            translator=translator,
            make_page_callback=lambda p: SearchPageCallback(page=p).pack(),
        )
    )
    return builder.as_markup()


def product_detail_keyboard(
    *, back_callback_data: str, translator: Callable[..., str]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=translator("common.back"), callback_data=back_callback_data)
    )
    return builder.as_markup()
