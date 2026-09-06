"""Click, Payme and Paynet gateway integration.

Click and Payme implement their own public, versioned merchant protocols (Prepare/Complete for
Click; a JSON-RPC method set for Payme) — the logic below follows those specs. Paynet does not
publish an open spec the way Click/Payme do; `paynet_check`/`paynet_pay` are a best-effort
placeholder built on the common "check then pay" pattern used by most Uzbek payment aggregators,
and MUST be revisited against Paynet's actual API documentation once a merchant agreement with
them is in place (see PAYNET_* settings).
"""

import hashlib
import hmac
import time
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    OrderNotFoundError,
    PaymentNotConfiguredError,
)
from app.db.models.enums import PaymentProvider, PaymentStatus, PaymentTxState
from app.db.models.order import Order
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
        return bool(settings.click_service_id and settings.click_merchant_id)
    if provider == PaymentProvider.PAYME:
        return bool(settings.payme_merchant_id)
    if provider == PaymentProvider.PAYNET:
        return bool(settings.paynet_merchant_id and settings.paynet_api_base_url)
    return False


def build_pay_url(order: Order, provider: PaymentProvider) -> str:
    if not is_provider_configured(provider):
        raise PaymentNotConfiguredError(f"{provider.value} is not configured")

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

    # Paynet: placeholder URL shape — replace with their real checkout entry point once known.
    params = {
        "merchant_id": settings.paynet_merchant_id,
        "order_id": order.order_number,
        "amount": f"{order.total:.2f}",
    }
    return f"{settings.paynet_api_base_url.rstrip('/')}/pay?{urlencode(params)}"


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

    if Decimal(str(params.get("amount", "0"))) != order.total:
        return _click_response(
            params, error=CLICK_ERROR_INVALID_AMOUNT, error_note="Incorrect amount"
        )

    click_trans_id = str(params.get("click_trans_id"))
    existing = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.CLICK, click_trans_id
    )
    if existing is not None:
        tx = existing
    else:
        tx = await payment_repository.create(
            session,
            order_id=order.id,
            provider=PaymentProvider.CLICK,
            amount=order.total,
            provider_transaction_id=click_trans_id,
            state=PaymentTxState.PENDING,
            raw_payload=params,
        )

    return _click_response(params, error=CLICK_ERROR_OK, merchant_prepare_id=tx.id)


async def click_complete(session: AsyncSession, params: dict) -> dict:
    if _click_signature(params, action=1) != params.get("sign_string"):
        return _click_response(
            params, error=CLICK_ERROR_SIGN_FAILED, error_note="SIGN CHECK FAILED!"
        )

    order = await order_repository.get_by_number(session, str(params.get("merchant_trans_id")))
    if order is None:
        return _click_response(
            params, error=CLICK_ERROR_ORDER_NOT_FOUND, error_note="Order not found"
        )

    click_trans_id = str(params.get("click_trans_id"))
    tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.CLICK, click_trans_id, for_update=True
    )
    if tx is None or str(tx.id) != str(params.get("merchant_prepare_id")):
        return _click_response(
            params, error=CLICK_ERROR_TRANSACTION_NOT_FOUND, error_note="Transaction not found"
        )

    if Decimal(str(params.get("amount", "0"))) != order.total:
        return _click_response(
            params, error=CLICK_ERROR_INVALID_AMOUNT, error_note="Incorrect amount"
        )

    # Click sends a negative `error` on its own request when the payment itself failed/was
    # cancelled on their side — we must still ack (error: 0) but mark our side as failed.
    click_reported_error = int(params.get("error", 0))
    if click_reported_error < 0:
        await payment_repository.update_state(
            session, tx, state=PaymentTxState.CANCELLED, raw_payload=params
        )
        return _click_response(params, error=CLICK_ERROR_OK, merchant_confirm_id=tx.id)

    if tx.state == PaymentTxState.PAID:
        return _click_response(params, error=CLICK_ERROR_OK, merchant_confirm_id=tx.id)

    await payment_repository.update_state(
        session, tx, state=PaymentTxState.PAID, raw_payload=params
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

    try:
        decoded = base64.b64decode(authorization_header.removeprefix("Basic ")).decode()
    except (ValueError, UnicodeDecodeError):
        return False
    expected = f"Paycom:{settings.payme_secret_key}"
    return hmac.compare_digest(decoded, expected)


async def _payme_get_order(session: AsyncSession, params: dict) -> Order:
    account = params.get("account") or {}
    order_id = account.get("order_id")
    order = None
    if order_id is not None:
        try:
            order = await order_repository.get_by_id(session, int(order_id))
        except (TypeError, ValueError):
            order = None
    if order is None:
        raise PaymeRpcError(PAYME_ERR_ORDER_NOT_FOUND, "Order not found", data="order_id")
    return order


async def _payme_check_perform_transaction(session: AsyncSession, params: dict) -> dict:
    order = await _payme_get_order(session, params)
    if int(params.get("amount", 0)) != _to_tiyin(order.total):
        raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")
    if order.payment_status == PaymentStatus.PAID:
        raise PaymeRpcError(
            PAYME_ERR_ORDER_ALREADY_PAID, "Order already paid", data="order_id"
        )
    return {"allow": True}


async def _payme_create_transaction(session: AsyncSession, params: dict) -> dict:
    payme_tx_id = str(params.get("id"))
    existing = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id, for_update=True
    )
    if existing is not None:
        if (
            existing.state in (PaymentTxState.CANCELLED,)
            and existing.raw_payload.get("_payme_state") == PAYME_STATE_CANCELLED
        ):
            raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Transaction is cancelled")
        return {
            "create_time": _dt_to_ms(existing.created_at),
            "transaction": str(existing.id),
            "state": existing.raw_payload.get("_payme_state", PAYME_STATE_CREATED),
        }

    order = await _payme_get_order(session, params)
    if int(params.get("amount", 0)) != _to_tiyin(order.total):
        raise PaymeRpcError(PAYME_ERR_INVALID_AMOUNT, "Invalid amount", data="amount")

    other_active = await payment_repository.get_by_order_and_provider(
        session, order.id, PaymentProvider.PAYME
    )
    if other_active is not None and other_active.state == PaymentTxState.PENDING:
        raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Order already has a transaction")

    payload = dict(params)
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
    return {
        "create_time": _dt_to_ms(tx.created_at),
        "transaction": str(tx.id),
        "state": PAYME_STATE_CREATED,
    }


