from collections.abc import AsyncGenerator
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_db
from app.core.security import create_access_token
from app.db.models.admin import Admin
from app.db.models.cart import Cart, CartItem
from app.db.models.category import Category
from app.db.models.enums import AdminRole, ProductUnit
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.setting import Setting
from app.db.models.user import User
from app.db.repositories import setting_repository
from app.main import create_app
from app.services.after_commit import commit_with_after_commit, register_after_commit


async def test_commit_failure_sends_no_notification() -> None:
    events: list[str] = []

    class CommitFailureSession:
        def __init__(self) -> None:
            self.info: dict = {}

        async def commit(self) -> None:
            events.append("commit_failed")
            raise RuntimeError("database unavailable")

    async def notify() -> None:
        events.append("telegram_send_started")

    session = CommitFailureSession()
    register_after_commit(session, notify)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="database unavailable"):
        await commit_with_after_commit(session)  # type: ignore[arg-type]

    assert events == ["commit_failed"]
    assert not session.info


async def _exercise_checkout_commit_order(
    test_engine, monkeypatch, fail_notification: bool
) -> None:
    events: list[str] = []

    class RecordingSession(AsyncSession):
        async def commit(self) -> None:
            await super().commit()
            events.append("commit_finished")

    session_maker = async_sessionmaker(
        test_engine, class_=RecordingSession, expire_on_commit=False
    )
    suffix = uuid4().hex[:12]
    telegram_id = 8_200_000_000_000_000 + int(suffix, 16)
    category = Category(
        name_uz="Test category",
        name_ru="Test category",
        slug=f"after-commit-{suffix}",
    )
    customer = User(telegram_id=telegram_id, first_name="Checkout customer", language="uz")
    admin_user = User(telegram_id=telegram_id + 1, first_name="Test admin", language="uz")
    admin = Admin(
        telegram_id=telegram_id + 1,
        full_name="Test admin",
        role=AdminRole.SUPERADMIN,
    )
    saved_settings: dict[str, object] = {}
    setting_values = {
        "is_shop_open": True,
        "min_order_amount": 0,
        "delivery_fee": 0,
        "free_delivery_from": 0,
    }

    async with session_maker() as session:
        session.add_all([category, customer, admin_user, admin])
        await session.flush()
        product = Product(
            category_id=category.id,
            name_uz="Test pen",
            name_ru="Test pen",
            sku=f"AFTER-COMMIT-{suffix}",
            price=5000,
            stock_qty=10,
            unit=ProductUnit.DONA,
        )
        session.add(product)
        await session.flush()
        session.add(
            CartItem(
                cart=Cart(user_id=customer.id, is_active=True),
                product_id=product.id,
                quantity=1,
                price_snapshot=product.price,
            )
        )
        existing = await setting_repository.get_all(session)
        saved_settings = {key: existing[key] for key in setting_values if key in existing}
        for key, value in setting_values.items():
            await setting_repository.set_value(session, key, value)
        await session.commit()
        customer_id = customer.id
        product_id = product.id
        category_id = category.id
        admin_user_id = admin_user.id
        admin_id = admin.id

    events.clear()

    class FakeBot:
        async def send_message(self, chat_id: int, text: str, **kwargs: object):
            events.append("telegram_send_started")
            if fail_notification:
                raise RuntimeError("synthetic Telegram failure")
            return SimpleNamespace(message_id=44)

    app = create_app()
    app.state.bot = FakeBot()
    app.state.session_maker = session_maker

    async def test_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await commit_with_after_commit(session)
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = test_get_db

    class FakeRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}

        async def incr(self, key: str) -> int:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, key: str, seconds: int) -> bool:
            return key in self.counts and seconds > 0

    monkeypatch.setattr("app.api.rate_limit.get_redis", lambda: FakeRedis())

    class ResponseRecorder:
        def __init__(self, application) -> None:
            self.application = application

        async def __call__(self, scope, receive, send) -> None:
            async def record_send(message) -> None:
                if message["type"] == "http.response.start" and message["status"] in (
                    200,
                    201,
                ):
                    events.append("http_success_sent")
                await send(message)

            await self.application(scope, receive, record_send)

    from app.bot.services import order_notifications

    original_session_maker = order_notifications.async_session_maker
    order_notifications.async_session_maker = session_maker
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ResponseRecorder(app)),
        base_url="http://testserver",
    )
    token = create_access_token(user_id=customer_id, telegram_id=telegram_id)
    key = str(uuid4())
    try:
        response = await client.post(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
            json={
                "order_type": "pickup",
                "customer_name": "Checkout customer",
                "customer_phone": "+998901234567",
                "payment_method": "cash",
            },
        )
        assert response.status_code == 201
        assert events.index("commit_finished") < events.index("telegram_send_started")
        assert events.index("commit_finished") < events.index("http_success_sent")

        async with session_maker() as session:
            created_order = await session.scalar(
                select(Order).where(Order.user_id == customer_id)
            )
        assert created_order is not None
        if fail_notification:
            assert not created_order.admin_message_ids
        else:
            assert created_order.admin_message_ids == {str(telegram_id + 1): 44}
    finally:
        await client.aclose()
        order_notifications.async_session_maker = original_session_maker
        app.dependency_overrides.clear()
        async with session_maker() as session:
            await session.execute(delete(Order).where(Order.user_id == customer_id))
            await session.execute(delete(Cart).where(Cart.user_id == customer_id))
            await session.execute(delete(Admin).where(Admin.id == admin_id))
            await session.execute(
                delete(User).where(User.id.in_([customer_id, admin_user_id]))
            )
            await session.execute(delete(Product).where(Product.id == product_id))
            await session.execute(delete(Category).where(Category.id == category_id))
            for key_name, _value in setting_values.items():
                if key_name in saved_settings:
                    await setting_repository.set_value(
                        session, key_name, saved_settings[key_name]
                    )
                else:
                    await session.execute(delete(Setting).where(Setting.key == key_name))
            await session.commit()


