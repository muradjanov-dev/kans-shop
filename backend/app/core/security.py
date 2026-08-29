import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60


def _jwt_encode(payload: dict, ttl_seconds: int, token_type: str) -> str:
    now = int(time.time())
    to_encode = {
        **payload,
        "type": token_type,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: int, telegram_id: int, is_admin: bool = False) -> str:
    return _jwt_encode(
        {"sub": str(user_id), "telegram_id": telegram_id, "is_admin": is_admin},
        settings.jwt_access_ttl_minutes * 60,
        "access",
    )


def create_refresh_token(*, user_id: int, telegram_id: int) -> str:
    return _jwt_encode(
        {"sub": str(user_id), "telegram_id": telegram_id},
        settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        "refresh",
    )


def decode_token(token: str, *, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Wrong token type")
    return payload


def verify_telegram_init_data(
    init_data: str, *, bot_token: str, max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS
) -> dict:
    """Validate Telegram WebApp `initData` per Telegram's HMAC-SHA256 scheme and return the
    decoded fields (including a parsed `user` dict) on success.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    # strict_parsing raises on anything that isn't a well-formed query string - including the
    # empty string a non-Telegram browser sends. That's an untrusted request body, so it has to
    # surface as 401 rather than escaping as an unhandled 500 (and paging the error channel).
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise UnauthorizedError("initData is malformed") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise UnauthorizedError("initData missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise UnauthorizedError("initData signature mismatch")

    auth_date = pairs.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        raise UnauthorizedError("initData missing auth_date")

    if time.time() - int(auth_date) > max_age_seconds:
        raise UnauthorizedError("initData expired")

    result = dict(pairs)
    if "user" in result:
        # Signature already verified above, so this is well-formed in practice - but it is
        # still attacker-supplied bytes, and a decode error must not become a 500.
        try:
            result["user"] = json.loads(result["user"])
        except json.JSONDecodeError as exc:
            raise UnauthorizedError("initData user payload is malformed") from exc
    return result


def verify_webhook_secret(provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, settings.webhook_secret)
