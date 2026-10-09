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
    admin_source_detail_keyboard,
    admin_sources_list_keyboard,
)
from app.bot.states.admin_catalog import SourceFormStates
from app.bot.utils.admin_guard import MANAGEMENT_ROLES, require_admin
from app.bot.utils.identity import bot_username
from app.bot.utils.messages import require_message
from app.core.exceptions import TrafficSourceCodeConflictError
from app.db.models.admin import Admin
from app.db.models.traffic_source import TrafficSource
from app.db.repositories import traffic_source_repository
from app.services import traffic_source_service

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
    send: Sender,
    session: AsyncSession,
    *,
    admin_id: int,
    translator: Callable[..., str],
) -> None:
    result = await traffic_source_service.list_sources(
        session, admin_id=admin_id, page=1, limit=100
    )
    sources = result.items
    text = translator("admin.sources_title" if sources else "admin.sources_empty")
    await send(text, reply_markup=admin_sources_list_keyboard(sources, translator=translator))


async def render_source_detail(
    send: Sender,
    session: AsyncSession,
    bot: Bot,
    source: TrafficSource,
    *,
    admin_id: int,
    translator: Callable[..., str],
) -> None:
    stats = await traffic_source_service.get_source_stats(
        session, admin_id=admin_id, source_id=source.id
    )
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
        users=stats.first_touch_users,
        orders=stats.orders_count,
        order_value=_format_price(stats.order_value),
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
    if admin is None or not await require_admin(
        callback, admin, _, roles=MANAGEMENT_ROLES, session=session
    ):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    source = await _get_source_or_alert(callback, session, callback_data.source_id, _)
    if source is None:
        return
    await render_source_detail(
        message.edit_text, session, bot, source, admin_id=admin.id, translator=_
    )
    await callback.answer()


@router.callback_query(AdminSourceAddCallback.filter())
async def on_source_add(
    callback: CallbackQuery,
    session: AsyncSession,
    admin: Admin | None,
    state: FSMContext,
    _: Callable,
) -> None:
    if admin is None or not await require_admin(
        callback, admin, _, roles=MANAGEMENT_ROLES, session=session
    ):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await state.set_state(SourceFormStates.entering_name)
    await message.edit_text(_("admin.source_enter_name"), reply_markup=cancel_only_keyboard(_))
    await callback.answer()


@router.message(SourceFormStates.entering_name, F.text)
async def on_source_name_entered(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    admin: Admin | None,
    _: Callable,
) -> None:
    if admin is None or not await require_admin(
        message, admin, _, roles=MANAGEMENT_ROLES, session=session
    ):
        return
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
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
    admin: Admin | None,
    _: Callable,
) -> None:
    if admin is None or not await require_admin(
        message, admin, _, roles=MANAGEMENT_ROLES, session=session
    ):
        return
    data = await state.get_data()
    raw = (message.text or "").strip()
    # "-" accepts the code suggested from the campaign name.
    code = data.get("suggested_code", "") if raw == "-" else raw.lower()

    if not traffic_source_repository.CODE_PATTERN.match(code):
        await message.answer(
            _("admin.source_invalid_code"), reply_markup=cancel_only_keyboard(_)
        )
        return
    try:
        source = await traffic_source_service.create_source(
            session, admin_id=admin.id, code=code, name=data.get("name", code)
        )
    except TrafficSourceCodeConflictError:
        await message.answer(
            _("admin.source_code_exists"), reply_markup=cancel_only_keyboard(_)
        )
        return
    await state.clear()
    await message.answer(_("admin.source_created"))
    await render_source_detail(
        message.answer, session, bot, source, admin_id=admin.id, translator=_
    )


@router.callback_query(AdminSourceActionCallback.filter(F.action == "toggle"))
async def on_source_toggle(
    callback: CallbackQuery,
    callback_data: AdminSourceActionCallback,
    session: AsyncSession,
    bot: Bot,
    admin: Admin | None,
    _: Callable,
) -> None:
    if admin is None or not await require_admin(
        callback, admin, _, roles=MANAGEMENT_ROLES, session=session
    ):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    source = await _get_source_or_alert(callback, session, callback_data.source_id, _)
    if source is None:
        return
    source = await traffic_source_service.update_source(
        session,
        admin_id=admin.id,
        source_id=source.id,
        name=None,
        active=not source.is_active,
    )
    await render_source_detail(
        message.edit_text, session, bot, source, admin_id=admin.id, translator=_
    )
    await callback.answer()
