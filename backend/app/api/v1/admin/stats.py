from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_roles
from app.api.schemas.admin import StatsOverviewOut, TopProductOut
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.services import stats_service

router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])
_require_stats_admin = require_admin_roles(
    AdminRole.SUPERADMIN, AdminRole.MANAGER, AdminRole.OPERATOR
)
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/overview", response_model=StatsOverviewOut)
async def get_stats_overview(
    response: Response,
    period: Literal["today", "week", "month"] = Query(default="today"),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_stats_admin),
) -> StatsOverviewOut:
    result = await stats_service.get_admin_stats(
        session, admin_id=admin.id, period=period, now=datetime.now(UTC)
    )
    response.headers["Cache-Control"] = "private, no-store"
    return StatsOverviewOut(
        period=result.period,
        orders_count=result.orders_count,
        order_value=result.order_value,
        paid_amount=result.paid_amount,
        revenue=result.revenue,
        avg_check=result.avg_check,
        new_users=result.new_users,
        top_products=[
            TopProductOut(name=item.name, sold=item.sold) for item in result.top_products
        ],
    )


@router.get("/export.xlsx", include_in_schema=True)
async def export_stats_xlsx(
    period: Literal["today", "week", "month"] = Query(default="today"),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_stats_admin),
) -> Response:
    data = await stats_service.export_admin_stats_xlsx(
        session, admin_id=admin.id, period=period, now=datetime.now(UTC)
    )
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="stats_{period}.xlsx"',
        },
    )