async def _payme_perform_transaction(session: AsyncSession, params: dict) -> dict:
    payme_tx_id = str(params.get("id"))
    tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id, for_update=True
    )
    if tx is None:
        raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")

    if tx.raw_payload.get("_payme_state") == PAYME_STATE_COMPLETED:
        return {
            "transaction": str(tx.id),
            "perform_time": tx.raw_payload.get("_payme_perform_time", _now_ms()),
            "state": PAYME_STATE_COMPLETED,
        }
    if tx.state == PaymentTxState.CANCELLED:
        raise PaymeRpcError(PAYME_ERR_UNABLE_TO_PERFORM, "Transaction is cancelled")

    perform_time = _now_ms()
    payload = dict(tx.raw_payload)
    payload["_payme_state"] = PAYME_STATE_COMPLETED
    payload["_payme_perform_time"] = perform_time
    await payment_repository.update_state(
        session, tx, state=PaymentTxState.PAID, raw_payload=payload
    )

    order = await order_service.get_order(session, tx.order_id)
    await order_service.mark_paid(session, order)

    return {
        "transaction": str(tx.id),
        "perform_time": perform_time,
        "state": PAYME_STATE_COMPLETED,
    }


async def _payme_cancel_transaction(session: AsyncSession, params: dict) -> dict:
    payme_tx_id = str(params.get("id"))
    tx = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYME, payme_tx_id, for_update=True
    )
    if tx is None:
        raise PaymeRpcError(PAYME_ERR_TRANSACTION_NOT_FOUND, "Transaction not found")

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


async def _payme_check_transaction(session: AsyncSession, params: dict) -> dict:
    payme_tx_id = str(params.get("id"))
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


async def payme_handle_rpc(session: AsyncSession, body: dict) -> dict:
    method = body.get("method")
    params = body.get("params") or {}
    request_id = body.get("id")

    handler = PAYME_METHODS.get(method) if isinstance(method, str) else None
    if handler is None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }

    try:
        result = await handler(session, params)
    except PaymeRpcError as exc:
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


# --- Paynet (placeholder — see module docstring) ------------------------------------------


def _paynet_verify_signature(payload: dict, signature: str | None) -> bool:
    """Generic HMAC-SHA1 over sorted `key=value` pairs. Replace with Paynet's real signing
    scheme once their API documentation is available."""
    if not signature:
        return False
    raw = "&".join(f"{k}={payload[k]}" for k in sorted(payload) if k != "sign")
    expected = hmac.new(
        settings.paynet_secret_key.encode(), raw.encode(), hashlib.sha1
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def paynet_check(session: AsyncSession, payload: dict) -> dict:
    if not _paynet_verify_signature(payload, payload.get("sign")):
        return {"result": 0, "error": "Invalid signature"}

    order = await order_repository.get_by_number(session, str(payload.get("order_id")))
    if order is None:
        return {"result": 0, "error": "Order not found"}
    if Decimal(str(payload.get("amount", "0"))) != order.total:
        return {"result": 0, "error": "Invalid amount"}

    return {"result": 1, "order_id": order.order_number, "amount": f"{order.total:.2f}"}


async def paynet_pay(session: AsyncSession, payload: dict) -> dict:
    if not _paynet_verify_signature(payload, payload.get("sign")):
        return {"result": 0, "error": "Invalid signature"}

    order = await order_repository.get_by_number(session, str(payload.get("order_id")))
    if order is None:
        return {"result": 0, "error": "Order not found"}
    if Decimal(str(payload.get("amount", "0"))) != order.total:
        return {"result": 0, "error": "Invalid amount"}

    tx_id = str(payload.get("transaction_id", ""))
    existing = await payment_repository.get_by_provider_tx_id(
        session, PaymentProvider.PAYNET, tx_id, for_update=True
    )
    if existing is not None and existing.state == PaymentTxState.PAID:
        return {"result": 1, "order_id": order.order_number, "transaction_id": tx_id}

    tx = existing or await payment_repository.create(
        session,
        order_id=order.id,
        provider=PaymentProvider.PAYNET,
        amount=order.total,
        provider_transaction_id=tx_id,
        state=PaymentTxState.PENDING,
        raw_payload=payload,
    )
    await payment_repository.update_state(
        session, tx, state=PaymentTxState.PAID, raw_payload=payload
    )
    await order_service.mark_paid(session, order)

    return {"result": 1, "order_id": order.order_number, "transaction_id": tx_id}
