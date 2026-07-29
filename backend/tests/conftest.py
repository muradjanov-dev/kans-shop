import os
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base
from app.db.models.admin import Admin
from app.db.models.category import Category
from app.db.models.enums import AdminRole, ProductUnit
from app.db.models.product import Product
from app.db.models.user import User

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://kansshop:kansshop@localhost:5432/kansshop_test",
)


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        await conn.exec_driver_sql(
            "CREATE SEQUENCE IF NOT EXISTS kans_order_seq START WITH 1 INCREMENT BY 1"
        )
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.exec_driver_sql("DROP SEQUENCE IF EXISTS kans_order_seq")
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Each test runs inside a savepoint on a single connection, rolled back afterward —
    tests never see each other's data and the schema is only built once per session."""
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session_maker = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with session_maker() as session:
            yield session
        await trans.rollback()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(telegram_id=111111, first_name="Test", language="uz")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> Admin:
    a = Admin(telegram_id=917456291, full_name="Test Admin", role=AdminRole.SUPERADMIN)
    db_session.add(a)
    await db_session.flush()
    return a


@pytest_asyncio.fixture
async def category(db_session: AsyncSession) -> Category:
    c = Category(
        name_uz="Yozuv qurollari", name_ru="Письменные принадлежности", slug="test-cat"
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def product(db_session: AsyncSession, category: Category) -> Product:
    p = Product(
        category_id=category.id,
        name_uz="Ruchka",
        name_ru="Ручка",
        sku="TEST-SKU-1",
        price=Decimal("5000"),
        stock_qty=10,
        unit=ProductUnit.DONA,
    )
    db_session.add(p)
    await db_session.flush()
    return p
