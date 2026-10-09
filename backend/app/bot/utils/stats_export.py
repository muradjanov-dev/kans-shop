from collections.abc import Callable
from io import BytesIO

from openpyxl import Workbook

from app.bot.utils.i18n import translate
from app.services.stats_service import AdminStats

_PERIOD_LABEL_KEYS = {
    "today": "admin.stats_period_today",
    "week": "admin.stats_period_week",
    "month": "admin.stats_period_month",
}


def build_stats_workbook(
    stats: AdminStats, *, translator: Callable[..., str] | None = None
) -> BytesIO:
    if translator is None:

        def translate_uz(key: str, **values: object) -> str:
            return translate("uz", key, **values)

        translator = translate_uz

    wb = Workbook()
    ws = wb.active
    ws.title = translator("admin.stats_xlsx_sheet_title")

    ws.append(
        [
            translator("admin.stats_xlsx_metrics_heading"),
            translator("admin.stats_xlsx_value_heading"),
        ]
    )
    period_label_key = _PERIOD_LABEL_KEYS.get(stats.period)
    period_label = translator(period_label_key) if period_label_key else stats.period
    ws.append([translator("admin.stats_xlsx_period"), period_label])
    ws.append(
        [translator("admin.stats_xlsx_start_utc"), stats.since.strftime("%Y-%m-%d %H:%M")]
    )
    ws.append([translator("admin.stats_xlsx_end_utc"), stats.until.strftime("%Y-%m-%d %H:%M")])
    ws.append([translator("admin.stats_xlsx_orders_count"), stats.orders_count])
    amount_label = translator(
        "admin.stats_xlsx_amount_format",
        label=translator("admin.stats_order_value_label"),
    )
    paid_amount_label = translator(
        "admin.stats_xlsx_amount_format",
        label=translator("admin.stats_paid_amount_label"),
    )
    ws.append([amount_label, float(stats.order_value)])
    ws.append([paid_amount_label, float(stats.paid_amount)])
    ws.append([translator("admin.stats_xlsx_avg_check"), float(stats.avg_check)])
    ws.append([translator("admin.stats_xlsx_new_users"), stats.new_users])
    ws.append([])
    ws.append(
        [
            translator("admin.stats_xlsx_top_products"),
            translator("admin.stats_xlsx_sold"),
        ]
    )
    for product in stats.top_products:
        ws.append([product.name, product.sold])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
