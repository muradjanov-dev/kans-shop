import asyncio
import base64
import hashlib
import hmac
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import (
    OrderAlreadyProcessedError,
    PaymentAlreadyProcessedError,
    PaymentNotConfiguredError,
)
from app.db.models.enums import (
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    PaymentTxState,
)
from app.db.models.order import Order
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.payment_transaction import PaymentTransaction
from app.db.models.user import User
from app.db.repositories import order_repository
from app.services import payment_service


@pytest.fixture(autouse=True)
def configured_synthetic_gateway_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callback fixtures model a configured merchant account unless a test clears it."""
    for key, value in {
        "click_service_id": "synthetic-service",
        "click_merchant_id": "synthetic-merchant",
        "click_merchant_user_id": "synthetic-user",
        "click_secret_key": "synthetic-click-key",
        "payme_merchant_id": "synthetic-payme",
        "payme_secret_key": "synthetic-payme-key",
    }.items():
        monkeypatch.setattr(payment_service.settings, key, value)


async def _make_order(
    session: AsyncSession,
    user_id: int,
    *,
    payment_method: PaymentMethod = PaymentMethod.CLICK,
    status: OrderStatus = OrderStatus.NEW,
    amount: Decimal = Decimal("5000.00"),
) -> Order:
    suffix = uuid4().hex[:10]
    order = Order(
        order_number=f"KANS-{suffix}",
        user_id=user_id,
        order_type=OrderType.PICKUP,
        status=status,
        customer_name="Synthetic Customer",
        customer_phone="+998901234567",
        subtotal=amount,
        total=amount,
        payment_method=payment_method,
        payment_status=PaymentStatus.PENDING,
        source="webapp",
    )
    session.add(order)
    await session.flush()
    return order


def _click_params(
    order: Order,
    transaction_id: str,
    *,
    action: int,
    prepare_id: int | None = None,
    amount: str = "5000.00",
    error: int = 0,
) -> dict:
    params = {
        "click_trans_id": transaction_id,
        "merchant_trans_id": order.order_number,
        "amount": amount,
        "sign_time": "2026-10-09 12:00:00",
        "error": error,
    }
    if prepare_id is not None:
        params["merchant_prepare_id"] = str(prepare_id)
    params["sign_string"] = payment_service._click_signature(params, action=action)
    return params


async def _prepare_click(session: AsyncSession, order: Order, transaction_id: str) -> int:
    response = await payment_service.click_prepare(
        session, _click_params(order, transaction_id, action=0)
    )
    assert response["error"] == payment_service.CLICK_ERROR_OK
    return int(response["merchant_prepare_id"])


async def _payment_history_count(session: AsyncSession, order_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
        )
        or 0
    )


async def test_gateway_exact_duplicate(db_session: AsyncSession, user) -> None:
    order = await _make_order(db_session, user.id)
    prepare_id = await _prepare_click(db_session, order, "click-exact-duplicate")
    params = _click_params(order, "click-exact-duplicate", action=1, prepare_id=prepare_id)

    first = await payment_service.click_complete(db_session, params)
    order.status = OrderStatus.COMPLETED
    second = await payment_service.click_complete(db_session, params)

    assert first["error"] == second["error"] == payment_service.CLICK_ERROR_OK
    assert first["merchant_confirm_id"] == second["merchant_confirm_id"] == prepare_id
    assert order.payment_status == PaymentStatus.PAID
    assert await _payment_history_count(db_session, order.id) == 1


async def test_concurrent_click_duplicate_refreshes_locked_transaction(
    test_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retry that loaded PENDING before waiting on the order lock sees the committed winner."""
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    telegram_id = 8_300_000_000_000_000 + int(uuid4().hex[:12], 16)
    async with session_maker() as setup_session:
        user = User(telegram_id=telegram_id, first_name="Concurrent callback test")
        setup_session.add(user)
        await setup_session.flush()
        order = await _make_order(setup_session, user.id)
        prepare_id = await _prepare_click(setup_session, order, "click-concurrent-duplicate")
        params = _click_params(
            order,
            "click-concurrent-duplicate",
            action=1,
            prepare_id=prepare_id,
        )
        order_id = order.id
        user_id = user.id
        await setup_session.commit()

    retry_reached_order_lock = asyncio.Event()
    release_retry = asyncio.Event()
    retry_session: AsyncSession | None = None
    original_get_by_id_for_update = order_repository.get_by_id_for_update

    async def pause_retry_before_order_lock(session: AsyncSession, locked_order_id: int):
        if session is retry_session:
            # click_complete has already read and cached the PENDING transaction by this point.
            retry_reached_order_lock.set()
            await release_retry.wait()
        return await original_get_by_id_for_update(session, locked_order_id)

    monkeypatch.setattr(
        order_repository, "get_by_id_for_update", pause_retry_before_order_lock
    )

    async def retry_callback() -> dict:
        nonlocal retry_session
        async with session_maker() as session:
            retry_session = session
            response = await payment_service.click_complete(session, params)
            await session.commit()
            return response

    retry_task: asyncio.Task[dict] | None = None
    try:
        retry_task = asyncio.create_task(retry_callback())
        await asyncio.wait_for(retry_reached_order_lock.wait(), timeout=5)

        async with session_maker() as winner_session:
            winner = await payment_service.click_complete(winner_session, params)
            await winner_session.commit()

        release_retry.set()
        retry = await asyncio.wait_for(retry_task, timeout=5)

        assert winner["error"] == payment_service.CLICK_ERROR_OK
        assert retry["error"] == payment_service.CLICK_ERROR_OK
        assert winner["merchant_confirm_id"] == retry["merchant_confirm_id"] == prepare_id
        async with session_maker() as verify_session:
            order = await verify_session.get(Order, order_id)
            assert order is not None and order.payment_status == PaymentStatus.PAID
            assert await _payment_history_count(verify_session, order_id) == 1
    finally:
        release_retry.set()
        if retry_task is not None and not retry_task.done():
            await asyncio.gather(retry_task, return_exceptions=True)
        async with session_maker() as cleanup_session:
            await cleanup_session.execute(delete(Order).where(Order.id == order_id))
            await cleanup_session.execute(delete(User).where(User.id == user_id))
            await cleanup_session.commit()


