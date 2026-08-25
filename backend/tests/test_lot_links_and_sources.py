"""Data-level behaviour of the two new order/marketing features."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category import Category
from app.db.models.enums import OrderStatus, OrderType, ProductUnit
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories import setting_repository, traffic_source_repository
from app.services import cart_service, order_service


async def _product(
    session: AsyncSession, category: Category, sku: str, *, lot_url: str | None
) -> Product:
    product = Product(
        category_id=category.id,
        name_uz=f"Mahsulot {sku}",
        name_ru=f"Товар {sku}",
        sku=sku,
        price=Decimal("10000"),
        stock_qty=50,
        unit=ProductUnit.DONA,
        lot_url=lot_url,
    )
    session.add(product)
    await session.flush()
    return product


async def _checkout(session: AsyncSession, user: User):
    await setting_repository.set_value(session, "min_order_amount", 0)
    return await order_service.checkout(
        session,
        user_id=user.id,
        order_type=OrderType.PICKUP,
        customer_name="Test",
        customer_phone="+998901234567",
    )


async def test_lot_links_splits_items_with_and_without_a_lot_page(
    db_session: AsyncSession, user: User, category: Category
) -> None:
    with_lot = await _product(db_session, category, "LOT-1", lot_url="https://lot.example/1")
    without_lot = await _product(db_session, category, "LOT-2", lot_url=None)
    await cart_service.add_item(db_session, user.id, with_lot.id, quantity=1)
    await cart_service.add_item(db_session, user.id, without_lot.id, quantity=2)

    order = await _checkout(db_session, user)
    links, missing = await order_service.lot_links(db_session, order)

    assert [(link.product_name, link.url) for link in links] == [
        (with_lot.name_uz, "https://lot.example/1")
    ]
    assert missing == [without_lot.name_uz]


async def test_lot_links_uses_the_current_url_not_an_order_snapshot(
    db_session: AsyncSession, user: User, category: Category
) -> None:
    """A lot page can move after the order is placed; the customer must get the live link."""
    product = await _product(db_session, category, "LOT-3", lot_url="https://lot.example/old")
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)
    order = await _checkout(db_session, user)

    product.lot_url = "https://lot.example/new"
    await db_session.flush()

    links, _missing = await order_service.lot_links(db_session, order)
    assert links[0].url == "https://lot.example/new"


async def test_lot_links_is_empty_for_an_order_with_no_lot_products(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await cart_service.add_item(db_session, user.id, product.id, quantity=1)
    order = await _checkout(db_session, user)

    links, missing = await order_service.lot_links(db_session, order)
    assert links == []
    assert missing == [product.name_uz]


async def test_source_stats_count_only_attributed_users(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    source = await traffic_source_repository.create(
        db_session, code="instagram", name="Instagram"
    )
    other = User(telegram_id=999001, first_name="Unattributed", language="uz")
    db_session.add(other)
    await db_session.flush()

    user.traffic_source_id = source.id
    await db_session.flush()

    await cart_service.add_item(db_session, user.id, product.id, quantity=2)
    await _checkout(db_session, user)

    stats = await traffic_source_repository.get_stats(db_session, source)
    assert stats.users_count == 1
    assert stats.orders_count == 1
    assert stats.revenue == Decimal("10000")


async def test_cancelled_orders_are_excluded_from_source_revenue(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    source = await traffic_source_repository.create(db_session, code="bozor", name="Bozor")
    user.traffic_source_id = source.id
    await db_session.flush()

    await cart_service.add_item(db_session, user.id, product.id, quantity=1)
    order = await _checkout(db_session, user)
    await order_service.cancel_order(db_session, order, admin_id=None, reason="test")

    stats = await traffic_source_repository.get_stats(db_session, source)
    assert stats.orders_count == 1, "the order still happened"
    assert stats.revenue == Decimal("0"), "but cancelled revenue must not be counted"
    assert order.status == OrderStatus.CANCELLED


async def test_increment_clicks_is_an_atomic_update(
    db_session: AsyncSession,
) -> None:
    source = await traffic_source_repository.create(db_session, code="qr", name="QR")
    for _ in range(3):
        await traffic_source_repository.increment_clicks(db_session, source.id)
    await db_session.refresh(source)

    assert source.clicks_count == 3


async def test_code_lookup_is_case_insensitive(db_session: AsyncSession) -> None:
    """Codes are stored lowercase so a link typed with capitals still resolves."""
    await traffic_source_repository.create(db_session, code="telegram", name="Telegram")

    assert await traffic_source_repository.get_by_code(db_session, "TELEGRAM") is not None
    assert await traffic_source_repository.get_by_code(db_session, "telegram") is not None
