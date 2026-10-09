"""Click, Payme and Paynet gateway integration.

Click and Payme implement their own public, versioned merchant protocols (Prepare/Complete for
Click; a JSON-RPC method set for Payme). Paynet remains disabled until its merchant protocol has
been verified against the merchant agreement and primary documentation.
"""

import hashlib
import hmac
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    OrderAlreadyProcessedError,
    OrderNotFoundError,
    PaymentAlreadyProcessedError,
    PaymentNotConfiguredError,
)
from app.db.models.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
    PaymentTxState,
)
from app.db.models.order import Order
from app.db.models.payment_transaction import PaymentTransaction
from app.db.repositories import order_repository, payment_repository
from app.services import order_service

# --- Amount conversion -------------------------------------------------------------------
# Orders store UZS as a Decimal so'm amount. Click expects so'm (2 decimals); Payme expects
# tiyin (so'm * 100) as an integer.


def _to_tiyin(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def _from_tiyin(tiyin: int) -> Decimal:
    return Decimal(tiyin) / 100


def _now_ms() -> int:
    return int(time.time() * 1000)


def _dt_to_ms(dt: datetime | None) -> int:
    if dt is None:
        return 0
    return int(dt.timestamp() * 1000)


# --- Pay link generation ------------------------------------------------------------------


def is_provider_configured(provider: PaymentProvider) -> bool:
    if provider == PaymentProvider.CLICK:
        return all(
            value.strip()
            for value in (
                settings.click_service_id,
                settings.click_merchant_id,
                settings.click_merchant_user_id,
                settings.click_secret_key,
            )
        )
    if provider == PaymentProvider.PAYME:
        return all(
            value.strip() for value in (settings.payme_merchant_id, settings.payme_secret_key)
        )
    if provider == PaymentProvider.PAYNET:
        # Config values alone must not enable Paynet before the merchant contract is verified.
        return False
    return False


def build_pay_url(order: Order, provider: PaymentProvider) -> str:
    if not is_provider_configured(provider):
        raise PaymentNotConfiguredError(f"{provider.value} is not configured")
    if order.payment_method != PaymentMethod(provider.value):
        raise PaymentNotConfiguredError("This provider is not configured for the order")
    if order.payment_status == PaymentStatus.PAID:
        raise PaymentAlreadyProcessedError("Order is already paid")
    if order.status in (OrderStatus.CANCELLED, OrderStatus.COMPLETED):
        raise OrderAlreadyProcessedError("Order is no longer payable")

    if provider == PaymentProvider.CLICK:
        params = {
            "service_id": settings.click_service_id,
            "merchant_id": settings.click_merchant_id,
            "amount": f"{order.total:.2f}",
            "transaction_param": order.order_number,
            "return_url": settings.webapp_url,
        }
        return f"https://my.click.uz/services/pay?{urlencode(params)}"

    if provider == PaymentProvider.PAYME:
        import base64

        raw = (
            f"m={settings.payme_merchant_id};ac.order_id={order.id};a={_to_tiyin(order.total)}"
        )
        encoded = base64.b64encode(raw.encode()).decode()
        return f"https://checkout.paycom.uz/{encoded}"

    raise PaymentNotConfiguredError(f"{provider.value} is not configured")


# --- Click ----------------------------------------------------------------------------------
# https://docs.click.uz/en/click-api-request/  (Prepare = action 0, Complete = action 1)

CLICK_ERROR_OK = 0
CLICK_ERROR_SIGN_FAILED = -1
CLICK_ERROR_INVALID_AMOUNT = -2
CLICK_ERROR_ACTION_NOT_FOUND = -3
CLICK_ERROR_ALREADY_PAID = -4
CLICK_ERROR_ORDER_NOT_FOUND = -5
CLICK_ERROR_TRANSACTION_NOT_FOUND = -6
CLICK_ERROR_REQUEST_FAILED = -8
CLICK_ERROR_TRANSACTION_CANCELLED = -9


def _click_signature(params: dict, *, action: int) -> str:
    parts = [
        str(params.get("click_trans_id", "")),
        settings.click_service_id,
        settings.click_secret_key,
        str(params.get("merchant_trans_id", "")),
    ]
    if action == 1:
        parts.append(str(params.get("merchant_prepare_id", "")))
    parts.append(str(params.get("amount", "")))
    parts.append(str(action))
    parts.append(str(params.get("sign_time", "")))
    return hashlib.md5("".join(parts).encode()).hexdigest()


def _click_response(
    params: dict, *, error: int, error_note: str = "Success", **extra: object
) -> dict:
    return {
        "click_trans_id": params.get("click_trans_id"),
        "merchant_trans_id": params.get("merchant_trans_id"),
        "error": error,
        "error_note": error_note,
        **extra,
    }


def _click_amount_matches(amount: object, expected: Decimal) -> bool:
    try:
        return Decimal(str(amount)) == expected
    except (InvalidOperation, TypeError, ValueError):
        return False


def _order_is_terminal(order: Order) -> bool:
    return order.status in (OrderStatus.CANCELLED, OrderStatus.COMPLETED)


def _order_is_payable(order: Order, provider: PaymentProvider) -> bool:
    return (
        order.payment_method == PaymentMethod(provider.value)
        and order.payment_status != PaymentStatus.PAID
        and not _order_is_terminal(order)
    )


async def _has_other_paid_transaction(
    session: AsyncSession,
    *,
    order_id: int,
    provider: PaymentProvider,
    exclude_id: int,
) -> bool:
    other_id = await session.scalar(
        select(PaymentTransaction.id)
        .where(
            PaymentTransaction.order_id == order_id,
            PaymentTransaction.provider == provider,
            PaymentTransaction.state == PaymentTxState.PAID,
            PaymentTransaction.id != exclude_id,
        )
        .limit(1)
    )
    return other_id is not None


async def click_prepare(session: AsyncSession, params: dict) -> dict:
    if _click_signature(params, action=0) != params.get("sign_string"):
        return _click_response(
            params, error=CLICK_ERROR_SIGN_FAILED, error_note="SIGN CHECK FAILED!"
        )
    order = await order_repository.get_by_number(session, str(params.get("merchant_trans_id")))
    if order is None:
        return _click_response(
            params, error=CLICK_ERROR_ORDER_NOT_FOUND, error_note="Order not found"
        )
    locked_order = await order_repository.get_by_id_for_update(session, order.id)
    if locked_order is None:
        return _click_response(
            params, error=CLICK_ERROR_ORDER_NOT_FOUND, error_note="Order not found"
        )
    order = locked_order

    if _click_signature(params, action=0) != params.get("sign_string"):
        return _click_response(
            params, error=CLICK_ERROR_SIGN_FAILED, error_note="SIGN CHECK FAILED!"
        )
    if order.payment_method != PaymentMethod.CLICK:
        return _click_response(
            params, error=CLICK_ERROR_ORDER_NOT_FOUND, error_note="Order not found"
        )

    if not _click_amount_matches(params.get("amount", "0"), order.total):
        return _click_response(
            params, error=CLICK_ERROR_INVALID_AMOUNT, error_note="Incorrect amount"
        )

    click_trans_id = str(params.get("click_trans_id", ""))
    existing = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.CLICK, click_trans_id, for_update=True
    )
    if existing is not None:
        if (
            existing.order_id != order.id
            or existing.amount != order.total
            or existing.raw_payload.get("_click_prepare_payload") != params
        ):
            return _click_response(
                params,
                error=CLICK_ERROR_TRANSACTION_NOT_FOUND,
                error_note="Transaction not found",
            )
        return _click_response(params, error=CLICK_ERROR_OK, merchant_prepare_id=existing.id)

    if not _order_is_payable(order, PaymentProvider.CLICK):
        return _click_response(
            params, error=CLICK_ERROR_ALREADY_PAID, error_note="Order is not payable"
        )

    tx = await payment_repository.create(
        session,
        order_id=order.id,
        provider=PaymentProvider.CLICK,
        amount=order.total,
        provider_transaction_id=click_trans_id,
        state=PaymentTxState.PENDING,
        raw_payload={"_click_prepare_payload": params},
    )
    return _click_response(params, error=CLICK_ERROR_OK, merchant_prepare_id=tx.id)


