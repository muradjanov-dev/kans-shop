from collections.abc import Awaitable, Callable
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    ORIGIN_CATEGORY,
    ORIGIN_SEARCH,
    ROOT_CATEGORY_ID,
    AddToCartCallback,
    CategoryCallback,
    FavoriteToggleCallback,
    ProductCallback,
    ProductListCallback,
    ProductQtyCallback,
    SearchPageCallback,
    SearchProductCallback,
)
from app.bot.keyboards.inline.catalog import (
    categories_keyboard,
    product_detail_keyboard,
    product_list_keyboard,
    search_results_keyboard,
)
from app.bot.utils.i18n import menu_button_texts
from app.bot.utils.messages import require_message
from app.core.exceptions import CategoryNotFoundError, OutOfStockError, ProductNotFoundError
from app.db.models.category import Category
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories import favorite_repository
from app.services import cart_service, catalog_service
from app.services.common import DEFAULT_CATALOG_PAGE_SIZE

router = Router(name="catalog")

Sender = Callable[..., Awaitable[object]]


def _category_name(category: Category, lang: str) -> str:
    return category.name_uz if lang == "uz" else category.name_ru


def _product_name(product: Product, lang: str) -> str:
    return product.name_uz if lang == "uz" else product.name_ru


def _product_description(product: Product, lang: str) -> str:
    return (product.description_uz if lang == "uz" else product.description_ru) or ""


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


def _back_callback_for(origin: str, ref_id: int, page: int) -> str:
    if origin == ORIGIN_SEARCH:
        return SearchPageCallback(page=page).pack()
    return ProductListCallback(category_id=ref_id, page=page).pack()


async def send_category_level(
    send: Sender,
    session: AsyncSession,
    category_id: int,
    *,
    lang: str,
    translator: Callable[..., str],
) -> None:
    """category_id=ROOT_CATEGORY_ID shows top-level categories; otherwise shows the given
    category's subcategories if it has any, else falls through to its product list."""
    if category_id == ROOT_CATEGORY_ID:
        categories = await catalog_service.list_root_categories(session)
        if not categories:
            await send(translator("catalog.empty_catalog"))
            return
        await send(
            translator("catalog.choose_category"),
            reply_markup=categories_keyboard(
                categories, lang=lang, translator=translator, back_target=None
            ),
        )
        return

    try:
        category = await catalog_service.get_category(session, category_id)
    except CategoryNotFoundError:
        await send(translator("common.not_found"))
        return

    subcategories = await catalog_service.list_subcategories(session, category_id)
    if subcategories:
        back_target = (
            category.parent_id if category.parent_id is not None else ROOT_CATEGORY_ID
        )
        await send(
            translator("catalog.choose_category"),
            reply_markup=categories_keyboard(
                subcategories, lang=lang, translator=translator, back_target=back_target
            ),
        )
        return

    await send_product_list(send, session, category_id, 1, lang=lang, translator=translator)


async def send_product_list(
    send: Sender,
    session: AsyncSession,
    category_id: int,
    page: int,
    *,
    lang: str,
    translator: Callable[..., str],
) -> None:
    try:
        category = await catalog_service.get_category(session, category_id)
    except CategoryNotFoundError:
        await send(translator("common.not_found"))
        return

    result = await catalog_service.list_products(
        session, category_id, page=page, limit=DEFAULT_CATALOG_PAGE_SIZE
    )
    if not result.items:
        await send(translator("catalog.empty_category"))
        return

    back_target = category.parent_id if category.parent_id is not None else ROOT_CATEGORY_ID
    await send(
        _category_name(category, lang),
        reply_markup=product_list_keyboard(
            result,
            category_id=category_id,
            lang=lang,
            translator=translator,
            back_target=back_target,
        ),
    )


async def send_product_detail(
    send: Sender,
    session: AsyncSession,
    product_id: int,
    *,
    user_id: int,
    origin: str,
    ref_id: int,
    page: int,
    qty: int = 1,
    back_callback_data: str,
    lang: str,
    translator: Callable[..., str],
    track_view: bool = True,
) -> None:
    try:
        product = await catalog_service.get_product(session, product_id, track_view=track_view)
    except ProductNotFoundError:
        await send(translator("common.not_found"))
        return

    name = _product_name(product, lang)
    description = _product_description(product, lang)
    price = _format_price(product.price)
    unit = translator(f"units.{product.unit.value}")
    in_stock = product.stock_qty > 0
    stock = str(product.stock_qty) if in_stock else translator("catalog.out_of_stock")

    if description:
        text = translator(
            "catalog.product_card",
            name=name,
            description=description,
            price=price,
            stock=stock,
            unit=unit,
        )
    else:
        text = translator(
            "catalog.product_card_no_description",
            name=name,
            price=price,
            stock=stock,
            unit=unit,
        )

    is_favorite = (await favorite_repository.get(session, user_id, product_id)) is not None
    qty = max(1, min(qty, product.stock_qty)) if in_stock else qty

    await send(
        text,
        reply_markup=product_detail_keyboard(
            product_id=product_id,
            origin=origin,
            ref_id=ref_id,
            page=page,
            qty=qty,
            in_stock=in_stock,
            is_favorite=is_favorite,
            back_callback_data=back_callback_data,
            translator=translator,
        ),
    )


