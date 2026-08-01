from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import Admin
from app.db.models.enums import OrderType
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.services import cart_service, order_service
from app.services.stats_service import get_stats


async def _checkout(session: AsyncSession, user: User, product: Product, qty: int = 1):
    await setting_repository.set_value(session, "min_order_amount", 0)
    await cart_service.add_item(session, user.id, product.id, quantity=qty)
    return await order_service.checkout(
        session,
        user_id=user.id,
        order_type=OrderType.DELIVERY,
        customer_name="Test Customer",
        customer_phone="+998901234567",
        address="Chilonzor 9",
    )


async def test_get_stats_counts_orders_and_revenue(
    db_session: AsyncSession, user: User, product: Product
) -> None:
    await _checkout(db_session, user, product, qty=2)

    stats = await get_stats(db_session, "today")

    assert stats.orders_count == 1
    assert stats.revenue == Decimal("5000") * 2
    assert stats.avg_check == Decimal("5000") * 2
    assert stats.top_products
    assert stats.top_products[0].name == product.name_uz
    assert stats.top_products[0].sold == 2


async def test_get_stats_excludes_cancelled_orders_from_revenue(
    db_session: AsyncSession, user: User, product: Product, admin: Admin
) -> None:
    order = await _checkout(db_session, user, product, qty=1)
    await order_service.cancel_order(db_session, order, admin_id=admin.id, reason="test")

    stats = await get_stats(db_session, "today")

    assert stats.orders_count == 1  # still counted as an order created today
    assert stats.revenue == Decimal("0")  # but excluded from revenue
    assert stats.avg_check == Decimal("0")
    assert stats.top_products == []


async def test_get_stats_counts_new_users(db_session: AsyncSession, user: User) -> None:
    stats = await get_stats(db_session, "today")
    assert stats.new_users >= 1


async def test_get_stats_zero_orders_has_no_division_error(db_session: AsyncSession) -> None:
    stats = await get_stats(db_session, "today")
    assert stats.orders_count == 0
    assert stats.avg_check == Decimal("0")