async def click_complete(session: AsyncSession, params: dict) -> dict:
    if _click_signature(params, action=1) != params.get("sign_string"):
        return _click_response(
            params, error=CLICK_ERROR_SIGN_FAILED, error_note="SIGN CHECK FAILED!"
        )
    click_trans_id = str(params.get("click_trans_id", ""))
    associated_tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.CLICK, click_trans_id
    )
    if associated_tx is None:
        return _click_response(
            params,
            error=CLICK_ERROR_TRANSACTION_NOT_FOUND,
            error_note="Transaction not found",
        )

    order = await order_repository.get_by_id_for_update(session, associated_tx.order_id)
    if order is None:
        return _click_response(
            params, error=CLICK_ERROR_ORDER_NOT_FOUND, error_note="Order not found"
        )
    tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.CLICK, click_trans_id, for_update=True
    )
    if (
        tx is None
        or tx.id != associated_tx.id
        or tx.order_id != order.id
        or str(tx.id) != str(params.get("merchant_prepare_id"))
    ):
        return _click_response(
            params, error=CLICK_ERROR_TRANSACTION_NOT_FOUND, error_note="Transaction not found"
        )

    if _click_signature(params, action=1) != params.get("sign_string"):
        return _click_response(
            params, error=CLICK_ERROR_SIGN_FAILED, error_note="SIGN CHECK FAILED!"
        )
    if (
        order.payment_method != PaymentMethod.CLICK
        or str(params.get("merchant_trans_id")) != order.order_number
    ):
        return _click_response(
            params,
            error=CLICK_ERROR_TRANSACTION_NOT_FOUND,
            error_note="Transaction not found",
        )
    if not _click_amount_matches(
        params.get("amount", "0"), order.total
    ) or not _click_amount_matches(params.get("amount", "0"), tx.amount):
        return _click_response(
            params, error=CLICK_ERROR_INVALID_AMOUNT, error_note="Incorrect amount"
        )

    if tx.state == PaymentTxState.PAID:
        if tx.raw_payload.get("_click_complete_payload") == params:
            return _click_response(params, error=CLICK_ERROR_OK, merchant_confirm_id=tx.id)
        return _click_response(
            params, error=CLICK_ERROR_ALREADY_PAID, error_note="Transaction already paid"
        )
    if tx.state == PaymentTxState.CANCELLED:
        if tx.raw_payload.get("_click_complete_payload") == params:
            return _click_response(params, error=CLICK_ERROR_OK, merchant_confirm_id=tx.id)
        return _click_response(
            params,
            error=CLICK_ERROR_TRANSACTION_CANCELLED,
            error_note="Transaction is cancelled",
        )

    # Click sends a negative `error` on its own request when the payment itself failed/was
    # cancelled on their side — we must still ack (error: 0) but mark our side as failed.
    try:
        click_reported_error = int(params.get("error", 0))
    except (TypeError, ValueError):
        return _click_response(
            params, error=CLICK_ERROR_ACTION_NOT_FOUND, error_note="Invalid transaction error"
        )
    if click_reported_error < 0:
        payload = dict(tx.raw_payload)
        payload["_click_complete_payload"] = params
        await payment_repository.update_state(
            session, tx, state=PaymentTxState.CANCELLED, raw_payload=payload
        )
        return _click_response(params, error=CLICK_ERROR_OK, merchant_confirm_id=tx.id)

    if not _order_is_payable(order, PaymentProvider.CLICK):
        return _click_response(
            params, error=CLICK_ERROR_ALREADY_PAID, error_note="Order is not payable"
        )
    if await _has_other_paid_transaction(
        session,
        order_id=order.id,
        provider=PaymentProvider.CLICK,
        exclude_id=tx.id,
    ):
        return _click_response(
            params, error=CLICK_ERROR_ALREADY_PAID, error_note="Order is already paid"
        )

    payload = dict(tx.raw_payload)
    payload["_click_complete_payload"] = params
    await payment_repository.update_state(
        session, tx, state=PaymentTxState.PAID, raw_payload=payload
    )
    await order_service.mark_paid(session, order)

    return _click_response(params, error=CLICK_ERROR_OK, merchant_confirm_id=tx.id)


