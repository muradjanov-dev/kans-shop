import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.admin_order_message import AdminOrderMessage
from app.db.models.enums import (
    AdminRole,
    NotificationOutboxStatus,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from app.db.models.notification_outbox import NotificationOutbox
from app.db.models.order import Order
from app.db.models.traffic_source import TrafficSource
from app.db.models.user import User
from app.services.notification_outbox_service import enqueue_outbox_event
from app.services.notification_outbox_worker import (
    ack_outbox,
    claim_outbox_batch,
    run_outbox_worker,
)


def _queue_row(
    *,
    recipient_user_id: int,
    event_type: str = "admin.order_message.queued",
    aggregate_id: int = 1,
    payload_id: int = 1,
    dedupe_key: str | None = None,
) -> NotificationOutbox:
    return NotificationOutbox(
        recipient_user_id=recipient_user_id,
        event_type=event_type,
        aggregate_id=str(aggregate_id),
        payload_id=str(payload_id),
        dedupe_key=dedupe_key or f"outbox-test:{uuid4()}",
        status=NotificationOutboxStatus.PENDING,
        attempts=0,
        next_available_at=datetime.now(UTC),
    )


async def _claim(
    maker: async_sessionmaker[AsyncSession], worker_id: str, *, now: datetime, limit: int = 1
):
    async with maker() as session, session.begin():
        return await claim_outbox_batch(
            session,
            worker_id=worker_id,
            now=now,
            limit=limit,
            lease_seconds=30,
        )


class _FakeRedis:
    async def eval(self, *_args, **_kwargs):
        return 0


class _OutboxMessageBot:
    id = 812345

    def __init__(self, stop: asyncio.Event, *, error: Exception | None = None) -> None:
        self.stop = stop
        self.error = error
        self.messages: list[tuple[int, str, dict]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs):
        self.messages.append((chat_id, text, kwargs))
        if self.error is not None:
            error, self.error = self.error, None
            self.stop.set()
            raise error
        self.stop.set()
        return SimpleNamespace(message_id=999)

    async def send_photo(self, *_args, **_kwargs):
        self.stop.set()

    async def send_document(self, *_args, **_kwargs):
        self.stop.set()

    async def edit_message_text(self, *_args, **_kwargs):
        self.stop.set()


async def _message_case(session: AsyncSession, *, suffix: str):
    user = User(
        telegram_id=8_100_000_000_000_000 + int(suffix[:10], 16),
        first_name="Outbox customer",
        language="uz",
    )
    actor = Admin(
        telegram_id=8_200_000_000_000_000 + int(suffix[:10], 16),
        full_name="Outbox actor",
        role=AdminRole.MANAGER,
    )
    session.add_all([user, actor])
    await session.flush()
    order = Order(
        order_number=f"OUT-{suffix[:10]}",
        user_id=user.id,
        order_type=OrderType.PICKUP,
        customer_name="Outbox customer",
        customer_phone="+998901234567",
        subtotal=1000,
        delivery_fee=0,
        discount=0,
        total=1000,
        payment_method=PaymentMethod.CASH,
        admin_message_ids={},
    )
    session.add(order)
    await session.flush()
    message = AdminOrderMessage(
        order_id=order.id,
        admin_id=actor.id,
        text="Please call me <b>tomorrow</b>.",
        idempotency_key=uuid4(),
    )
    session.add(message)
    await session.flush()
    event = _queue_row(
        recipient_user_id=user.id,
        aggregate_id=order.id,
        payload_id=message.id,
        dedupe_key=f"admin-order-message:{message.id}",
    )
    session.add(event)
    await session.flush()
    return user, actor, order, message, event


async def test_business_rollback_removes_outbox(db_session: AsyncSession, user: User) -> None:
    await enqueue_outbox_event(
        db_session,
        event_type="test.rollback",
        aggregate_id=987654,
        dedupe_key=f"rollback:{uuid4()}",
        recipient_user_id=user.id,
    )
    await db_session.rollback()

    remaining = await db_session.scalar(
        select(NotificationOutbox).where(NotificationOutbox.event_type == "test.rollback")
    )
    assert remaining is None


async def test_two_sessions_claim_distinct_rows(test_engine) -> None:
    suffix = uuid4().hex
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        user = User(
            telegram_id=8_300_000_000_000_000 + int(suffix[:10], 16),
            first_name="Concurrent outbox user",
        )
        session.add(user)
        await session.flush()
        recipient_id = user.id
        session.add_all(
            [
                _queue_row(recipient_user_id=recipient_id, dedupe_key=f"claim-a:{suffix}"),
                _queue_row(recipient_user_id=recipient_id, dedupe_key=f"claim-b:{suffix}"),
            ]
        )
        await session.commit()

    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    first, second = await asyncio.gather(
        _claim(maker, f"worker-a-{suffix}", now=now),
        _claim(maker, f"worker-b-{suffix}", now=now),
    )
    claimed_ids = [claim.event_id for claim in first + second]
    assert len(claimed_ids) == 2
    assert len(set(claimed_ids)) == 2
    async with maker() as session:
        await session.execute(
            delete(NotificationOutbox).where(
                NotificationOutbox.dedupe_key.like(f"claim-%:{suffix}")
            )
        )
        await session.execute(
            delete(User).where(
                User.telegram_id == 8_300_000_000_000_000 + int(suffix[:10], 16)
            )
        )
        await session.commit()


async def test_expired_lease_reclaimed_and_old_token_cannot_ack(test_engine) -> None:
    suffix = uuid4().hex
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        user = User(
            telegram_id=8_400_000_000_000_000 + int(suffix[:10], 16),
            first_name="Lease outbox user",
        )
        session.add(user)
        await session.flush()
        row = _queue_row(recipient_user_id=user.id, dedupe_key=f"lease:{suffix}")
        session.add(row)
        await session.commit()
        event_id = row.id

    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    first_now = datetime.now(UTC)
    first = (await _claim(maker, f"first-{suffix}", now=first_now))[0]
    second = (await _claim(maker, f"second-{suffix}", now=first_now + timedelta(seconds=31)))[
        0
    ]
    assert first.event_id == second.event_id == event_id
    assert first.lease_token != second.lease_token

    async with maker() as session, session.begin():
        stale_lease_ack = await ack_outbox(
            session,
            event_id=event_id,
            lease_token=first.lease_token,
            sent_at=first_now + timedelta(seconds=31),
        )
    assert stale_lease_ack is False

    async with maker() as session, session.begin():
        assert await ack_outbox(
            session,
            event_id=event_id,
            lease_token=second.lease_token,
            sent_at=first_now + timedelta(seconds=31),
        )
    async with maker() as session:
        await session.execute(
            delete(NotificationOutbox).where(NotificationOutbox.id == event_id)
        )
        await session.execute(
            delete(User).where(
                User.telegram_id == 8_400_000_000_000_000 + int(suffix[:10], 16)
            )
        )
        await session.commit()


async def test_restart_sends_pending_outbox(test_engine, monkeypatch) -> None:
    suffix = uuid4().hex
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        user, actor, order, _message, event = await _message_case(session, suffix=suffix)
        user_id, actor_id, order_id, event_id = user.id, actor.id, order.id, event.id

    monkeypatch.setattr(
        "app.services.notification_outbox_worker.acquire_telegram_slot",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )
    stop = asyncio.Event()
    bot = _OutboxMessageBot(stop)
    await run_outbox_worker(bot, maker, _FakeRedis(), stop)

    assert bot.messages == [
        (
            user.telegram_id,
            "Please call me <b>tomorrow</b>.",
            {"reply_markup": None, "parse_mode": None},
        )
    ]
    async with maker() as session:
        row = await session.get(NotificationOutbox, event_id)
        assert row is not None and row.status == NotificationOutboxStatus.SENT
        assert row.sent_at is not None
        assert row.lease_token is None
        assert row.recipient_user_id == user_id
        assert row.aggregate_id == str(order_id)
        saved_message = await session.get(AdminOrderMessage, int(row.payload_id or 0))
        assert saved_message is not None and saved_message.admin_id == actor_id
    async with maker() as session:
        await session.execute(delete(Order).where(Order.id == order_id))
        await session.execute(delete(Admin).where(Admin.id == actor_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_fanout_is_one_row_per_admin(db_session: AsyncSession, user: User) -> None:
    from app.services import (
        order_service,  # Load the service graph before its checkout dependency.
    )
    from app.services.purchase_service import enqueue_order_created_notifications

    assert hasattr(order_service, "enqueue_manual_payment_notification")

    suffix = uuid4().hex
    admins = [
        Admin(
            telegram_id=8_500_000_000_000_000 + int(suffix[:9], 16) * 10 + index,
            full_name=f"Outbox admin {index}",
            role=AdminRole.OPERATOR,
            is_active=True,
            notifications_enabled=True,
        )
        for index in range(2)
    ]
    order = Order(
        order_number=f"FAN-{suffix[:10]}",
        user_id=user.id,
        order_type=OrderType.PICKUP,
        customer_name="Fanout customer",
        customer_phone="+998901234567",
        subtotal=1000,
        delivery_fee=0,
        discount=0,
        total=1000,
        payment_method=PaymentMethod.CASH,
        admin_message_ids={},
    )
    db_session.add_all([*admins, order])
    await db_session.flush()

    await enqueue_order_created_notifications(db_session, order_id=order.id)
    events = list(
        (
            await db_session.scalars(
                select(NotificationOutbox).where(
                    NotificationOutbox.event_type == "order.created",
                    NotificationOutbox.aggregate_id == str(order.id),
                )
            )
        ).all()
    )
    assert {event.recipient_admin_id for event in events} == {admin.id for admin in admins}
    assert len(events) == len(admins)
    assert len({event.dedupe_key for event in events}) == len(admins)


async def test_order_status_change_queues_user_and_admin_in_same_transaction(
    db_session: AsyncSession, user: User, admin: Admin
) -> None:
    from app.services.order_service import confirm_order

    order = Order(
        order_number=f"STATUS-{uuid4().hex[:10]}",
        user_id=user.id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        customer_name="Status customer",
        customer_phone="+998901234567",
        subtotal=1000,
        delivery_fee=0,
        discount=0,
        total=1000,
        payment_method=PaymentMethod.CASH,
        admin_message_ids={str(admin.telegram_id): 654},
    )
    db_session.add(order)
    await db_session.flush()

    changed = await confirm_order(db_session, order, admin_id=admin.id)
    events = list(
        (
            await db_session.scalars(
                select(NotificationOutbox).where(
                    NotificationOutbox.aggregate_id == str(order.id),
                    NotificationOutbox.event_type.in_(
                        {"order.status.changed", "order.admin_card.status_updated"}
                    ),
                )
            )
        ).all()
    )
    assert changed.status == OrderStatus.CONFIRMED
    assert {
        (event.event_type, event.recipient_user_id, event.recipient_admin_id)
        for event in events
    } == {
        ("order.status.changed", user.id, None),
        ("order.admin_card.status_updated", None, admin.id),
    }
    assert len({event.payload_id for event in events}) == 1

    from app.services.notification_outbox_worker import OutboxClaim, _Delivery, _render_event

    admin_event = next(
        event for event in events if event.event_type == "order.admin_card.status_updated"
    )
    rendered = await _render_event(
        db_session,
        OutboxClaim(
            event_id=admin_event.id,
            event_type=admin_event.event_type,
            aggregate_id=admin_event.aggregate_id,
            payload_id=admin_event.payload_id,
            recipient_user_id=None,
            recipient_admin_id=admin.id,
            lease_token=uuid4(),
            attempts=1,
        ),
    )
    assert isinstance(rendered, _Delivery)
    assert rendered.operation == "edit_order"
    assert "✅ TASDIQLANDI" in rendered.text


async def test_retry_after_and_forbidden_update(test_engine, monkeypatch) -> None:
    suffix = uuid4().hex
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        user, actor, order, _message, event = await _message_case(session, suffix=suffix)
        user_id, actor_id, order_id, event_id = user.id, actor.id, order.id, event.id

    monkeypatch.setattr(
        "app.services.notification_outbox_worker.acquire_telegram_slot",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )
    stop = asyncio.Event()
    retry = TelegramRetryAfter(
        method=SendMessage(chat_id=123, text="synthetic"),
        message="synthetic retry",
        retry_after=17,
    )
    await run_outbox_worker(_OutboxMessageBot(stop, error=retry), maker, _FakeRedis(), stop)

    async with maker() as session:
        event = await session.get(NotificationOutbox, event_id)
        assert event is not None and event.status == NotificationOutboxStatus.PENDING
        assert event.next_available_at >= datetime.now(UTC) + timedelta(seconds=16)
        assert event.lease_token is None
        assert (
            await claim_outbox_batch(
                session,
                worker_id=f"retry-check-{suffix}",
                now=datetime.now(UTC),
                limit=1,
                lease_seconds=30,
            )
            == []
        )
        event.next_available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    stop = asyncio.Event()
    forbidden = TelegramForbiddenError(
        method=SendMessage(chat_id=123, text="synthetic"), message="synthetic forbidden"
    )
    await run_outbox_worker(
        _OutboxMessageBot(stop, error=forbidden), maker, _FakeRedis(), stop
    )

    async with maker() as session:
        user = await session.get(User, user_id)
        event = await session.get(NotificationOutbox, event_id)
        assert user is not None and user.is_blocked is True
        assert event is not None and event.status == NotificationOutboxStatus.FAILED
    async with maker() as session:
        await session.execute(delete(Order).where(Order.id == order_id))
        await session.execute(
            delete(NotificationOutbox).where(NotificationOutbox.id == event_id)
        )
        await session.execute(delete(Admin).where(Admin.id == actor_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_revoked_actor_admin_and_blocked_user_are_rechecked(
    test_engine, monkeypatch
) -> None:
    suffix = uuid4().hex
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        user, actor, order, _message, user_event = await _message_case(session, suffix=suffix)
        recipient = Admin(
            telegram_id=8_800_000_000_000_000 + int(suffix[:10], 16),
            full_name="Outbox recipient",
            role=AdminRole.SUPERADMIN,
        )
        inactive_recipient = Admin(
            telegram_id=8_900_000_000_000_000 + int(suffix[:10], 16),
            full_name="Inactive outbox recipient",
            role=AdminRole.MANAGER,
            is_active=False,
        )
        audit = AdminAuditEvent(
            actor_admin_id=actor.id,
            action="admin.team.update",
            resource_type="team",
            resource_id=str(actor.id),
            request_id=f"outbox-test:{suffix}",
            before_json=None,
            after_json={"role": "manager"},
        )
        session.add_all([recipient, inactive_recipient, audit])
        await session.flush()
        session.add_all(
            [
                NotificationOutbox(
                    recipient_admin_id=recipient.id,
                    event_type="admin.team.changed",
                    aggregate_id=str(actor.id),
                    payload_id=str(audit.id),
                    dedupe_key=f"revoked-actor:{suffix}",
                    status=NotificationOutboxStatus.PENDING,
                    attempts=0,
                    next_available_at=datetime.now(UTC),
                ),
                NotificationOutbox(
                    recipient_admin_id=inactive_recipient.id,
                    event_type="system.deploy",
                    aggregate_id="0",
                    dedupe_key=f"inactive-admin:{suffix}",
                    status=NotificationOutboxStatus.PENDING,
                    attempts=0,
                    next_available_at=datetime.now(UTC),
                ),
            ]
        )
        actor.is_active = False
        user.is_blocked = True
        user_id, actor_id, recipient_id = user.id, actor.id, recipient.id
        inactive_id, order_id = inactive_recipient.id, order.id
        event_ids = [
            user_event.id,
            *(
                await session.scalars(
                    select(NotificationOutbox.id).where(
                        NotificationOutbox.dedupe_key.in_(
                            [f"revoked-actor:{suffix}", f"inactive-admin:{suffix}"]
                        )
                    )
                )
            ).all(),
        ]

    monkeypatch.setattr(
        "app.services.notification_outbox_worker.acquire_telegram_slot",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )
    stop = asyncio.Event()
    timer = asyncio.create_task(asyncio.sleep(0.1))
    timer.add_done_callback(lambda _task: stop.set())
    bot = _OutboxMessageBot(stop)
    await run_outbox_worker(bot, maker, _FakeRedis(), stop)
    assert bot.messages == []
    async with maker() as session:
        rows = list(
            (
                await session.scalars(
                    select(NotificationOutbox).where(NotificationOutbox.id.in_(event_ids))
                )
            ).all()
        )
        assert len(rows) == 3
        assert all(row.status == NotificationOutboxStatus.FAILED for row in rows)
        assert {row.last_error for row in rows} == {
            "actor_inactive",
            "admin_inactive",
            "recipient_blocked",
        }
    async with maker() as session:
        await session.execute(delete(Order).where(Order.id == order_id))
        await session.execute(
            delete(AdminAuditEvent).where(
                AdminAuditEvent.request_id == f"outbox-test:{suffix}"
            )
        )
        await session.execute(
            delete(Admin).where(Admin.id.in_([actor_id, recipient_id, inactive_id]))
        )
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_existing_id_only_admin_events_have_safe_renderers(
    test_engine, monkeypatch
) -> None:
    suffix = uuid4().hex
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        actor = Admin(
            telegram_id=9_000_000_000_000_000 + int(suffix[:10], 16),
            full_name="Source actor",
            role=AdminRole.MANAGER,
        )
        recipient = Admin(
            telegram_id=9_100_000_000_000_000 + int(suffix[:10], 16),
            full_name="Source recipient",
            role=AdminRole.SUPERADMIN,
        )
        source = TrafficSource(code=f"safe-{suffix[:8]}", name="Private campaign name")
        session.add_all([actor, recipient, source])
        await session.flush()
        audit_events = [
            AdminAuditEvent(
                actor_admin_id=actor.id,
                action=f"outbox.test.{event_type.replace('.', '_')}",
                resource_type="safe_test",
                resource_id=str(source.id),
                request_id=f"renderer:{suffix}:{index}",
                before_json=None,
                after_json={"private_value": "must not appear"},
            )
            for index, event_type in enumerate(
                [
                    "admin.team.changed",
                    "store.settings.updated",
                    "traffic_source.created",
                    "traffic_source.updated",
                ]
            )
        ]
        session.add_all(audit_events)
        await session.flush()
        event_types = [
            "admin.team.changed",
            "store.settings.updated",
            "traffic_source.created",
            "traffic_source.updated",
        ]
        rows = [
            NotificationOutbox(
                recipient_admin_id=recipient.id,
                event_type=event_type,
                aggregate_id="1" if index < 2 else str(source.id),
                payload_id=str(audit_events[index].id),
                dedupe_key=f"renderer:{suffix}:{index}",
                status=NotificationOutboxStatus.PENDING,
                attempts=0,
                next_available_at=datetime.now(UTC),
            )
            for index, event_type in enumerate(event_types)
        ]
        session.add_all(rows)
        await session.flush()
        actor_id, recipient_id, source_id = actor.id, recipient.id, source.id
        event_ids = [row.id for row in rows]

    monkeypatch.setattr(
        "app.services.notification_outbox_worker.acquire_telegram_slot",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )

    class _FourMessageBot(_OutboxMessageBot):
        def __init__(self, stop: asyncio.Event) -> None:
            super().__init__(stop)

        async def send_message(self, chat_id: int, text: str, **kwargs):
            self.messages.append((chat_id, text, kwargs))
            if len(self.messages) == 4:
                self.stop.set()
            return SimpleNamespace(message_id=55)

    stop = asyncio.Event()
    bot = _FourMessageBot(stop)
    watchdog = asyncio.create_task(asyncio.sleep(1))
    watchdog.add_done_callback(lambda _task: stop.set())
    await run_outbox_worker(bot, maker, _FakeRedis(), stop)
    watchdog.cancel()
    assert len(bot.messages) == 4
    assert all("must not appear" not in message[1] for message in bot.messages)
    assert all("Private campaign name" not in message[1] for message in bot.messages)
    async with maker() as session:
        rows = list(
            (
                await session.scalars(
                    select(NotificationOutbox).where(NotificationOutbox.id.in_(event_ids))
                )
            ).all()
        )
        assert len(rows) == 4
        assert all(row.status == NotificationOutboxStatus.SENT for row in rows)
    async with maker() as session:
        await session.execute(
            delete(NotificationOutbox).where(NotificationOutbox.id.in_(event_ids))
        )
        await session.execute(
            delete(AdminAuditEvent).where(
                AdminAuditEvent.request_id.like(f"renderer:{suffix}:%")
            )
        )
        await session.execute(delete(TrafficSource).where(TrafficSource.id == source_id))
        await session.execute(delete(Admin).where(Admin.id.in_([actor_id, recipient_id])))
        await session.commit()


async def test_phase1_direct_send_is_not_duplicated():
    """Order creation/status callers queue in their transaction; only the worker sends."""
    from app.bot.services import order_notifications

    assert not hasattr(order_notifications, "register_new_order_notification")
    assert not hasattr(order_notifications, "register_order_status_notifications")


async def test_shared_pacing_caps_all_worker_instances_at_twenty_per_second() -> None:
    from app.services.telegram_pacing_service import acquire_telegram_slot

    redis_clients = [
        Redis.from_url(settings.redis_url, decode_responses=True),
        Redis.from_url(settings.redis_url, decode_responses=True),
    ]
    bot_id = 8_600_000_000_000_000 + int(uuid4().hex[:10], 16)
    times: list[float] = []

    async def reserve(index: int) -> None:
        await acquire_telegram_slot(
            redis_clients[index % len(redis_clients)],
            bot_id=bot_id,
            now=datetime.now(UTC),
        )
        times.append(asyncio.get_running_loop().time())

    try:
        await asyncio.gather(*(reserve(index) for index in range(25)))
        times.sort()
        assert (
            max(sum(0 <= current - start < 1 for current in times) for start in times) <= 20
        ), times
    finally:
        await redis_clients[0].delete(f"telegram:pacing:{bot_id}")
        await asyncio.gather(*(redis.aclose() for redis in redis_clients))


async def test_lifespan_starts_and_stops_one_outbox_task(monkeypatch) -> None:
    from app.main import create_app

    class _BotSession:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _Bot:
        def __init__(self) -> None:
            self.session = _BotSession()

    bot = _Bot()
    redis = object()
    session_maker = object()
    started = asyncio.Event()
    worker_stop_seen = asyncio.Event()

    async def fake_worker(_bot, actual_session_maker, actual_redis, stop) -> None:
        assert actual_session_maker is session_maker
        assert actual_redis is redis
        started.set()
        await stop.wait()
        worker_stop_seen.set()

    async def no_setup(_bot) -> None:
        return None

    monkeypatch.setattr("app.main.create_bot", lambda: bot)
    monkeypatch.setattr("app.main.get_redis", lambda: redis)
    monkeypatch.setattr("app.main.setup_bot_commands", no_setup)
    monkeypatch.setattr("app.main.run_outbox_worker", fake_worker)
    app = create_app()
    app.state.session_maker = session_maker

    async with app.router.lifespan_context(app):
        await started.wait()
        assert not worker_stop_seen.is_set()
        assert app.state.notification_outbox_task.done() is False

    assert worker_stop_seen.is_set()
    assert bot.session.closed is True
