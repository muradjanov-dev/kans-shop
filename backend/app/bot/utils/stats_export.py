from io import BytesIO

from openpyxl import Workbook

from app.services.stats_service import AdminStats


def build_stats_workbook(stats: AdminStats) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Statistika"

    ws.append(["Ko'rsatkich", "Qiymat"])
    ws.append(["Davr", stats.period])
    ws.append(["Boshlanish (UTC)", stats.since.strftime("%Y-%m-%d %H:%M")])
    ws.append(["Tugash (UTC)", stats.until.strftime("%Y-%m-%d %H:%M")])
    ws.append(["Buyurtmalar soni", stats.orders_count])
    ws.append(["Bekor qilinmagan buyurtmalar summasi (so'm)", float(stats.order_value)])
    ws.append(["To'langan summa (so'm)", float(stats.paid_amount)])
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