# --- Payme ------------------------------------------------------------------------------
# https://developer.help.paycom.uz/  (Merchant API, JSON-RPC 2.0)

PAYME_STATE_CREATED = 1
PAYME_STATE_COMPLETED = 2
PAYME_STATE_CANCELLED = -1
PAYME_STATE_CANCELLED_AFTER_COMPLETE = -2

PAYME_ERR_INVALID_AMOUNT = -31001
PAYME_ERR_TRANSACTION_NOT_FOUND = -31003
PAYME_ERR_UNABLE_TO_PERFORM = -31008
PAYME_ERR_ORDER_NOT_FOUND = -31050
PAYME_ERR_ORDER_ALREADY_PAID = -31051


class PaymeRpcError(Exception):
    def __init__(self, code: int, message: str, *, data: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def verify_payme_auth(authorization_header: str | None) -> bool:
    if not authorization_header or not authorization_header.startswith("Basic "):
        return False
    import base64
    import binascii

    try:
        decoded = base64.b64decode(
            authorization_header.removeprefix("Basic "), validate=True
        ).decode()
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    expected = f"Paycom:{settings.payme_secret_key}"
    return hmac.compare_digest(decoded, expected)


async def _payme_get_order(
    session: AsyncSession, params: dict, *, for_update: bool = False
) -> Order:
    account = params.get("account") or {}
    if not isinstance(account, dict):
        account = {}
    order_id = account.get("order_id")
    order = None
    if order_id is not None:
        try:
            order_id_value = int(order_id)
        except (TypeError, ValueError):
            order_id_value = None
        if order_id_value is not None:
            if for_update:
                order = await order_repository.get_by_id_for_update(session, order_id_value)
            else:
                order = await order_repository.get_by_id(session, order_id_value)
    if order is None:
        raise PaymeRpcError(PAYME_ERR_ORDER_NOT_FOUND, "Order not found", data="order_id")
    return order


def _require_payme_auth(authorization_header: str | None) -> None:
    if authorization_header is not None and not verify_payme_auth(authorization_header):
        raise PaymeRpcError(-32504, "Insufficient privileges")


def _payme_amount_matches(amount: object, order: Order) -> bool:
    try:
        return Decimal(str(amount)) == _to_tiyin(order.total)
    except (InvalidOperation, TypeError, ValueError):
        return False


def _payme_assert_order_payable(order: Order) -> None:
    if order.payment_status == PaymentStatus.PAID:
        raise PaymeRpcError(
            PAYME_ERR_ORDER_ALREADY_PAID, "Order already paid", data="order_id"
        )
    if order.payment_method != PaymentMethod.PAYME or _order_is_terminal(order):
        raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Unable to perform operation")


def _payme_assert_transaction_association(
    tx: PaymentTransaction, order: Order, params: dict
) -> None:
    if (
        tx.provider != PaymentProvider.PAYME
        or tx.order_id != order.id
        or order.payment_method != PaymentMethod.PAYME
    ):
        raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")
    if tx.amount != order.total:
        raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")
    account = params.get("account") or {}
    if not isinstance(account, dict):
        account = {}
    if account.get("order_id") is not None:
        try:
            request_order_id = int(account["order_id"])
        except (TypeError, ValueError):
            request_order_id = None
        if request_order_id != order.id:
            raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Unable to perform operation")
    stored_order_id = tx.raw_payload.get("_payme_order_id")
    if stored_order_id is not None:
        try:
            stored_order_id = int(stored_order_id)
        except (TypeError, ValueError):
            stored_order_id = None
        if stored_order_id != order.id:
            raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")


async def _payme_check_perform_transaction(
    session: AsyncSession, params: dict, authorization_header: str | None = None
) -> dict:
    order = await _payme_get_order(session, params, for_update=True)
    _require_payme_auth(authorization_header)
    if not _payme_amount_matches(params.get("amount", 0), order):
        raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")
    _payme_assert_order_payable(order)
    return {"allow": True}


def _payme_create_result(tx: PaymentTransaction) -> dict:
    return {
        "create_time": _dt_to_ms(tx.created_at),
        "transaction": str(tx.id),
        "state": tx.raw_payload.get("_payme_state", PAYME_STATE_CREATED),
    }


async def _payme_create_transaction(
    session: AsyncSession, params: dict, authorization_header: str | None = None
) -> dict:
    payme_tx_id = str(params.get("id", ""))
    existing = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id
    )
    if existing is not None:
        order = await order_repository.get_by_id_for_update(session, existing.order_id)
        if order is None:
            raise PaymeRpcError(PAYME_ERR_ORDER_NOT_FOUND, "Order not found", data="order_id")
        tx = await payment_repository.get_by_provider_tx_id(
            session, PaymentProvider.PAYME, payme_tx_id, for_update=True
        )
        if tx is None or tx.id != existing.id or tx.order_id != order.id:
            raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")
        _require_payme_auth(authorization_header)
        _payme_assert_transaction_association(tx, order, params)
        if not _payme_amount_matches(params.get("amount", 0), order):
            raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")
        if tx.raw_payload.get("_payme_create_request") != params:
            raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Transaction already exists")
        if tx.state == PaymentTxState.CANCELLED:
            raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Transaction is cancelled")
        return _payme_create_result(tx)

    unlocked_order = await _payme_get_order(session, params)
    order = await order_repository.get_by_id_for_update(session, unlocked_order.id)
    if order is None:
        raise PaymeRpcError(PAYME_ERR_ORDER_NOT_FOUND, "Order not found", data="order_id")
    _require_payme_auth(authorization_header)
    if not _payme_amount_matches(params.get("amount", 0), order):
        raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")
    _payme_assert_order_payable(order)

    other_active = await payment_repository.get_by_order_and_provider(
        session, order.id, PaymentProvider.PAYME, for_update=True
    )
    if other_active is not None and other_active.state == PaymentTxState.PENDING:
        raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Order already has a transaction")

    payload = dict(params)
    payload["_payme_create_request"] = dict(params)
    payload["_payme_order_id"] = order.id
    payload["_payme_state"] = PAYME_STATE_CREATED
    tx = await payment_repository.create(
        session,
        order_id=order.id,
        provider=PaymentProvider.PAYME,
        amount=order.total,
        provider_transaction_id=payme_tx_id,
        state=PaymentTxState.PENDING,
        raw_payload=payload,
    )
    return _payme_create_result(tx)