@router.message(F.text.in_(menu_button_texts("menu.catalog")))
async def open_catalog(
    message: Message, session: AsyncSession, lang: str, _: Callable
) -> None:
    await send_category_level(
        message.answer, session, ROOT_CATEGORY_ID, lang=lang, translator=_
    )


@router.callback_query(CategoryCallback.filter())
async def on_category_selected(
    callback: CallbackQuery,
    callback_data: CategoryCallback,
    session: AsyncSession,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await send_category_level(
        edit, session, callback_data.category_id, lang=lang, translator=_
    )
    await callback.answer()


@router.callback_query(ProductListCallback.filter())
async def on_product_list_page(
    callback: CallbackQuery,
    callback_data: ProductListCallback,
    session: AsyncSession,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    await send_product_list(
        edit, session, callback_data.category_id, callback_data.page, lang=lang, translator=_
    )
    await callback.answer()


@router.callback_query(ProductCallback.filter())
async def on_product_selected(
    callback: CallbackQuery,
    callback_data: ProductCallback,
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

    back = ProductListCallback(
        category_id=callback_data.category_id, page=callback_data.page
    ).pack()
    await send_product_detail(
        edit,
        session,
        callback_data.product_id,
        user_id=user.id,
        origin=ORIGIN_CATEGORY,
        ref_id=callback_data.category_id,
        page=callback_data.page,
        back_callback_data=back,
        lang=lang,
        translator=_,
    )
    await callback.answer()


@router.callback_query(ProductQtyCallback.filter())
async def on_product_qty_change(
    callback: CallbackQuery,
    callback_data: ProductQtyCallback,
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

    delta = 1 if callback_data.action == "inc" else -1
    new_qty = max(1, callback_data.qty + delta)
    back = _back_callback_for(callback_data.origin, callback_data.ref_id, callback_data.page)
    await send_product_detail(
        edit,
        session,
        callback_data.product_id,
        user_id=user.id,
        origin=callback_data.origin,
        ref_id=callback_data.ref_id,
        page=callback_data.page,
        qty=new_qty,
        back_callback_data=back,
        lang=lang,
        translator=_,
        track_view=False,
    )
    await callback.answer()


@router.callback_query(AddToCartCallback.filter())
async def on_add_to_cart(
    callback: CallbackQuery,
    callback_data: AddToCartCallback,
    session: AsyncSession,
    user: User,
    _: Callable,
) -> None:
    try:
        await cart_service.add_item(
            session, user.id, callback_data.product_id, callback_data.qty
        )
    except OutOfStockError:
        await callback.answer(_("cart.out_of_stock_alert"), show_alert=True)
        return
    except ProductNotFoundError:
        await callback.answer(_("common.not_found"), show_alert=True)
        return
    await callback.answer(_("cart.added_alert"))


@router.callback_query(FavoriteToggleCallback.filter())
async def on_favorite_toggle(
    callback: CallbackQuery,
    callback_data: FavoriteToggleCallback,
    session: AsyncSession,
    user: User,
    lang: str,
    _: Callable,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    existing = await favorite_repository.get(session, user.id, callback_data.product_id)
    if existing is not None:
        await favorite_repository.remove(session, user.id, callback_data.product_id)
    else:
        await favorite_repository.add(session, user.id, callback_data.product_id)

    async def edit(text: str, reply_markup=None) -> object:
        return await message.edit_text(text, reply_markup=reply_markup)

    back = _back_callback_for(callback_data.origin, callback_data.ref_id, callback_data.page)
    await send_product_detail(
        edit,
        session,
        callback_data.product_id,
        user_id=user.id,
        origin=callback_data.origin,
        ref_id=callback_data.ref_id,
        page=callback_data.page,
        back_callback_data=back,
        lang=lang,
        translator=_,
        track_view=False,
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(SearchPageCallback.filter())
async def on_search_page(
    callback: CallbackQuery,
    callback_data: SearchPageCallback,
    session: AsyncSession,
    lang: str,
    _: Callable,
    state: FSMContext,
) -> None:
    message = await require_message(callback, _)
    if message is None:
        return

    data = await state.get_data()
    query = data.get("search_query", "")
    result = await catalog_service.search_products(
        session, query, page=callback_data.page, limit=DEFAULT_CATALOG_PAGE_SIZE
    )
    await message.edit_text(
        _("catalog.search_results", query=query, count=result.total),
        reply_markup=search_results_keyboard(result, lang=lang, translator=_),
    )
    await callback.answer()


@router.callback_query(SearchProductCallback.filter())
async def on_search_product_selected(
    callback: CallbackQuery,
    callback_data: SearchProductCallback,
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

    back = SearchPageCallback(page=callback_data.page).pack()
    await send_product_detail(
        edit,
        session,
        callback_data.product_id,
        user_id=user.id,
        origin=ORIGIN_SEARCH,
        ref_id=0,
        page=callback_data.page,
        back_callback_data=back,
        lang=lang,
        translator=_,
    )
    await callback.answer()


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def search_products_by_text(
    message: Message, session: AsyncSession, lang: str, _: Callable, state: FSMContext
) -> None:
    query = (message.text or "").strip()
    if not query:
        return
    await state.update_data(search_query=query)
    result = await catalog_service.search_products(
        session, query, limit=DEFAULT_CATALOG_PAGE_SIZE
    )
    if not result.items:
        await message.answer(_("catalog.search_empty"))
        return
    await message.answer(
        _("catalog.search_results", query=query, count=result.total),
        reply_markup=search_results_keyboard(result, lang=lang, translator=_),
    )
