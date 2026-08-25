"""Admin section: campaign deep links ("where did this lead come from?").

Each source owns a short code; the shareable link is `t.me/<bot>?start=src_<code>`, and
app.bot.handlers.user.start attributes first-time visitors who arrive on it.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import (
    AdminSourceActionCallback,
    AdminSourceAddCallback,
    AdminSourceDetailCallback,
)
from app.bot.keyboards.inline.admin_common import cancel_only_keyboard
from app.bot.keyboards.inline.admin_sources import (
    admin_source_delete_confirm_keyboard,
    admin_source_detail_keyboard,
    admin_sources_list_keyboard,
)
from app.bot.states.admin_catalog import SourceFormStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.identity import bot_username
from app.bot.utils.messages import require_message
from app.db.models.admin import Admin
from app.db.models.traffic_source import TrafficSource
from app.db.repositories import traffic_source_repository

router = Router(name="admin_sources")

Sender = Callable[..., Awaitable[object]]


def _format_price(price: Decimal) -> str:
    return f"{price:,.0f}".replace(",", " ")


async def source_link(bot: Bot, source: TrafficSource) -> str:
    return f"https://t.me/{await bot_username(bot)}?start=src_{source.code}"


def _share_url(link: str, source: TrafficSource) -> str:
    """Telegram's forward dialog, pre-filled with the link and its campaign name."""
    return f"https://t.me/share/url?url={quote(link)}&text={quote(source.name)}"


async def render_sources_list(
    send: Sender, session: AsyncSession, *, translator: Callable[..., str]
) -> None:
    sources = await traffic_source_repository.list_all(session)
    text = translator("admin.sources_title" if sources else "admin.sources_empty")
    await send(text, reply_markup=admin_sources_list_keyboard(sources, translator=translator))


async def render_source_detail(
    send: Sender,
    session: AsyncSession,
    bot: Bot,
    source: TrafficSource,
    *,
    translator: Callable[..., str],
) -> None:
    stats = await traffic_source_repository.get_stats(session, source)
    link = await source_link(bot, source)
    status_key = (
        "admin.source_status_active" if source.is_active else "admin.source_status_inactive"
    )
    text = translator(
        "admin.source_detail",
        name=source.name,
        code=source.code,
        link=link,
        clicks=source.clicks_count,
        users=stats.users_count,
        orders=stats.orders_count,
        revenue=_format_price(stats.revenue),
        status=translator(status_key),
    )
    await send(
        text,
        reply_markup=admin_source_detail_keyboard(
            source, translator=translator, share_url=_share_url(link, source)
        ),
    )


async def _get_source_or_alert(
    callback: CallbackQuery,
    session: AsyncSession,
    source_id: int,
    translator: Callable[..., str],
) -> TrafficSource | None:
    source = await traffic_source_repository.get_by_id(session, source_id)
    if source is None:
        await callback.answer(translator("admin.source_not_found"), show_alert=True)
    return source


@router.callback_query(AdminSourceDetailCallback.filter())
async def on_source_detail(
    callback: CallbackQuery,
    callback_data: AdminSourceDetailCallback,
    session: AsyncSession,
    bot: Bot,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    source = await _get_source_or_alert(callback, session, callback_data.source_id, _)
    if source is None:
        return
    await render_source_detail(message.edit_text, session, bot, source, translator=_)
    await callback.answer()


@router.callback_query(AdminSourceAddCallback.filter())
async def on_source_add(
    callback: CallbackQuery,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(SourceFormStates.entering_name)
    await message.edit_text(_("admin.source_enter_name"), reply_markup=cancel_only_keyboard(_))
    await callback.answer()


@router.message(SourceFormStates.entering_name, F.text)
async def on_source_name_entered(message: Message, state: FSMContext, _: Callable) -> None:
    name = (message.text or "").strip()
    if not name:
        return
    suggested = traffic_source_repository.normalize_code(name)
    await state.update_data(name=name[:128], suggested_code=suggested)
    await state.set_state(SourceFormStates.entering_code)
    await message.answer(
        _("admin.source_enter_code", suggested=suggested or "-"),
        reply_markup=cancel_only_keyboard(_),
    )


@router.message(SourceFormStates.entering_code, F.text)
async def on_source_code_entered(
    message: Message, session: AsyncSession, bot: Bot, state: FSMContext, _: Callable
) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    # "-" accepts the code suggested from the campaign name.
    code = data.get("suggested_code", "") if raw == "-" else raw.lower()

    if not traffic_source_repository.CODE_PATTERN.match(code):
        await message.answer(
            _("admin.source_invalid_code"), reply_markup=cancel_only_keyboard(_)
        )
        return
    if await traffic_source_repository.get_by_code(session, code) is not None:
        await message.answer(
            _("admin.source_code_exists"), reply_markup=cancel_only_keyboard(_)
        )
        return

    source = await traffic_source_repository.create(
        session, code=code, name=data.get("name", code)
    )
    await state.clear()
    await message.answer(_("admin.source_created"))
    await render_source_detail(message.answer, session, bot, source, translator=_)


@router.callback_query(AdminSourceActionCallback.filter(F.action == "toggle"))
async def on_source_toggle(
    callback: CallbackQuery,
    callback_data: AdminSourceActionCallback,
    session: AsyncSession,
    bot: Bot,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    source = await _get_source_or_alert(callback, session, callback_data.source_id, _)
    if source is None:
        return
    source.is_active = not source.is_active
    await session.flush()
    await render_source_detail(message.edit_text, session, bot, source, translator=_)
    await callback.answer()


@router.callback_query(AdminSourceActionCallback.filter(F.action == "delete_request"))
async def on_source_delete_request(
    callback: CallbackQuery,
    callback_data: AdminSourceActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    source = await _get_source_or_alert(callback, session, callback_data.source_id, _)
    if source is None:
        return
    await message.edit_text(
        _("admin.source_delete_confirm", name=source.name),
        reply_markup=admin_source_delete_confirm_keyboard(source, translator=_),
    )
    await callback.answer()


@router.callback_query(AdminSourceActionCallback.filter(F.action == "delete_confirm"))
async def on_source_delete_confirm(
    callback: CallbackQuery,
    callback_data: AdminSourceActionCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _, roles=MANAGEMENT_ROLES):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    source = await _get_source_or_alert(callback, session, callback_data.source_id, _)
    if source is None:
        return
    # users.traffic_source_id is ON DELETE SET NULL — already-attributed users survive, they
    # just lose the attribution along with the campaign.
    await traffic_source_repository.delete(session, source)
    await callback.answer(_("admin.source_deleted"))
    await render_sources_list(message.edit_text, session, translator=_)
