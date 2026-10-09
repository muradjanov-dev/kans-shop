from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    TrafficSourceNotFoundError,
    TrafficSourceValidationError,
)
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.db.models.traffic_source import TrafficSource
from app.db.repositories import traffic_source_repository
from app.db.repositories.traffic_source_repository import SourceStats
from app.services.admin_actor_service import load_live_admin
from app.services.admin_audit_service import write_audit_event
from app.services.common import Page

MANAGEMENT_ROLES = frozenset({AdminRole.SUPERADMIN, AdminRole.MANAGER})


async def _load_manager(session: AsyncSession, *, admin_id: int, lock: bool = False) -> Admin:
    return await load_live_admin(
        session,
        admin_id=admin_id,
        allowed_roles=MANAGEMENT_ROLES,
        lock=lock,
    )


def _source_snapshot(source: TrafficSource) -> dict[str, object]:
    return {
        "id": source.id,
        "name": source.name,
        # The audit redactor treats an unqualified `code` as sensitive; this explicit safe
        # name preserves the campaign slug without weakening redaction for auth codes.
        "source_code": source.code,
        "is_active": source.is_active,
        "clicks_count": source.clicks_count,
    }


async def _write_source_audit(
    session: AsyncSession,
    *,
    admin_id: int,
    action: str,
    source: TrafficSource,
    before: dict[str, object] | None,
) -> None:
    await write_audit_event(
        session,
        admin_id=admin_id,
        action=action,
        entity="traffic_source",
        entity_id=source.id,
        request_id=uuid4().hex,
        before=before,
        after=_source_snapshot(source),
    )


async def list_sources(
    session: AsyncSession,
    *,
    admin_id: int,
    page: int,
    limit: int,
) -> Page[TrafficSource]:
    await _load_manager(session, admin_id=admin_id)
    return await traffic_source_repository.list_page(session, page=page, limit=limit)


async def create_source(
    session: AsyncSession,
    *,
    admin_id: int,
    name: str,
    code: str,
) -> TrafficSource:
    await _load_manager(session, admin_id=admin_id, lock=True)
    normalized_name = name.strip()
    normalized_code = code.strip().lower()
    if not normalized_name or len(normalized_name) > 128:
        raise TrafficSourceValidationError("Source name must contain 1 to 128 characters")
    if not traffic_source_repository.CODE_PATTERN.fullmatch(normalized_code):
        raise TrafficSourceValidationError(
            "Source code must contain 2 to 32 link-safe characters"
        )
    source = await traffic_source_repository.create_unique(
        session, code=normalized_code, name=normalized_name
    )
    await _write_source_audit(
        session,
        admin_id=admin_id,
        action="traffic_source.create",
        source=source,
        before=None,
    )
    return source


async def get_source_stats(
    session: AsyncSession,
    *,
    admin_id: int,
    source_id: int,
) -> SourceStats:
    await _load_manager(session, admin_id=admin_id)
    source = await traffic_source_repository.get_by_id(session, source_id)
    if source is None:
        raise TrafficSourceNotFoundError("Traffic source not found")
    return await traffic_source_repository.get_stats(session, source)


async def update_source(
    session: AsyncSession,
    *,
    admin_id: int,
    source_id: int,
    name: str | None,
    active: bool | None,
) -> TrafficSource:
    await _load_manager(session, admin_id=admin_id, lock=True)
    source = await traffic_source_repository.get_by_id(session, source_id, lock=True)
    if source is None:
        raise TrafficSourceNotFoundError("Traffic source not found")
    if name is None and active is None:
        raise TrafficSourceValidationError("Provide a source name or active state")
    normalized_name = None if name is None else name.strip()
    if normalized_name is not None and not normalized_name:
        raise TrafficSourceValidationError("Source name must not be empty")
    if normalized_name is not None and len(normalized_name) > 128:
        raise TrafficSourceValidationError("Source name must contain at most 128 characters")

    before = _source_snapshot(source)
    if normalized_name is not None:
        source.name = normalized_name
    if active is not None:
        source.is_active = active
    await session.flush()
    await _write_source_audit(
        session,
        admin_id=admin_id,
        action="traffic_source.update",
        source=source,
        before=before,
    )
    return source
