import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_telegram_init_data,
)


def _sign_init_data(params: dict, bot_token: str) -> str:
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signed = dict(params)
    signed["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(signed)


def test_valid_init_data_is_accepted() -> None:
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "AAABBB",
        "user": '{"id":917456291,"first_name":"Test"}',
    }
    init_data = _sign_init_data(params, settings.bot_token)

    result = verify_telegram_init_data(init_data, bot_token=settings.bot_token)

    assert result["user"]["id"] == 917456291


def test_tampered_init_data_is_rejected() -> None:
    params = {
        "auth_date": str(int(time.time())),
        "user": '{"id":917456291,"first_name":"Test"}',
    }
    init_data = _sign_init_data(params, settings.bot_token).replace("Test", "Hacked")

    with pytest.raises(UnauthorizedError):
        verify_telegram_init_data(init_data, bot_token=settings.bot_token)


def test_expired_init_data_is_rejected() -> None:
    old_timestamp = int(time.time()) - 999_999
    params = {"auth_date": str(old_timestamp)}
    init_data = _sign_init_data(params, settings.bot_token)

    with pytest.raises(UnauthorizedError):
        verify_telegram_init_data(init_data, bot_token=settings.bot_token)


def test_missing_hash_is_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        verify_telegram_init_data("auth_date=123&query_id=x", bot_token=settings.bot_token)


def test_access_token_round_trip() -> None:
    token = create_access_token(user_id=42, telegram_id=917456291, is_admin=True)
    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == "42"
    assert payload["telegram_id"] == 917456291
    assert payload["is_admin"] is True


def test_refresh_token_rejected_as_access_token() -> None:
    token = create_refresh_token(user_id=42, telegram_id=917456291)

    with pytest.raises(UnauthorizedError):
        decode_token(token, expected_type="access")


def test_garbage_token_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-jwt", expected_type="access")