async def test_gateway_second_transaction_rejected(db_session: AsyncSession, user) -> None:
    order = await _make_order(db_session, user.id)
    first_prepare_id = await _prepare_click(db_session, order, "click-first")
    second_prepare_id = await _prepare_click(db_session, order, "click-second")
    first = await payment_service.click_complete(
        db_session,
        _click_params(order, "click-first", action=1, prepare_id=first_prepare_id),
    )
    second = await payment_service.click_complete(
        db_session,
        _click_params(order, "click-second", action=1, prepare_id=second_prepare_id),
    )

    assert first["error"] == payment_service.CLICK_ERROR_OK
    assert second["error"] == payment_service.CLICK_ERROR_ALREADY_PAID
    second_tx = await db_session.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.provider == PaymentProvider.CLICK,
            PaymentTransaction.provider_transaction_id == "click-second",
        )
    )
    assert second_tx is not None and second_tx.state == PaymentTxState.PENDING
    assert await _payment_history_count(db_session, order.id) == 1


async def test_click_wrong_provider_order_amount_and_terminal_order_are_rejected(
    db_session: AsyncSession, user
) -> None:
    payme_order = await _make_order(db_session, user.id, payment_method=PaymentMethod.PAYME)
    wrong_provider = await payment_service.click_prepare(
        db_session, _click_params(payme_order, "click-wrong-provider", action=0)
    )
    assert wrong_provider["error"] != payment_service.CLICK_ERROR_OK

    first_order = await _make_order(db_session, user.id)
    other_order = await _make_order(db_session, user.id)
    prepare_id = await _prepare_click(db_session, first_order, "click-wrong-order")
    wrong_order_params = _click_params(
        other_order, "click-wrong-order", action=1, prepare_id=prepare_id
    )
    wrong_order = await payment_service.click_complete(db_session, wrong_order_params)
    assert wrong_order["error"] == payment_service.CLICK_ERROR_TRANSACTION_NOT_FOUND
    assert first_order.payment_status == PaymentStatus.PENDING

    wrong_amount = await payment_service.click_complete(
        db_session,
        _click_params(
            first_order,
            "click-wrong-order",
            action=1,
            prepare_id=prepare_id,
            amount="4000.00",
        ),
    )
    assert wrong_amount["error"] == payment_service.CLICK_ERROR_INVALID_AMOUNT

    first_order.status = OrderStatus.CANCELLED
    terminal = await payment_service.click_complete(
        db_session,
        _click_params(first_order, "click-wrong-order", action=1, prepare_id=prepare_id),
    )
    assert terminal["error"] == payment_service.CLICK_ERROR_ALREADY_PAID
    assert first_order.payment_status == PaymentStatus.PENDING