async def _payme_lock_associated_transaction(
    session: AsyncSession,
    params: dict,
    authorization_header: str | None,
) -> tuple[PaymentTransaction, Order]:
    payme_tx_id = str(params.get("id", ""))
    associated_tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id
    )
    if associated_tx is None:
        raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")
    order = await order_repository.get_by_id_for_update(session, associated_tx.order_id)
    if order is None:
        raise PaymeRpcError(PAYME_ERR_ORDER_NOT_FOUND, "Order not found", data="order_id")
    tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id, for_update=True
    )
    if tx is None or tx.id != associated_tx.id or tx.order_id != order.id:
        raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")
    _require_payme_auth(authorization_header)
    _payme_assert_transaction_association(tx, order, params)
    return tx, order


async def _payme_perform_transaction(
    session: AsyncSession, params: dict, authorization_header: str | None = None
) -> dict:
    tx, order = await _payme_lock_associated_transaction(session, params, authorization_header)
    if params.get("amount") is not None and not _payme_amount_matches(params["amount"], order):
        raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")

    if tx.raw_payload.get("_payme_state") == PAYME_STATE_COMPLETED:
        if tx.raw_payload.get("_payme_perform_request") != params:
            raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Transaction already completed")
        return {
            "transaction": str(tx.id),
            "perform_time": tx.raw_payload.get("_payme_perform_time", _now_ms()),
            "state": PAYME_STATE_COMPLETED,
        }
    if tx.state == PaymentTxState.CANCELLED:
        raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Transaction is cancelled")
    _payme_assert_order_payable(order)
    if await _has_other_paid_transaction(
        session,
        order_id=order.id,
        provider=PaymentProvider.PAYME,
        exclude_id=tx.id,
    ):
        raise PaymeRpcError(
            PAYME_ERR_ORDER_ALREADY_PAID, "Order already paid", data="order_id"
        )

    perform_time = _now_ms()
    payload = dict(tx.raw_payload)
    payload["_payme_perform_request"] = dict(params)
    payload["_payme_state"] = PAYME_STATE_COMPLETED
    payload["_payme_perform_time"] = perform_time
    await payment_repository.update_state(
        session, tx, state=PaymentTxState.PAID, raw_payload=payload
    )

    await order_service.mark_paid(session, order)

    return {
        "transaction": str(tx.id),
        "perform_time": perform_time,
        "state": PAYME_STATE_COMPLETED,
    }


