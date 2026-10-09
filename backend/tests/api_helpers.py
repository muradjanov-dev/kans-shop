from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from secrets import randbelow, token_hex
from unittest.mock import patch

import httpx
from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.api.deps import get_db
from app.core.security import create_access_token
from app.db.models.category import Category
from app.db.models.enums import ProductUnit
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.models.user import User
from app.main import create_app

IMAGE_URL = "https://cdn.example.test/products/test-image.jpg"


class FakeBot:
    """A placeholder bot for app state; cart API requests never call Telegram."""


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return key in self.counts and seconds > 0


@dataclass
class ApiCase:
    client: httpx.AsyncClient
    session_maker: async_sessionmaker[AsyncSession]
    user_id: int
    other_user_id: int
    product_id: int
    token: str
    other_token: str
    fake_bot: FakeBot


@asynccontextmanager
async def make_api_case(test_engine: AsyncEngine) -> AsyncIterator[ApiCase]:
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    suffix = token_hex(8)
    telegram_id = 8_000_000_000_000_000 + randbelow(100_000_000)
    category = Category(
        name_uz="Test category",
        name_ru="Test category",
        slug=f"api-cart-{suffix}",
    )
    user = User(telegram_id=telegram_id, first_name="Cart API test", language="uz")
    other_user = User(
        telegram_id=telegram_id + 1,
        first_name="Other cart API test",
        language="uz",
    )
    async with session_maker() as session:
        session.add_all([category, user, other_user])
        await session.flush()
        product = Product(
            category_id=category.id,
            name_uz="Test pen",
            name_ru="Test pen",
            sku=f"API-CART-{suffix}",
            price=Decimal("5000"),
            stock_qty=10,
            unit=ProductUnit.DONA,
        )
        session.add(product)
        await session.flush()
        image = ProductImage(
            product_id=product.id,
            url=IMAGE_URL,
            telegram_file_id="synthetic-file-id",
            is_main=True,
            sort_order=0,
        )
        session.add(image)
        await session.commit()
        user_id = user.id
        other_user_id = other_user.id
        product_id = product.id

    app = create_app()
    fake_bot = FakeBot()
    fake_redis = FakeRedis()
    app.state.bot = fake_bot
    app.state.session_maker = session_maker

    async def get_case_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
        async with request.app.state.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = get_case_db
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )
    tokens = (
        create_access_token(user_id=user_id, telegram_id=telegram_id),
        create_access_token(user_id=other_user_id, telegram_id=telegram_id + 1),
    )
    try:
        with patch("app.api.rate_limit.get_redis", return_value=fake_redis):
            yield ApiCase(
                client=client,
                session_maker=session_maker,
                user_id=user_id,
                other_user_id=other_user_id,
                product_id=product_id,
                token=tokens[0],
                other_token=tokens[1],
                fake_bot=fake_bot,
            )
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        async with session_maker() as session:
            await session.execute(
                ProductImage.__table__.delete().where(ProductImage.product_id == product_id)
            )
            await session.execute(Product.__table__.delete().where(Product.id == product_id))
            await session.execute(
                User.__table__.delete().where(User.id.in_([user_id, other_user_id]))
            )
            await session.execute(
                Category.__table__.delete().where(Category.id == category.id)
            )
            await session.commit()
