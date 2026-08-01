from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import StatsOverviewOut, TopProductOut
from app.services import stats_service

router = APIRouter(
    prefix="/admin/stats",
    tags=["admin-stats"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


@router.get("/overview", response_model=StatsOverviewOut)
async def get_stats_overview(
    period: Literal["today", "week", "month"] = Query(default="today"),
    session: AsyncSession = Depends(get_db),
) -> StatsOverviewOut:
    result = await stats_service.get_stats(session, period)
    return StatsOverviewOut(
        period=result.period,
        orders_count=result.orders_count,
        revenue=result.revenue,
        avg_check=result.avg_check,
        new_users=result.new_users,
        top_products=[TopProductOut(name=p.name, sold=p.sold) for p in result.top_products],
    )