async def _payme_cancel_transaction(
    session: AsyncSession, params: dict, authorization_header: str | None = None
) -> dict:
    tx, _order = await _payme_lock_associated_transaction(
        session, params, authorization_header
    )

    was_completed = tx.raw_payload.get("_payme_state") == PAYME_STATE_COMPLETED
    cancel_time = tx.raw_payload.get("_payme_cancel_time", _now_ms())
    new_state = (
        PAYME_STATE_CANCELLED_AFTER_COMPLETE if was_completed else PAYME_STATE_CANCELLED
    )

    payload = dict(tx.raw_payload)
    payload["_payme_state"] = new_state
    payload["_payme_cancel_time"] = cancel_time
    payload["_payme_cancel_reason"] = params.get("reason")
    await payment_repository.update_state(
        session, tx, state=PaymentTxState.CANCELLED, raw_payload=payload
    )
    # NOTE: cancelling a transaction that already completed (refund) does not automatically
    # revert order.payment_status here — that's a business decision (partial fulfillment may
    # already be underway) and is left for an admin to action manually.

    return {"transaction": str(tx.id), "cancel_time": cancel_time, "state": new_state}


async def _payme_check_transaction(
    session: AsyncSession, params: dict, authorization_header: str | None = None
) -> dict:
    _require_payme_auth(authorization_header)
    payme_tx_id = str(params.get("id", ""))
    tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id
    )
    if tx is None:
        raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")

    payload = tx.raw_payload
    return {
        "create_time": _dt_to_ms(tx.created_at),
        "perform_time": payload.get("_payme_perform_time", 0),
        "cancel_time": payload.get("_payme_cancel_time", 0),
        "transaction": str(tx.id),
        "state": payload.get("_payme_state", PAYME_STATE_CREATED),
        "reason": payload.get("_payme_cancel_reason"),
    }


