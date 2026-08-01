from io import BytesIO

from openpyxl import Workbook

from app.services.stats_service import StatsResult


def build_stats_workbook(stats: StatsResult) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Statistika"

    ws.append(["Ko'rsatkich", "Qiymat"])
    ws.append(["Davr", stats.period])
    ws.append(["Boshlanish sanasi", stats.since.strftime("%Y-%m-%d %H:%M")])
    ws.append(["Buyurtmalar soni", stats.orders_count])
    ws.append(["Tushum (so'm)", float(stats.revenue)])
    ws.append(["O'rtacha chek (so'm)", float(stats.avg_check)])
    ws.append(["Yangi foydalanuvchilar", stats.new_users])
    ws.append([])
    ws.append(["Top mahsulotlar", "Sotildi (dona)"])
    for product in stats.top_products:
        ws.append([product.name, product.sold])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