async def test_payme_exact_duplicate_after_order_completion(
    db_session: AsyncSession, user, monkeypatch
) -> None:
    monkeypatch.setattr(payment_service.settings, "payme_secret_key", "synthetic-payme-key")
    order = await _make_order(db_session, user.id, payment_method=PaymentMethod.PAYME)
    authorization = "Basic " + base64.b64encode(b"Paycom:synthetic-payme-key").decode()
    create = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "CreateTransaction",
        "params": {
            "id": "payme-exact-duplicate",
            "time": 1_791_536_000_000,
            "amount": 500000,
            "account": {"order_id": order.id},
        },
    }
    created = await payment_service.payme_handle_rpc(
        db_session, create, authorization_header=authorization
    )
    assert "result" in created

    perform = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "PerformTransaction",
        "params": {"id": "payme-exact-duplicate"},
    }
    first = await payment_service.payme_handle_rpc(
        db_session, perform, authorization_header=authorization
    )
    order.status = OrderStatus.COMPLETED
    replay = await payment_service.payme_handle_rpc(
        db_session, perform, authorization_header=authorization
    )

    assert first["result"] == replay["result"]
    assert replay["result"]["state"] == payment_service.PAYME_STATE_COMPLETED
    assert await _payment_history_count(db_session, order.id) == 1


async def test_payme_second_transaction_wrong_provider_amount_and_terminal_rejected(
    db_session: AsyncSession, user, monkeypatch
) -> None:
    monkeypatch.setattr(payment_service.settings, "payme_secret_key", "synthetic-payme-key")
    authorization = "Basic " + base64.b64encode(b"Paycom:synthetic-payme-key").decode()
    order = await _make_order(db_session, user.id, payment_method=PaymentMethod.PAYME)
    wrong_provider_order = await _make_order(db_session, user.id)

    async def call(method: str, order_id: int, transaction_id: str, amount: int = 500000):
        return await payment_service.payme_handle_rpc(
            db_session,
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": method,
                "params": {
                    "id": transaction_id,
                    "amount": amount,
                    "account": {"order_id": order_id},
                },
            },
            authorization_header=authorization,
        )

    wrong_provider = await call(
        "CheckPerformTransaction", wrong_provider_order.id, "payme-wrong-provider"
    )
    assert "error" in wrong_provider
    wrong_amount = await call("CheckPerformTransaction", order.id, "payme-wrong-amount", 1)
    assert wrong_amount["error"]["code"] == payment_service.PAYME_ERR_INVALID_AMOUNT

    created = await call("CreateTransaction", order.id, "payme-first")
    assert "result" in created
    wrong_order_duplicate = await payment_service.payme_handle_rpc(
        db_session,
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "CreateTransaction",
            "params": {
                "id": "payme-first",
                "amount": 500000,
                "account": {"order_id": wrong_provider_order.id},
            },
        },
        authorization_header=authorization,
    )
    assert "error" in wrong_order_duplicate

    performed = await payment_service.payme_handle_rpc(
        db_session,
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "PerformTransaction",
            "params": {"id": "payme-first", "amount": 500000},
        },
        authorization_header=authorization,
    )
    assert "result" in performed
    second = await call("CreateTransaction", order.id, "payme-second")
    assert second["error"]["code"] == payment_service.PAYME_ERR_ORDER_ALREADY_PAID

    terminal_order = await _make_order(
        db_session, user.id, payment_method=PaymentMethod.PAYME, status=OrderStatus.CANCELLED
    )
    terminal = await call("CheckPerformTransaction", terminal_order.id, "payme-terminal")
    assert "error" in terminal

    bad_auth = await payment_service.payme_handle_rpc(
        db_session,
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "CheckPerformTransaction",
            "params": {"amount": 500000, "account": {"order_id": order.id}},
        },
        authorization_header="Basic invalid",
    )
    assert bad_auth["error"]["code"] == -32504


