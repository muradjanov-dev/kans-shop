import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_audit_event import AdminAuditEvent
from app.services.admin_actor_service import load_live_admin

_SAFE_METADATA_KEYS = frozenset({"receiptversion"})
_PHONE_KEYS = frozenset(
    {"phone", "phonenumber", "customerphone", "mobile", "msisdn", "telephone", "tel"}
)
_CARD_KEYS = frozenset({"card", "cardnumber", "cardno", "pan", "ccnumber"})
_CARD_NUMBER_PARTS = ("cardnumber", "cardno", "cardpan")
_CARD_CONTAINER_KEYS = frozenset({"card", "paymentcard", "creditcard", "debitcard"})
_AUTH_CODE_KEYS = frozenset(
    {"code", "logincode", "verificationcode", "authorizationcode", "authcode"}
)
_SENSITIVE_PARTS = (
    "secret",
    "password",
    "credential",
    "authorization",
    "apikey",
    "privatekey",
    "signature",
    "token",
    "csrf",
    "cookie",
    "session",
    "auth",
    "bearer",
    "otp",
    "login_code",
    "receiptbytes",
    "receiptdata",
    "receiptimage",
    "receiptfileid",
    "receipturl",
    "receiptstoragekey",
    "receiptcontenttype",
)


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalized_key(key)
    if normalized in _SAFE_METADATA_KEYS:
        return False
    if normalized in _AUTH_CODE_KEYS:
        return True
    if normalized.endswith("code") and normalized not in {
        "barcode",
        "ordercode",
        "postcode",
        "productcode",
        "sourcecode",
        "zipcode",
    }:
        return True
    if normalized in _PHONE_KEYS:
        return True
    if "phone" in normalized or normalized in {"mobile", "msisdn"}:
        return True
    if "gateway" in normalized and "payload" in normalized:
        return True
    if "rawpayload" in normalized:
        return True
    if normalized.startswith("receipt"):
        return True
    return any(part.replace("_", "") in normalized for part in _SENSITIVE_PARTS)


def _is_card_key(normalized: str) -> bool:
    return normalized in _CARD_KEYS or any(
        normalized.endswith(part) for part in _CARD_NUMBER_PARTS
    )


def _mask_card(value: object) -> str:
    digits = re.sub(r"\D", "", str(value))
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def _card_number_value(value: object) -> object:
    if isinstance(value, dict):
        for nested_key, nested_value in value.items():
            if isinstance(nested_key, str) and _normalized_key(nested_key) in {
                "number",
                "cardnumber",
                "pan",
                "value",
            }:
                return nested_value
        for nested_value in value.values():
            number = _card_number_value(nested_value)
            if number is not _OMIT:
                return number
        return _OMIT
    if isinstance(value, (list, tuple)):
        for nested_value in value:
            number = _card_number_value(nested_value)
            if number is not _OMIT:
                return number
        return _OMIT
    return value


def _json_safe(value: Any, *, key: str | None = None) -> Any:
    if key is not None:
        normalized = _normalized_key(key)
        if _is_sensitive_key(key):
            return _OMIT
        if _is_card_key(normalized) or normalized in _CARD_CONTAINER_KEYS:
            card_number = _card_number_value(value)
            return _mask_card(card_number) if card_number is not _OMIT else "****"

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                continue
            safe_value = _json_safe(nested_value, key=nested_key)
            if safe_value is not _OMIT:
                sanitized[nested_key] = safe_value
        return sanitized
    if isinstance(value, (list, tuple)):
        return [safe for item in value if (safe := _json_safe(item)) is not _OMIT]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return _OMIT
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return _OMIT


class _OmitValue:
    pass


_OMIT = _OmitValue()


def _redact_snapshot(snapshot: dict[str, object] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    sanitized = _json_safe(snapshot)
    return sanitized if isinstance(sanitized, dict) else {}


async def write_audit_event(
    session: AsyncSession,
    *,
    admin_id: int,
    action: str,
    entity: str,
    entity_id: int | None,
    request_id: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> AdminAuditEvent:
    if not request_id or len(request_id) > 64:
        raise ValueError("request_id must contain 1 to 64 characters")
    actor = await load_live_admin(session, admin_id=admin_id)

    event = AdminAuditEvent(
        actor_admin_id=admin_id,
        actor_name_snapshot=actor.full_name,
        action=action,
        resource_type=entity,
        resource_id=str(entity_id) if entity_id is not None else None,
        request_id=request_id,
        before_json=_redact_snapshot(before),
        after_json=_redact_snapshot(after),
    )
    session.add(event)
    await session.flush()
    return event
