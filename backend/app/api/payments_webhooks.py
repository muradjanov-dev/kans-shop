"""Server-to-server callback endpoints for Click, Payme and Paynet.

Deliberately NOT mounted under /api/v1: these calls come from the gateway's servers, not the
Mini App, so they carry no JWT and must stay exempt from RateLimitMiddleware's per-IP limits
(which only apply to /api/v1, see app/api/rate_limit.py) and from CORS. This mirrors how the
Telegram bot webhook is mounted directly in app/main.py rather than under /api/v1.

Each provider expects its own exact response envelope (not our normal `{error:{...}}` shape),
so these handlers call into app.services.payment_service and return its dict verbatim. Any
unexpected exception is caught here (rather than falling through to the app-wide JSON:API error
handler in app/api/errors.py) so the gateway still gets a response shape it can parse.
"""

from fastapi import APIRouter, Header, Request

from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.services import payment_service
from app.services.after_commit import commit_with_after_commit

log = get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["payment-webhooks"])


@router.post("/click/prepare")
async def click_prepare(request: Request) -> dict:
    form = await request.form()
    params = dict(form)
    try:
        async with async_session_maker() as session:
            result = await payment_service.click_prepare(session, params)
            await commit_with_after_commit(session)
        return result
    except Exception:
        log.error("click_prepare_failed", params=params, exc_info=True)
        return {
            "click_trans_id": params.get("click_trans_id"),
            "merchant_trans_id": params.get("merchant_trans_id"),
            "error": payment_service.CLICK_ERROR_REQUEST_FAILED,
            "error_note": "Internal error",
        }


@router.post("/click/complete")
async def click_complete(request: Request) -> dict:
    form = await request.form()
    params = dict(form)
    try:
        async with async_session_maker() as session:
            result = await payment_service.click_complete(session, params)
            await commit_with_after_commit(session)
        return result
    except Exception:
        log.error("click_complete_failed", params=params, exc_info=True)
        return {
            "click_trans_id": params.get("click_trans_id"),
            "merchant_trans_id": params.get("merchant_trans_id"),
            "error": payment_service.CLICK_ERROR_REQUEST_FAILED,
            "error_note": "Internal error",
        }


@router.post("/payme")
async def payme_rpc(
    request: Request, authorization: str | None = Header(default=None)
) -> dict:
    body = await request.json()
    if not payment_service.verify_payme_auth(authorization):
        return payment_service._payme_authorization_error(body.get("id"))
    try:
        async with async_session_maker() as session:
            result = await payment_service.payme_handle_rpc(
                session, body, authorization_header=authorization
            )
            await commit_with_after_commit(session)
        return result
    except Exception:
        log.error("payme_rpc_failed", body=body, exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32603, "message": "Internal error"},
        }


@router.post("/paynet/check")
async def paynet_check(request: Request) -> dict:
    payload = await request.json()
    try:
        async with async_session_maker() as session:
            result = await payment_service.paynet_check(session, payload)
            await commit_with_after_commit(session)
        return result
    except Exception:
        log.error("paynet_check_failed", payload=payload, exc_info=True)
        return {"result": 0, "error": "Internal error"}


@router.post("/paynet/pay")
async def paynet_pay(request: Request) -> dict:
    payload = await request.json()
    try:
        async with async_session_maker() as session:
            result = await payment_service.paynet_pay(session, payload)
            await commit_with_after_commit(session)
        return result
    except Exception:
        log.error("paynet_pay_failed", payload=payload, exc_info=True)
        return {"result": 0, "error": "Internal error"}
