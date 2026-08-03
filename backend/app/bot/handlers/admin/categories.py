import re
import unicodedata
from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    ROOT_CATEGORY_ID,
    AdminCategoryActionCallback,
    AdminCategoryDetailCallback,
    AdminCategoryListCallback,
)
from app.bot.keyboards.inline.admin_categories import (
    admin_categories_list_keyboard,
    admin_category_delete_confirm_keyboard,
    admin_category_detail_keyboard,
)
from app.bot.states.admin_catalog import CategoryFormStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.category import Category
from app.db.repositories import category_repository, product_repository

router = Router(name="admin_categories")

Sender = Callable[..., Awaitable[object]]


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "category"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    suffix = 2
    while await category_repository.get_by_slug(session, slug) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def render_categories_list(
    send: Sender, session: AsyncSession, parent_id: int, *, translator: Callable[..., str]
) -> None:
    categories = await category_repository.list_children(
        session, parent_id if parent_id != ROOT_CATEGORY_ID else None, active_only=False
    )
    text = translator("admin.categories_title")
    if not categories:
        text += "\n\n" + translator("admin.category_empty_list")
    await send(
        text,
        reply_markup=admin_categories_list_keyboard(
            categories, parent_id=parent_id, translator=translator
        ),
    )


async def _render_category_detail(
    message: Message, session: AsyncSession, category: Category, translator: Callable[..., str]
) -> None:
    _items, count = await product_repository.list_by_category(
        session, category.id, page=1, limit=1, active_only=False
    )
    status = (
        translator("admin.category_active")
        if category.is_active
        else translator("admin.category_inactive")
    )
    text = translator(
        "admin.category_detail",
        name_uz=category.name_uz,
        name_ru=category.name_ru,
        slug=category.slug,
        count=count,
        status=status,
    )
    await message.edit_text(
        text, reply_markup=admin_category_detail_keyboard(category, translator=translator)
    )


async def _get_category_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    category_id: int,
    translator: Callable[..., str],
) -> Category | None:
    category = await category_repository.get_by_id(session, category_id)
    if category is None:
        await callback.answer(translator("admin.category_not_found"), show_alert=True)
    return category


@router.callback_query(AdminCategoryListCallback.filter())
async def on_category_list(
    callback: CallbackQuery,
    callback_data: AdminCategoryListCallback,
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

    await render_categories_list(edit, session, callback_data.parent_id, translator=_)
    await callback.answer()


@router.callback_query(AdminCategoryDetailCallback.filter())
async def on_category_detail(
    callback: CallbackQuery,
    callback_data: AdminCategoryDetailCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    category = await _get_category_or_alert(callback, session, callback_data.category_id, _)
    if category is None:
        return
    await _render_category_detail(message, session, category, _)
    await callback.answer()


@router.callback_query(AdminCategoryActionCallback.filter(F.action == "add_sub"))
async def on_category_add_start(
    callback: CallbackQuery,
    callback_data: AdminCategoryActionCallback,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(CategoryFormStates.entering_name_uz)
    await state.update_data(parent_id=callback_data.category_id)
    await message.edit_text(_("admin.category_enter_name_uz"))
    await callback.answer()


@router.message(CategoryFormStates.entering_name_uz, F.text)
async def on_category_name_uz(
    message: Message, session: AsyncSession, state: FSMContext, _: Callable
) -> None:
    name_uz = (message.text or "").strip()
    if not name_uz:
        return
    data = await state.get_data()
    await state.clear()

    parent_id = data.get("parent_id") or None
    if parent_id == ROOT_CATEGORY_ID:
        parent_id = None
    slug = await _unique_slug(session, _slugify(name_uz))
    category = Category(name_uz=name_uz, name_ru=name_uz, slug=slug, parent_id=parent_id)
    session.add(category)
    await session.flush()

    await message.answer(_("admin.category_created"))
    await render_categories_list(
        message.answer, session, parent_id or ROOT_CATEGORY_ID, translator=_
    )


@router.callback_query(AdminCategoryActionCallback.filter(F.action == "toggle_active"))
async def on_category_toggle_active(
    callback: CallbackQuery,
    callback_data: AdminCategoryActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    category = await _get_category_or_alert(callback, session, callback_data.category_id, _)
    if category is None:
        return
    category.is_active = not category.is_active
    await session.flush()
    await _render_category_detail(message, session, category, _)
    await callback.answer()


@router.callback_query(AdminCategoryActionCallback.filter(F.action == "delete_request"))
async def on_category_delete_request(
    callback: CallbackQuery,
    callback_data: AdminCategoryActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    category = await _get_category_or_alert(callback, session, callback_data.category_id, _)
    if category is None:
        return
    await message.edit_text(
        _("admin.category_delete_confirm"),
        reply_markup=admin_category_delete_confirm_keyboard(category, translator=_),
    )
    await callback.answer()


@router.callback_query(AdminCategoryActionCallback.filter(F.action == "delete_confirm"))
async def on_category_delete_confirm(
    callback: CallbackQuery,
    callback_data: AdminCategoryActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    category = await _get_category_or_alert(callback, session, callback_data.category_id, _)
    if category is None:
        return

    _items, product_count = await product_repository.list_by_category(
        session, category.id, page=1, limit=1, active_only=False
    )
    children = await category_repository.list_children(session, category.id, active_only=False)
    if product_count or children:
        await callback.answer(_("admin.category_delete_has_products"), show_alert=True)
        return

    parent_id = category.parent_id or ROOT_CATEGORY_ID
    await session.delete(category)
    await session.flush()

    await message.edit_text(_("admin.category_deleted"))
    await render_categories_list(message.answer, session, parent_id, translator=_)
    await callback.answer()
