from collections.abc import Awaitable, Callable
from decimal import Decimal

from aiogram import Bot, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import StatsExportCallback, StatsPeriodCallback
from app.bot.keyboards.inline.admin_stats import stats_keyboard
from app.bot.utils.admin_guard import require_admin
from app.bot.utils.messages import require_message
from app.bot.utils.stats_export import build_stats_workbook
from app.db.models.admin import Admin
from app.services.stats_service import StatsResult, get_stats

router = Router(name="admin_stats")

Sender = Callable[..., Awaitable[object]]

PERIOD_LABEL_KEYS = {
    "today": "admin.stats_period_today",
    "week": "admin.stats_period_week",
    "month": "admin.stats_period_month",
}


def _format_price(value: Decimal) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _render_stats_text(stats: StatsResult, translator: Callable[..., str]) -> str:
    text = translator(
        "admin.stats_summary",
        period=translator(PERIOD_LABEL_KEYS[stats.period]),
        orders_count=stats.orders_count,
        revenue=_format_price(stats.revenue),
        avg_check=_format_price(stats.avg_check),
        new_users=stats.new_users,
    )
    if stats.top_products:
        text += translator("admin.stats_top_products_header")
        for idx, product in enumerate(stats.top_products, start=1):
            text += "\n" + translator(
                "admin.stats_top_product_line", index=idx, name=product.name, sold=product.sold
            )
    return text


async def render_stats(
    send: Sender, session: AsyncSession, period: str, translator: Callable[..., str]
) -> None:
    stats = await get_stats(session, period)
    await send(
        _render_stats_text(stats, translator),
        reply_markup=stats_keyboard(translator, period=period),
    )


@router.callback_query(StatsPeriodCallback.filter())
async def on_stats_period(
    callback: CallbackQuery,
    callback_data: StatsPeriodCallback,
    session: AsyncSession,
    admin: Admin | None,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return
    await render_stats(message.edit_text, session, callback_data.period, _)
    await callback.answer()


@router.callback_query(StatsExportCallback.filter())
async def on_stats_export(
    callback: CallbackQuery,
    callback_data: StatsExportCallback,
    session: AsyncSession,
    admin: Admin | None,
    bot: Bot,
    _: Callable,
) -> None:
    if not await require_admin(callback, admin, _):
        return
    message = await require_message(callback, _)
    if message is None:
        return

    stats = await get_stats(session, callback_data.period)
    buffer = build_stats_workbook(stats)
    filename = f"stats_{callback_data.period}.xlsx"
    await bot.send_document(
        message.chat.id,
        BufferedInputFile(buffer.read(), filename=filename),
        caption=_("admin.stats_export_caption"),
    )
    await callback.answer()