PAYME_METHODS = {
    "CheckPerformTransaction": _payme_check_perform_transaction,
    "CreateTransaction": _payme_create_transaction,
    "PerformTransaction": _payme_perform_transaction,
    "CancelTransaction": _payme_cancel_transaction,
    "CheckTransaction": _payme_check_transaction,
}


def _payme_authorization_error(request_id: object) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32504, "message": "Insufficient privileges"},
    }


async def payme_handle_rpc(
    session: AsyncSession,
    body: dict,
    *,
    authorization_header: str | None = None,
) -> dict:
    method = body.get("method")
    raw_params = body.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}
    request_id = body.get("id")

    handler = PAYME_METHODS.get(method) if isinstance(method, str) else None
    if handler is None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
    if authorization_header is not None and not verify_payme_auth(authorization_header):
        return _payme_authorization_error(request_id)

    try:
        result = await handler(session, params, authorization_header)
    except PaymeRpcError as exc:
        if exc.code == -32504:
            return _payme_authorization_error(request_id)
        error: dict = {"code": exc.code, "message": exc.message}
        if exc.data:
            error["data"] = exc.data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}
    except OrderNotFoundError:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": PAYME_ERR_ORDER_NOT_FOUND, "message": "Order not found"},
        }

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


# --- Paynet (disabled until its merchant protocol is verified) ----------------------------


async def paynet_check(session: AsyncSession, payload: dict) -> dict:
    return {"result": 0, "error": "Paynet integration is not enabled"}


async def paynet_pay(session: AsyncSession, payload: dict) -> dict:
    return {"result": 0, "error": "Paynet integration is not enabled"}