async def test_success_response_follows_commit(test_engine, monkeypatch) -> None:
    await _exercise_checkout_commit_order(test_engine, monkeypatch, fail_notification=False)


async def test_notification_failure_preserves_order(test_engine, monkeypatch) -> None:
    await _exercise_checkout_commit_order(test_engine, monkeypatch, fail_notification=True)


async def test_checkout_replay_skips_new_notification(test_engine, monkeypatch) -> None:
    events: list[str] = []

    class RecordingSession(AsyncSession):
        async def commit(self) -> None:
            await super().commit()
            events.append("commit_finished")

    session_maker = async_sessionmaker(
        test_engine, class_=RecordingSession, expire_on_commit=False
    )
    suffix = uuid4().hex[:12]
    telegram_id = 8_300_000_000_000_000 + int(suffix, 16)
    category = Category(
        name_uz="Replay category", name_ru="Replay category", slug=f"replay-{suffix}"
    )
    customer = User(telegram_id=telegram_id, first_name="Replay customer", language="uz")
    admin_user = User(telegram_id=telegram_id + 1, first_name="Test admin", language="uz")
    admin = Admin(
        telegram_id=telegram_id + 1,
        full_name="Test admin",
        role=AdminRole.SUPERADMIN,
    )
    setting_values = {
        "is_shop_open": True,
        "min_order_amount": 0,
        "delivery_fee": 0,
        "free_delivery_from": 0,
    }
    saved_settings: dict[str, object] = {}
    async with session_maker() as session:
        session.add_all([category, customer, admin_user, admin])
        await session.flush()
        product = Product(
            category_id=category.id,
            name_uz="Replay pen",
            name_ru="Replay pen",
            sku=f"REPLAY-{suffix}",
            price=5000,
            stock_qty=10,
            unit=ProductUnit.DONA,
        )
        session.add(product)
        await session.flush()
        session.add(
            CartItem(
                cart=Cart(user_id=customer.id, is_active=True),
                product_id=product.id,
                quantity=1,
                price_snapshot=product.price,
            )
        )
        existing = await setting_repository.get_all(session)
        saved_settings = {key: existing[key] for key in setting_values if key in existing}
        for key, value in setting_values.items():
            await setting_repository.set_value(session, key, value)
        await session.commit()
        customer_id = customer.id
        product_id = product.id
        category_id = category.id
        admin_user_id = admin_user.id
        admin_id = admin.id

    class FakeBot:
        async def send_message(self, chat_id: int, text: str, **kwargs: object):
            events.append("telegram_send_started")
            return SimpleNamespace(message_id=45)

    app = create_app()
    app.state.bot = FakeBot()
    app.state.session_maker = session_maker

    async def test_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await commit_with_after_commit(session)
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = test_get_db

    class FakeRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}

        async def incr(self, key: str) -> int:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, key: str, seconds: int) -> bool:
            return key in self.counts and seconds > 0

    fake_redis = FakeRedis()
    monkeypatch.setattr("app.api.rate_limit.get_redis", lambda: fake_redis)
    from app.bot.services import order_notifications

    original_session_maker = order_notifications.async_session_maker
    order_notifications.async_session_maker = session_maker
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )
    token = create_access_token(user_id=customer_id, telegram_id=telegram_id)
    key = str(uuid4())
    payload = {
        "order_type": "pickup",
        "customer_name": "Replay customer",
        "customer_phone": "+998901234567",
        "payment_method": "cash",
    }
    try:
        first = await client.post(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
            json=payload,
        )
        sends_after_first = events.count("telegram_send_started")
        second = await client.post(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
            json=payload,
        )
        assert first.status_code == 201
        assert second.status_code == 200
        assert sends_after_first == 1
        assert events.count("telegram_send_started") == sends_after_first
    finally:
        await client.aclose()
        order_notifications.async_session_maker = original_session_maker
        app.dependency_overrides.clear()
        async with session_maker() as session:
            await session.execute(delete(Order).where(Order.user_id == customer_id))
            await session.execute(delete(Cart).where(Cart.user_id == customer_id))
            await session.execute(delete(Admin).where(Admin.id == admin_id))
            await session.execute(
                delete(User).where(User.id.in_([customer_id, admin_user_id]))
            )
            await session.execute(delete(Product).where(Product.id == product_id))
            await session.execute(delete(Category).where(Category.id == category_id))
            for key_name, _value in setting_values.items():
                if key_name in saved_settings:
                    await setting_repository.set_value(
                        session, key_name, saved_settings[key_name]
                    )
                else:
                    await session.execute(delete(Setting).where(Setting.key == key_name))
            await session.commit()
