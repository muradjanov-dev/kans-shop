from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import (
    TrafficSourceCreateIn,
    TrafficSourceDetailOut,
    TrafficSourceOut,
    TrafficSourcePatchIn,
)
from app.api.schemas.common import PageOut
from app.core.config import settings
from app.db.models.admin import Admin
from app.services import traffic_source_service
from app.services.common import Page

router = APIRouter(prefix="/admin/sources", tags=["admin-sources"])
_require_management_admin = require_admin_roles(*MANAGEMENT_ROLES)


def _detail_out(stats: traffic_source_service.SourceStats) -> TrafficSourceDetailOut:
    source = stats.source
    username = settings.bot_username.removeprefix("@").strip()
    return TrafficSourceDetailOut(
        id=source.id,
        name=source.name,
        code=source.code,
        is_active=source.is_active,
        bot_link=f"https://t.me/{username}?start=src_{source.code}",
        clicks=stats.clicks,
        first_touch_users=stats.first_touch_users,
        orders_count=stats.orders_count,
        order_value=stats.order_value,
        created_at=source.created_at,
    )


@router.get("", response_model=PageOut[TrafficSourceOut])
async def list_traffic_sources(
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> PageOut[TrafficSourceOut]:
    result = await traffic_source_service.list_sources(
        session, admin_id=admin.id, page=page, limit=limit
    )
    response.headers["Cache-Control"] = "private, no-store"
    page_out = Page(
        items=[TrafficSourceOut.model_validate(source) for source in result.items],
        total=result.total,
        page=result.page,
        limit=result.limit,
    )
    return PageOut[TrafficSourceOut].from_page(page_out)


@router.post("", response_model=TrafficSourceOut, status_code=status.HTTP_201_CREATED)
async def create_traffic_source(
    payload: TrafficSourceCreateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> TrafficSourceOut:
    source = await traffic_source_service.create_source(
        session,
        admin_id=admin.id,
        name=payload.name,
        code=payload.code,
    )
    return TrafficSourceOut.model_validate(source)


@router.get("/{source_id}", response_model=TrafficSourceDetailOut)
async def get_traffic_source(
    source_id: int,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> TrafficSourceDetailOut:
    stats = await traffic_source_service.get_source_stats(
        session, admin_id=admin.id, source_id=source_id
    )
    response.headers["Cache-Control"] = "private, no-store"
    return _detail_out(stats)


@router.patch("/{source_id}", response_model=TrafficSourceDetailOut)
async def patch_traffic_source(
    source_id: int,
    payload: TrafficSourcePatchIn,
    response: Response,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> TrafficSourceDetailOut:
    source = await traffic_source_service.update_source(
        session,
        admin_id=admin.id,
        source_id=source_id,
        name=payload.name,
        active=payload.active,
    )
    stats = await traffic_source_service.get_source_stats(
        session, admin_id=admin.id, source_id=source.id
    )
    response.headers["Cache-Control"] = "private, no-store"
    return _detail_out(stats)