async def test_payme_cancel_retry_preserves_cancelled_after_complete_state(
    db_session: AsyncSession, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(payment_service.settings, "payme_secret_key", "synthetic-payme-key")
    authorization = "Basic " + base64.b64encode(b"Paycom:synthetic-payme-key").decode()
    order = await _make_order(db_session, user.id, payment_method=PaymentMethod.PAYME)

    async def call(method: str, request_id: int, params: dict) -> dict:
        return await payment_service.payme_handle_rpc(
            db_session,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            authorization_header=authorization,
        )

    created = await call(
        "CreateTransaction",
        20,
        {
            "id": "payme-cancel-after-complete",
            "time": 1_791_536_000_000,
            "amount": 500000,
            "account": {"order_id": order.id},
        },
    )
    assert "result" in created
    performed = await call("PerformTransaction", 21, {"id": "payme-cancel-after-complete"})
    assert "result" in performed

    cancel_params = {"id": "payme-cancel-after-complete", "reason": 5}
    first = await call("CancelTransaction", 22, cancel_params)
    retry = await call("CancelTransaction", 23, cancel_params)

    assert "result" in first and "result" in retry
    assert first["result"] == retry["result"]
    assert retry["result"]["state"] == payment_service.PAYME_STATE_CANCELLED_AFTER_COMPLETE
    assert order.payment_status == PaymentStatus.PAID


async def test_callback_authentication_rejects_empty_provider_secrets(
    db_session: AsyncSession, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    click_order = await _make_order(db_session, user.id)
    prepare_id = await _prepare_click(db_session, click_order, "click-empty-secret-complete")
    monkeypatch.setattr(payment_service.settings, "click_secret_key", "")
    unsigned_click = await payment_service.click_prepare(
        db_session, _click_params(click_order, "click-empty-secret", action=0)
    )
    assert unsigned_click["error"] == payment_service.CLICK_ERROR_SIGN_FAILED
    unsigned_complete = await payment_service.click_complete(
        db_session,
        _click_params(
            click_order,
            "click-empty-secret-complete",
            action=1,
            prepare_id=prepare_id,
        ),
    )
    assert unsigned_complete["error"] == payment_service.CLICK_ERROR_SIGN_FAILED

    payme_order = await _make_order(db_session, user.id, payment_method=PaymentMethod.PAYME)
    monkeypatch.setattr(payment_service.settings, "payme_secret_key", "")
    empty_secret_auth = "Basic " + base64.b64encode(b"Paycom:").decode()
    unauthenticated_payme = await payment_service.payme_handle_rpc(
        db_session,
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "CheckPerformTransaction",
            "params": {"amount": 500000, "account": {"order_id": payme_order.id}},
        },
        authorization_header=empty_secret_auth,
    )
    assert unauthenticated_payme["error"]["code"] == -32504
    assert await db_session.scalar(select(func.count()).select_from(PaymentTransaction)) == 1
    click_transaction = await db_session.scalar(select(PaymentTransaction))
    assert click_transaction is not None and click_transaction.state == PaymentTxState.PENDING


async def test_paynet_placeholder_rejects_supported_looking_callback(
    db_session: AsyncSession, user, monkeypatch
) -> None:
    monkeypatch.setattr(payment_service.settings, "paynet_secret_key", "synthetic-paynet-key")
    order = await _make_order(db_session, user.id, payment_method=PaymentMethod.PAYNET)
    payload = {"order_id": order.order_number, "amount": "5000.00", "transaction_id": "p-1"}
    raw = "&".join(f"{key}={payload[key]}" for key in sorted(payload))
    payload["sign"] = hmac.new(b"synthetic-paynet-key", raw.encode(), hashlib.sha1).hexdigest()

    result = await payment_service.paynet_pay(db_session, payload)

    assert result["result"] == 0
    assert await db_session.scalar(select(func.count()).select_from(PaymentTransaction)) == 0


async def test_paylink_requires_matching_unpaid_nonterminal_order(
    db_session: AsyncSession, user, monkeypatch
) -> None:
    order = Order(
        order_number=f"KANS-{uuid4().hex[:10]}",
        user_id=user.id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        customer_name="Synthetic Customer",
        customer_phone="+998901234567",
        subtotal=Decimal("5000.00"),
        total=Decimal("5000.00"),
        payment_method=PaymentMethod.CLICK,
        payment_status=PaymentStatus.PENDING,
        source="webapp",
    )
    db_session.add(order)

    for key, value in {
        "click_service_id": "synthetic-service",
        "click_merchant_id": "synthetic-merchant",
        "click_merchant_user_id": "synthetic-user",
        "click_secret_key": "synthetic-secret",
        "payme_merchant_id": "synthetic-payme",
        "payme_secret_key": "synthetic-payme-key",
    }.items():
        monkeypatch.setattr(payment_service.settings, key, value)

    assert "my.click.uz" in payment_service.build_pay_url(order, PaymentProvider.CLICK)
    with pytest.raises(PaymentNotConfiguredError):
        payment_service.build_pay_url(order, PaymentProvider.PAYME)

    order.payment_status = PaymentStatus.PAID
    with pytest.raises(PaymentAlreadyProcessedError):
        payment_service.build_pay_url(order, PaymentProvider.CLICK)
    order.payment_status = PaymentStatus.PENDING
    order.status = OrderStatus.CANCELLED
    with pytest.raises(OrderAlreadyProcessedError):
        payment_service.build_pay_url(order, PaymentProvider.CLICK)
