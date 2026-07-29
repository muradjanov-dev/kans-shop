"""One-shot seed script: demo categories, demo products, and superadmins from ADMIN_IDS.

Idempotent — safe to run multiple times (upserts by unique key: slug / sku / telegram_id).
Usage: python -m app.db.seed
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models.admin import Admin
from app.db.models.category import Category
from app.db.models.enums import AdminRole, ProductUnit
from app.db.models.product import Product
from app.db.models.setting import Setting
from app.db.session import async_session_maker

log = get_logger(__name__)

CATEGORIES = [
    {
        "slug": "yozuv-qurollari",
        "name_uz": "Yozuv qurollari",
        "name_ru": "Письменные принадлежности",
    },
    {
        "slug": "qogoz-mahsulotlari",
        "name_uz": "Qog'oz mahsulotlari",
        "name_ru": "Бумажная продукция",
    },
    {
        "slug": "maktab-buyumlari",
        "name_uz": "Maktab buyumlari",
        "name_ru": "Школьные товары",
    },
    {
        "slug": "ofis-texnikasi-aksessuarlari",
        "name_uz": "Ofis texnikasi aksessuarlari",
        "name_ru": "Аксессуары для офисной техники",
    },
    {
        "slug": "papkalar-va-tashkilotchilar",
        "name_uz": "Papkalar va tashkilotchilar",
        "name_ru": "Папки и органайзеры",
    },
]

PRODUCTS = [
    # (slug of category, sku, name_uz, name_ru, price, old_price, stock, unit, featured)
    (
        "yozuv-qurollari",
        "PEN-PILOT-BLUE",
        "Ruchka Pilot ko'k",
        "Ручка Pilot синяя",
        "5000",
        None,
        500,
        ProductUnit.DONA,
        True,
    ),
    (
        "yozuv-qurollari",
        "PEN-PILOT-BLACK",
        "Ruchka Pilot qora",
        "Ручка Pilot чёрная",
        "5000",
        None,
        500,
        ProductUnit.DONA,
        False,
    ),
    (
        "yozuv-qurollari",
        "PENCIL-HB",
        "Grifel qalam HB",
        "Карандаш HB",
        "2000",
        "2500",
        800,
        ProductUnit.DONA,
        False,
    ),
    (
        "yozuv-qurollari",
        "MARKER-SET-6",
        "Markёr to'plami (6 rang)",
        "Набор маркеров (6 цветов)",
        "35000",
        None,
        120,
        ProductUnit.KOMPLEKT,
        True,
    ),
    (
        "qogoz-mahsulotlari",
        "A4-SVETOCOPY",
        "A4 qog'oz Svetocopy 500 varaq",
        "Бумага A4 Svetocopy 500 листов",
        "65000",
        "72000",
        300,
        ProductUnit.QUTI,
        True,
    ),
    (
        "qogoz-mahsulotlari",
        "NOTEBOOK-96",
        "Daftar 96 varaq katakli",
        "Тетрадь 96 листов клетка",
        "18000",
        None,
        400,
        ProductUnit.DONA,
        False,
    ),
    (
        "qogoz-mahsulotlari",
        "STICKY-NOTES",
        "Yopishqoq qog'oz (stikkerlar)",
        "Стикеры для заметок",
        "12000",
        None,
        250,
        ProductUnit.PAKET,
        False,
    ),
    (
        "maktab-buyumlari",
        "BACKPACK-SCHOOL",
        "Maktab ryukzagi",
        "Школьный рюкзак",
        "180000",
        "210000",
        60,
        ProductUnit.DONA,
        True,
    ),
    (
        "maktab-buyumlari",
        "PENCIL-CASE",
        "Qalamdon",
        "Пенал",
        "25000",
        None,
        150,
        ProductUnit.DONA,
        False,
    ),
    (
        "maktab-buyumlari",
        "RULER-SET",
        "Chizg'ich to'plami",
        "Набор линеек",
        "8000",
        None,
        300,
        ProductUnit.KOMPLEKT,
        False,
    ),
    (
        "ofis-texnikasi-aksessuarlari",
        "PRINTER-CARTRIDGE-HP",
        "Printer kartriji HP 12A",
        "Картридж для принтера HP 12A",
        "220000",
        None,
        40,
        ProductUnit.DONA,
        True,
    ),
    (
        "ofis-texnikasi-aksessuarlari",
        "USB-FLASH-32",
        "USB flesh xotira 32GB",
        "USB флеш-накопитель 32ГБ",
        "45000",
        None,
        90,
        ProductUnit.DONA,
        False,
    ),
    (
        "ofis-texnikasi-aksessuarlari",
        "CALCULATOR-BASIC",
        "Kalkulyator",
        "Калькулятор",
        "38000",
        None,
        70,
        ProductUnit.DONA,
        False,
    ),
    (
        "papkalar-va-tashkilotchilar",
        "FOLDER-RING-A4",
        "Halqali papka A4",
        "Папка-регистратор A4",
        "22000",
        None,
        200,
        ProductUnit.DONA,
        True,
    ),
    (
        "papkalar-va-tashkilotchilar",
        "FILE-CLEAR-100",
        "Fayl-tirqich (100 dona)",
        "Файлы-вкладыши (100 шт)",
        "28000",
        "32000",
        180,
        ProductUnit.PAKET,
        False,
    ),
]

DEFAULT_SETTINGS = [
    ("delivery_fee", 20000, "Standart yetkazib berish narxi (so'm)"),
    ("free_delivery_from", 300000, "Shu summadan yuqori bepul yetkazib berish (so'm)"),
    ("min_order_amount", 30000, "Minimal buyurtma summasi (so'm)"),
    ("work_hours", "09:00-19:00", "Ish vaqti"),
    ("card_number", "8600 0000 0000 0000", "To'lov uchun karta raqami"),
    ("card_holder", "KANS SHOP MCHJ", "Karta egasi"),
    ("support_username", "kansshop_support", "Qo'llab-quvvatlash Telegram username"),
    ("shop_phone", "+998901234567", "Do'kon telefon raqami"),
    ("is_shop_open", True, "Do'kon hozir buyurtma qabul qilyaptimi"),
    (
        "welcome_text_uz",
        "Kans Shop'ga xush kelibsiz! Ofis va maktab buyumlari uchun ishonchli manzil.",
        "Salomlashuv matni (uz)",
    ),
    (
        "welcome_text_ru",
        "Добро пожаловать в Kans Shop! Надёжный магазин канцтоваров.",
        "Приветственный текст (ru)",
    ),
]


async def seed_categories(session) -> dict[str, int]:
    slug_to_id: dict[str, int] = {}
    for order, cat in enumerate(CATEGORIES):
        existing = await session.scalar(select(Category).where(Category.slug == cat["slug"]))
        if existing:
            slug_to_id[cat["slug"]] = existing.id
            continue
        category = Category(
            name_uz=cat["name_uz"],
            name_ru=cat["name_ru"],
            slug=cat["slug"],
            sort_order=order,
        )
        session.add(category)
        await session.flush()
        slug_to_id[cat["slug"]] = category.id
        log.info("category_seeded", slug=cat["slug"])
    return slug_to_id


async def seed_products(session, slug_to_id: dict[str, int]) -> None:
    counts: dict[int, int] = {}
    for (
        cat_slug,
        sku,
        name_uz,
        name_ru,
        price,
        old_price,
        stock,
        unit,
        featured,
    ) in PRODUCTS:
        existing = await session.scalar(select(Product).where(Product.sku == sku))
        category_id = slug_to_id[cat_slug]
        if existing:
            counts[category_id] = counts.get(category_id, 0) + 1
            continue
        product = Product(
            category_id=category_id,
            name_uz=name_uz,
            name_ru=name_ru,
            sku=sku,
            price=Decimal(price),
            old_price=Decimal(old_price) if old_price else None,
            stock_qty=stock,
            unit=unit,
            is_featured=featured,
        )
        session.add(product)
        counts[category_id] = counts.get(category_id, 0) + 1
        log.info("product_seeded", sku=sku)

    for category_id, count in counts.items():
        category = await session.get(Category, category_id)
        if category:
            category.products_count = count


async def seed_settings(session) -> None:
    for key, value, description in DEFAULT_SETTINGS:
        existing = await session.scalar(select(Setting).where(Setting.key == key))
        if existing:
            continue
        session.add(Setting(key=key, value=value, description=description))
        log.info("setting_seeded", key=key)


async def seed_admins(session) -> None:
    for telegram_id in settings.admin_ids_list:
        existing = await session.scalar(select(Admin).where(Admin.telegram_id == telegram_id))
        if existing:
            continue
        session.add(
            Admin(
                telegram_id=telegram_id,
                full_name=f"Superadmin {telegram_id}",
                role=AdminRole.SUPERADMIN,
            )
        )
        log.info("superadmin_seeded", telegram_id=telegram_id)


async def run_seed() -> None:
    async with async_session_maker() as session, session.begin():
        slug_to_id = await seed_categories(session)
        await seed_products(session, slug_to_id)
        await seed_settings(session)
        await seed_admins(session)
    log.info("seed_complete")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run_seed())
